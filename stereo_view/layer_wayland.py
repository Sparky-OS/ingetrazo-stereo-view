# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Campos Ramos (Capitain Jack) and Sparky Stereo OS contributors.
"""The stereo layer of a Qt window on Wayland: a subsurface of its own.

The window stays an ordinary 2D window. Over its contents lies one
``wl_subsurface`` that carries both eyes side by side, left eye first, each
at its render resolution, in a shared-memory buffer; its ``wp_viewport``
destination is the window's size, and it is declared once as full side by
side through libstereo-declare. Stereo KWin draws the left half in the left
eye and the right half in the right eye, resized once to the window's
place.

PySide6 gives the Wayland display (``QNativeInterface.QWaylandApplication``)
but not a window's ``wl_surface``: that is QtWaylandClient's
``QWaylandNativeInterface::nativeResourceForWindow("surface", window)``,
reached here through its exported symbol and checked against the public
display before it is trusted.

Everything this layer creates lives on an event queue of its own, which only
this module dispatches, on the GUI thread; Qt's queue is never touched.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import mmap
import os

log = logging.getLogger("ingetrazo.plugins.stereo_view")

STEREO_SBS_FULL = 3
STEREO_NONE = 0
STEREO_CLASS_SCIENTIFIC = 4
WL_SHM_FORMAT_XRGB8888 = 1
WL_MARSHAL_FLAG_DESTROY = 1


class StereoUnavailable(RuntimeError):
    """This desktop or this Qt cannot take the stereo layer; says why."""


class _Argument(ctypes.Union):
    _fields_ = [("i", ctypes.c_int32), ("u", ctypes.c_uint32),
                ("s", ctypes.c_char_p), ("o", ctypes.c_void_p),
                ("n", ctypes.c_uint32), ("h", ctypes.c_int32)]


class _Message(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("signature", ctypes.c_char_p),
                ("types", ctypes.POINTER(ctypes.c_void_p))]


class _Interface(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_int),
                ("method_count", ctypes.c_int),
                ("methods", ctypes.POINTER(_Message)),
                ("event_count", ctypes.c_int),
                ("events", ctypes.POINTER(_Message))]


_GLOBAL = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32)
_GLOBAL_REMOVE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_uint32)
_RELEASE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)


def _load(name: str, soname: str):
    try:
        return ctypes.CDLL(soname)
    except OSError as exc:
        raise StereoUnavailable(f"{name} ({soname}) is missing") from exc


class _Wayland:
    """libwayland-client, the two viewporter interfaces it does not ship,
    and the calls this module needs, typed once."""

    def __init__(self) -> None:
        lib = self.lib = _load("libwayland-client", "libwayland-client.so.0")
        for name, res, args in (
                ("wl_display_create_queue", ctypes.c_void_p, [ctypes.c_void_p]),
                ("wl_event_queue_destroy", None, [ctypes.c_void_p]),
                ("wl_proxy_create_wrapper", ctypes.c_void_p, [ctypes.c_void_p]),
                ("wl_proxy_wrapper_destroy", None, [ctypes.c_void_p]),
                ("wl_proxy_set_queue", None, [ctypes.c_void_p, ctypes.c_void_p]),
                ("wl_proxy_get_version", ctypes.c_uint32, [ctypes.c_void_p]),
                ("wl_proxy_destroy", None, [ctypes.c_void_p]),
                ("wl_proxy_add_listener", ctypes.c_int,
                 [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
                ("wl_proxy_marshal_array_flags", ctypes.c_void_p,
                 [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                  ctypes.c_uint32, ctypes.c_uint32,
                  ctypes.POINTER(_Argument)]),
                ("wl_display_roundtrip_queue", ctypes.c_int,
                 [ctypes.c_void_p, ctypes.c_void_p]),
                ("wl_display_dispatch_queue_pending", ctypes.c_int,
                 [ctypes.c_void_p, ctypes.c_void_p]),
                ("wl_display_flush", ctypes.c_int, [ctypes.c_void_p]),
                ("wl_display_get_error", ctypes.c_int, [ctypes.c_void_p])):
            fn = getattr(lib, name)
            fn.restype = res
            fn.argtypes = args
        self.iface = {n: ctypes.addressof(ctypes.c_char.in_dll(lib, n + "_interface"))
                      for n in ("wl_registry", "wl_compositor", "wl_subcompositor",
                                "wl_subsurface", "wl_surface", "wl_shm",
                                "wl_shm_pool", "wl_buffer", "wl_region")}
        # wp_viewporter (wayland-protocols, stable/viewporter), as its
        # scanner would generate it.
        self._keep = []
        viewport = _Interface()
        viewporter = _Interface()
        vp_types = (ctypes.c_void_p * 2)(ctypes.addressof(viewport),
                                         self.iface["wl_surface"])
        viewporter_methods = (_Message * 2)(
            _Message(b"destroy", b"", None),
            _Message(b"get_viewport", b"no",
                     ctypes.cast(vp_types, ctypes.POINTER(ctypes.c_void_p))))
        nulls = (ctypes.c_void_p * 4)()
        viewport_methods = (_Message * 3)(
            _Message(b"destroy", b"", None),
            _Message(b"set_source", b"ffff",
                     ctypes.cast(nulls, ctypes.POINTER(ctypes.c_void_p))),
            _Message(b"set_destination", b"ii",
                     ctypes.cast(nulls, ctypes.POINTER(ctypes.c_void_p))))
        viewporter.name, viewporter.version = b"wp_viewporter", 1
        viewporter.method_count, viewporter.methods = 2, viewporter_methods
        viewport.name, viewport.version = b"wp_viewport", 1
        viewport.method_count, viewport.methods = 3, viewport_methods
        self._keep += [viewport, viewporter, vp_types, viewporter_methods,
                       viewport_methods, nulls]
        self.iface["wp_viewporter"] = ctypes.addressof(viewporter)
        self.iface["wp_viewport"] = ctypes.addressof(viewport)

    def request(self, proxy, opcode, args=(), new=None, version=None,
                flags=0, new_last=False):
        """One request; ``args`` are ``(kind, value)`` pairs, ``new`` the
        interface of the object it creates (its new_id comes first, or
        last with ``new_last``, as in ``wl_registry.bind``)."""
        values = [_Argument(**{kind: value}) for kind, value in args]
        if new is not None:
            values.insert(len(values) if new_last else 0, _Argument(n=0))
        arr = (_Argument * max(len(values), 1))(*values)
        ver = version if version is not None else self.lib.wl_proxy_get_version(proxy)
        return self.lib.wl_proxy_marshal_array_flags(
            proxy, opcode, self.iface[new] if new else None, ver, flags, arr)


def _qt_surface(window):
    """``(wl_display *, wl_surface *)`` of a shown QWindow, or a
    :class:`StereoUnavailable` saying why not."""
    import shiboken6
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QGuiApplication, QNativeInterface

    native = QGuiApplication.instance().nativeInterface()
    wayland = native if isinstance(native, QNativeInterface.QWaylandApplication) \
        else None
    if wayland is None:
        try:
            wayland = QNativeInterface.QWaylandApplication(native)   # pragma: no cover
        except Exception:                                          # noqa: BLE001
            wayland = None
    public = int(wayland.display()) if wayland is not None else 0
    gui = _load("QtGui", "libQt6Gui.so.6")
    client = _load("QtWaylandClient", "libQt6WaylandClient.so.6")
    try:
        pni = gui._ZN15QGuiApplication23platformNativeInterfaceEv
        resource = client._ZN15QtWaylandClient23QWaylandNativeInterface23nativeResourceForWindowERK10QByteArrayP7QWindow
    except AttributeError as exc:
        raise StereoUnavailable(
            "this Qt has no QWaylandNativeInterface::nativeResourceForWindow") from exc
    pni.restype = ctypes.c_void_p
    pni.argtypes = []
    resource.restype = ctypes.c_void_p
    resource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    interface = pni()
    win = shiboken6.getCppPointer(window)[0]

    def ask(name: bytes) -> int:
        key = QByteArray(name)
        return int(resource(interface, shiboken6.getCppPointer(key)[0], win) or 0)

    display = ask(b"display")
    if not display or (public and display != public):
        raise StereoUnavailable("Qt's Wayland native interface did not answer "
                                "with the application's display")
    surface = ask(b"surface")
    if not surface:
        raise StereoUnavailable("the window has no Wayland surface yet")
    return display, surface


class WaylandStereoLayer:
    """A declared full side by side subsurface over a shown QWindow."""

    def __init__(self, window) -> None:
        self.wl = _Wayland()
        self.declare = _load("libstereo-declare", "libstereo-declare.so.1")
        d = self.declare
        d.stereo_declare_wayland_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        d.stereo_declare_wayland_init.restype = ctypes.c_int
        d.stereo_supported_wayland.restype = ctypes.c_uint
        d.stereo_declare_wayland.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_uint]
        d.stereo_declare_wayland.restype = ctypes.c_int
        d.stereo_remove_wayland.argtypes = [ctypes.c_void_p]
        d.stereo_remove_wayland.restype = ctypes.c_int
        d.stereo_declare_wayland_finish.restype = None
        d.stereo_declare_version.restype = ctypes.c_uint
        self.library_version = d.stereo_declare_version()
        self.display, self.parent = _qt_surface(window)
        lib = self.wl.lib
        self.queue = lib.wl_display_create_queue(self.display)
        self.wrapper = lib.wl_proxy_create_wrapper(self.display)
        lib.wl_proxy_set_queue(self.wrapper, self.queue)
        self.globals = {}
        self._callbacks = []
        self.registry = self.wl.request(self.wrapper, 1, new="wl_registry",
                                        version=1)
        self._listen(self.registry, _GLOBAL(self._on_global),
                     _GLOBAL_REMOVE(lambda *_a: None))
        self._roundtrip()
        missing = [n for n in ("wl_compositor", "wl_subcompositor", "wl_shm",
                               "wp_viewporter") if n not in self.globals]
        if missing:
            self.close()
            raise StereoUnavailable("the compositor lacks " + ", ".join(missing))
        self.compositor = self._bind("wl_compositor", 4)
        self.subcompositor = self._bind("wl_subcompositor", 1)
        self.shm = self._bind("wl_shm", 1)
        self.viewporter = self._bind("wp_viewporter", 1)
        if d.stereo_declare_wayland_init(self.display, self.queue) != 0:
            self.close()
            raise StereoUnavailable("stereo_declare_wayland_init failed")
        self._declare_ready = True
        self._roundtrip()
        self.supported = d.stereo_supported_wayland()
        if not self.supported:
            self.close()
            raise StereoUnavailable("this desktop does not take stereo "
                                    "declarations (no kde_stereo_content_manager_v1)")
        self.surface = self.wl.request(self.compositor, 0, new="wl_surface")
        self.subsurface = self.wl.request(
            self.subcompositor, 1, [("o", self.surface), ("o", self.parent)],
            new="wl_subsurface")
        self.viewport = self.wl.request(self.viewporter, 1,
                                        [("o", self.surface)], new="wp_viewport")
        region = self.wl.request(self.compositor, 1, new="wl_region")
        self.wl.request(self.surface, 5, [("o", region)])      # no input: the window's
        self.wl.request(region, 0, flags=WL_MARSHAL_FLAG_DESTROY)
        self.wl.request(self.subsurface, 2, [("o", self.parent)])   # place_above
        self.wl.request(self.subsurface, 5)                        # set_desync
        self.declared = d.stereo_declare_wayland(
            self.surface, STEREO_SBS_FULL, STEREO_CLASS_SCIENTIFIC, 0) == 0
        if not self.declared:
            self.close()
            raise StereoUnavailable("stereo_declare_wayland failed")
        self.buffers = []          # [buffer, pool, mmap, fd, size, busy]
        self.position = None
        self.destination = None
        self.commits = 0
        lib.wl_display_flush(self.display)

    # ---- Wayland plumbing -----------------------------------------------------
    def _listen(self, proxy, *functions) -> None:
        table = (ctypes.c_void_p * len(functions))(
            *[ctypes.cast(f, ctypes.c_void_p) for f in functions])
        self._callbacks.append((functions, table))
        self.wl.lib.wl_proxy_add_listener(proxy, table, None)

    def _on_global(self, _data, _registry, name, interface, version) -> None:
        self.globals[interface.decode()] = (name, version)

    def _bind(self, interface: str, version: int):
        name, offered = self.globals[interface]
        version = min(version, offered)
        return self.wl.request(self.registry, 0,
                               [("u", name), ("s", interface.encode()),
                                ("u", version)], new=interface, version=version,
                               new_last=True)

    def _roundtrip(self) -> None:
        if self.wl.lib.wl_display_roundtrip_queue(self.display, self.queue) < 0:
            raise StereoUnavailable("the Wayland connection failed (error %d)"
                                    % self.wl.lib.wl_display_get_error(self.display))

    # ---- Frames -----------------------------------------------------------------
    def place(self, x: int, y: int, width: int, height: int) -> None:
        """Where the stereo layer lies in the window's surface, and the size
        one eye is shown at (logical pixels)."""
        if (x, y) != self.position:
            self.wl.request(self.subsurface, 1, [("i", int(x)), ("i", int(y))])
            self.position = (x, y)
        if (width, height) != self.destination and width > 0 and height > 0:
            self.wl.request(self.viewport, 2, [("i", int(width)), ("i", int(height))])
            self.destination = (width, height)

    def _release(self, entry):
        def on_release(_data, _buffer):
            entry[5] = False
        return _RELEASE(on_release)

    def _free_buffer(self, width: int, height: int):
        lib = self.wl.lib
        lib.wl_display_dispatch_queue_pending(self.display, self.queue)
        if sum(1 for e in self.buffers if e[5]) >= 3:
            self._roundtrip()          # the compositor still holds three
        stride = width * 4
        size = stride * height
        for entry in self.buffers:
            if not entry[5] and entry[4] == (width, height):
                return entry
        # Different size: the free buffers of the old size go.
        for entry in [e for e in self.buffers if not e[5]]:
            self._destroy_buffer(entry)
        fd = os.memfd_create("ingetrazo-stereo", os.MFD_CLOEXEC)
        os.ftruncate(fd, size)
        mem = mmap.mmap(fd, size)
        pool = self.wl.request(self.shm, 0, [("h", fd), ("i", size)],
                               new="wl_shm_pool")
        buffer = self.wl.request(pool, 0, [("i", 0), ("i", width), ("i", height),
                                           ("i", stride),
                                           ("u", WL_SHM_FORMAT_XRGB8888)],
                                 new="wl_buffer")
        entry = [buffer, pool, mem, fd, (width, height), False, None]
        entry[6] = self._release(entry)
        self._listen(buffer, entry[6])
        self.buffers.append(entry)
        return entry

    def _destroy_buffer(self, entry) -> None:
        self.wl.request(entry[0], 0, flags=WL_MARSHAL_FLAG_DESTROY)
        self.wl.request(entry[1], 1, flags=WL_MARSHAL_FLAG_DESTROY)
        entry[2].close()
        os.close(entry[3])
        self.buffers.remove(entry)

    def present(self, left, right) -> None:
        """Hand both eyes over: ``left`` and ``right`` are ``(h, w, 4)``
        uint8 arrays in XRGB8888 memory order (Qt's Format_RGB32), each
        copied whole into its half; nothing is resized."""
        import numpy as np
        h, w = left.shape[:2]
        if right.shape[:2] != (h, w):
            raise ValueError("the two eyes differ in size")
        entry = self._free_buffer(2 * w, h)
        frame = np.frombuffer(entry[2], dtype=np.uint8).reshape(h, 2 * w, 4)
        frame[:, :w] = left
        frame[:, w:] = right
        del frame
        entry[5] = True
        self.wl.request(self.surface, 1, [("o", entry[0]), ("i", 0), ("i", 0)])
        self.wl.request(self.surface, 9, [("i", 0), ("i", 0), ("i", 2 * w), ("i", h)])
        self.wl.request(self.surface, 6)                           # commit
        self.commits += 1
        self.wl.lib.wl_display_flush(self.display)

    def close(self) -> None:
        """Remove the declaration and every object of this layer."""
        lib = self.wl.lib
        d = self.declare
        surface = getattr(self, "surface", None)
        if surface:
            if getattr(self, "declared", False):
                d.stereo_remove_wayland(surface)
            self.wl.request(surface, 1, [("o", None), ("i", 0), ("i", 0)])
            self.wl.request(surface, 6)
        for name in ("viewport", "subsurface"):
            proxy = getattr(self, name, None)
            if proxy:
                self.wl.request(proxy, 0, flags=WL_MARSHAL_FLAG_DESTROY)
                setattr(self, name, None)
        if surface:
            self.wl.request(surface, 0, flags=WL_MARSHAL_FLAG_DESTROY)
            self.surface = None
        for entry in list(getattr(self, "buffers", ())):
            self._destroy_buffer(entry)
        if getattr(self, "_declare_ready", False):
            d.stereo_declare_wayland_finish()
            self._declare_ready = False
        for name in ("viewporter", "shm", "subcompositor", "compositor"):
            proxy = getattr(self, name, None)
            if proxy:
                if name in ("viewporter", "subcompositor"):
                    self.wl.request(proxy, 0, flags=WL_MARSHAL_FLAG_DESTROY)
                else:
                    lib.wl_proxy_destroy(proxy)
                setattr(self, name, None)
        if getattr(self, "registry", None):
            lib.wl_proxy_destroy(self.registry)
            self.registry = None
        if self.display:
            lib.wl_display_flush(self.display)
        if getattr(self, "wrapper", None):
            lib.wl_proxy_wrapper_destroy(self.wrapper)
            self.wrapper = None
        if getattr(self, "queue", None):
            lib.wl_display_roundtrip_queue(self.display, self.queue)
            lib.wl_event_queue_destroy(self.queue)
            self.queue = None
