# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Campos Ramos (Capitain Jack) and Sparky Stereo OS contributors.
"""The stereo view on X11 (IngeTrazo under xcb, through Xwayland).

The view's own top-level X11 window is declared full side by side through
libstereo-declare before it is mapped. Its size, as the program asks for
it, is one eye's render resolution; Stereo KWin (support version 3 and
later) makes the X11 window hold both eyes, twice as wide, and shows it on
screen as one view. When the size one view is shown at differs from the
render resolution, the view declares it (``ONE_VIEW_SIZE``, support 6).

Qt's backing store only knows the size it asked for, so the window paints
on screen itself (``WA_PaintOnScreen``): both eyes, copied whole into one
picture twice as wide, go to the window with ``xcb_put_image`` on Qt's own
connection, in strips that fit the server's request size.
"""
from __future__ import annotations

import ctypes
import logging

from .layer_wayland import (STEREO_CLASS_SCIENTIFIC, STEREO_SBS_FULL,
                            StereoUnavailable, _load)

log = logging.getLogger("ingetrazo.plugins.stereo_view")

_ZPIXMAP = 2
ONE_VIEW_SIZE_VERSION = 6


class _Cookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint)]


class OneViewRequest(ctypes.Structure):
    _fields_ = [("serial", ctypes.c_uint), ("width", ctypes.c_uint),
                ("height", ctypes.c_uint)]


class _Geometry(ctypes.Structure):
    _fields_ = [("response_type", ctypes.c_uint8), ("depth", ctypes.c_uint8),
                ("sequence", ctypes.c_uint16), ("length", ctypes.c_uint32),
                ("root", ctypes.c_uint32), ("x", ctypes.c_int16),
                ("y", ctypes.c_int16), ("width", ctypes.c_uint16),
                ("height", ctypes.c_uint16), ("border_width", ctypes.c_uint16)]


def _qt_x11():
    """``(Display *, xcb_connection_t *)`` of the running Qt application."""
    from PySide6.QtGui import QGuiApplication, QNativeInterface
    native = QGuiApplication.instance().nativeInterface()
    if not isinstance(native, QNativeInterface.QX11Application):
        raise StereoUnavailable("IngeTrazo is not running on X11")
    return int(native.display()), int(native.connection())


class X11StereoLayer:
    """The declaration of a view's X11 window and its on-screen painting."""

    def __init__(self, window_id: int) -> None:
        self.display, self.connection = _qt_x11()
        self.xid = int(window_id)
        d = self.declare = _load("libstereo-declare", "libstereo-declare.so.1")
        d.stereo_supported_x11.argtypes = [ctypes.c_void_p]
        d.stereo_supported_x11.restype = ctypes.c_uint
        d.stereo_declare_x11.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_uint]
        d.stereo_declare_x11.restype = ctypes.c_int
        d.stereo_declare_x11_one_view_size.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                       ctypes.c_uint, ctypes.c_uint]
        d.stereo_declare_x11_one_view_size.restype = ctypes.c_int
        d.stereo_x11_one_view_event.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                ctypes.c_void_p,
                                                ctypes.POINTER(OneViewRequest)]
        d.stereo_x11_one_view_event.restype = ctypes.c_int
        d.stereo_declare_x11_one_view_commit.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(OneViewRequest),
            ctypes.c_uint, ctypes.c_uint]
        d.stereo_declare_x11_one_view_commit.restype = ctypes.c_int
        d.stereo_remove_x11.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        d.stereo_remove_x11.restype = ctypes.c_int
        x = self.xcb = _load("libxcb", "libxcb.so.1")
        x.xcb_generate_id.argtypes = [ctypes.c_void_p]
        x.xcb_generate_id.restype = ctypes.c_uint32
        x.xcb_create_gc.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                    ctypes.c_uint32, ctypes.c_void_p]
        x.xcb_create_gc.restype = _Cookie
        x.xcb_free_gc.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        x.xcb_free_gc.restype = _Cookie
        x.xcb_put_image.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint32,
                                    ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint16,
                                    ctypes.c_int16, ctypes.c_int16, ctypes.c_uint8,
                                    ctypes.c_uint8, ctypes.c_uint32, ctypes.c_void_p]
        x.xcb_put_image.restype = _Cookie
        x.xcb_get_geometry.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        x.xcb_get_geometry.restype = _Cookie
        x.xcb_get_geometry_reply.argtypes = [ctypes.c_void_p, _Cookie, ctypes.c_void_p]
        x.xcb_get_geometry_reply.restype = ctypes.POINTER(_Geometry)
        x.xcb_get_maximum_request_length.argtypes = [ctypes.c_void_p]
        x.xcb_get_maximum_request_length.restype = ctypes.c_uint32
        x.xcb_flush.argtypes = [ctypes.c_void_p]
        x.xcb_flush.restype = ctypes.c_int
        self.libc = ctypes.CDLL(None)
        self.libc.free.argtypes = [ctypes.c_void_p]
        self.supported = d.stereo_supported_x11(self.display)
        if self.supported < 3:
            raise StereoUnavailable("this desktop does not take stereo "
                                    "declarations of X11 windows (support %d)"
                                    % self.supported)
        if d.stereo_declare_x11(self.display, self.xid, STEREO_SBS_FULL,
                                STEREO_CLASS_SCIENTIFIC, 0) != 0:
            raise StereoUnavailable("stereo_declare_x11 failed")
        self.declared = True
        self.view_size = None
        self.gc = x.xcb_generate_id(self.connection)
        x.xcb_create_gc(self.connection, self.gc, self.xid, 0, None)
        self.max_bytes = x.xcb_get_maximum_request_length(self.connection) * 4
        self.commits = 0
        x.xcb_flush(self.connection)

    def show_at(self, width: int, height: int, render_width: int,
                render_height: int) -> None:
        """The size one view is shown at, when it is not its resolution."""
        if self.supported < ONE_VIEW_SIZE_VERSION:
            return
        size = ((width, height) if (width, height) != (render_width, render_height)
                else (0, 0))
        if size != self.view_size:
            self.declare.stereo_declare_x11_one_view_size(
                self.display, self.xid, *size)
            self.view_size = size

    def proposal(self):
        """The desktop's current proposal for the place (support version 7),
        once per serial; None when there is none or it was answered."""
        if self.supported < 7 or self.view_size in (None, (0, 0)):
            return None
        req = OneViewRequest()
        if self.declare.stereo_x11_one_view_event(self.display, self.xid, None,
                                                  ctypes.byref(req)) != 1:
            return None
        if req.serial == getattr(self, "answered", None):
            return None
        return req

    def commit(self, req, width: int, height: int) -> None:
        """Answer a proposal with the size one view was drawn for."""
        self.declare.stereo_declare_x11_one_view_commit(
            self.display, self.xid, ctypes.byref(req), int(width), int(height))
        self.answered = req.serial
        self.view_size = (int(width), int(height))

    def geometry(self):
        """The X11 window's own size, as the server has it."""
        x = self.xcb
        reply = x.xcb_get_geometry_reply(
            self.connection, x.xcb_get_geometry(self.connection, self.xid), None)
        if not reply:
            return None
        size = (reply.contents.width, reply.contents.height, reply.contents.depth)
        self.libc.free(ctypes.cast(reply, ctypes.c_void_p))
        return size

    def present(self, left, right) -> bool:
        """Paint both eyes into the window, once it holds both; False while
        the desktop has not doubled it yet (a late doubling is legal)."""
        import numpy as np
        h, w = left.shape[:2]
        geom = self.geometry()
        if geom is None or geom[0] != 2 * w or geom[1] != h:
            return False
        frame = np.empty((h, 2 * w, 4), dtype=np.uint8)
        frame[:, :w] = left
        frame[:, w:] = right
        depth = geom[2]
        row = 2 * w * 4
        rows = max(1, (self.max_bytes - 64) // row)
        x = self.xcb
        for top in range(0, h, rows):
            chunk = np.ascontiguousarray(frame[top:top + rows])
            x.xcb_put_image(self.connection, _ZPIXMAP, self.xid, self.gc,
                            2 * w, chunk.shape[0], 0, top, 0, depth,
                            chunk.nbytes, chunk.ctypes.data)
        x.xcb_flush(self.connection)
        self.commits += 1
        return True

    def close(self) -> None:
        if getattr(self, "declared", False):
            self.declare.stereo_remove_x11(self.display, self.xid)
            self.declared = False
        if getattr(self, "gc", None):
            self.xcb.xcb_free_gc(self.connection, self.gc)
            self.gc = None
        self.xcb.xcb_flush(self.connection)
