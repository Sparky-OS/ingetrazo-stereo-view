# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Campos Ramos (Capitain Jack) and Sparky Stereo OS contributors.
"""Stereo view: the model in stereo 3D, in a view of its own.

An IngeTrazo extension for desktops that take a stereo declaration
(Stereo KWin, Sparky Stereo OS). The modelling stays in IngeTrazo's main
viewport, in 2D; the extension's window shows the same model through two
eye cameras (``cameras.py``), drawn by IngeTrazo's own renderer once per
eye, handed to the desktop as full side by side (both eyes next to each
other, left eye first, each at its render resolution) and declared once
through libstereo-declare. The desktop shows each eye to its eye on every
kind of 3D screen and resizes the eyes once, to the window.

Its only options, in Extensions ▸ Stereo 3D:

- Enable 3D (opens and closes the stereo view; remembered);
- Render resolution per eye (Follow the window, or 720p to 2160p with the
  width following the window's shape);
- Display Settings… (``kcmshell6 kcm_kscreen``), where each screen's 3D mode,
  eye order and stereo format are chosen: they belong to the desktop's
  outputs, so the extension has none.

It draws its own scene, so it offers no eye swap.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, QProcess, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QImage, QPalette
from PySide6.QtWidgets import QMessageBox, QWidget

from .cameras import SEPARATION_RATIO, eye_pair
from .layer_wayland import StereoUnavailable
from .strings import tr

log = logging.getLogger("ingetrazo.plugins.stereo_view")

__version__ = "0.1.0"

SETTINGS = "extensions/stereo_view"
#: Render resolutions per eye offered besides «Follow the window»: the
#: number of rows; the width follows the window's shape, so no eye is ever
#: stretched to another shape.
LINES = (720, 1080, 1440, 2160)
DISPLAY_SETTINGS = ("kcmshell6", ["kcm_kscreen"])


def qimage_rgb32(image: QImage):
    """A render's pixels as an ``(h, w, 4)`` uint8 array in Format_RGB32
    memory order (B, G, R, 0xff on little-endian), the order of
    WL_SHM_FORMAT_XRGB8888 and of a 24-bit X11 ZPixmap."""
    import numpy as np
    straight = {
        QImage.Format_ARGB32_Premultiplied: QImage.Format_ARGB32,
        QImage.Format_RGBA8888_Premultiplied: QImage.Format_RGBA8888,
    }.get(image.format())
    if straight is not None:
        # The render composed its own background: its colour is final, the
        # alpha a translucent face left behind is not (see the composer).
        image = image.copy()
        image.reinterpretAsFormat(straight)
    image = image.convertToFormat(QImage.Format_RGB32)
    w, h = image.width(), image.height()
    raw = np.frombuffer(image.constBits(), dtype=np.uint8,
                        count=image.bytesPerLine() * h)
    return raw.reshape(h, image.bytesPerLine())[:, :4 * w].reshape(h, w, 4).copy()


class StereoView(QWidget):
    """The extension's window: one 3D area, nothing else in it."""

    def __init__(self, controller) -> None:
        super().__init__(controller.app.window, Qt.Window)
        self.controller = controller
        self.setWindowTitle(tr("Stereo view") + " — IngeTrazo")
        self.setObjectName("stereo_view_window")
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(0, 0, 0))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.resize(960, 540)
        self.layer = None
        self.platform = QGuiApplication.platformName()
        if self.platform == "xcb":
            # Both eyes go to the window as one picture twice as wide as Qt
            # believes it is: Qt must not paint over them.
            self.setAttribute(Qt.WA_PaintOnScreen, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_OpaquePaintEvent, True)
            self.setAutoFillBackground(False)

    def paintEngine(self):                                  # noqa: N802
        return None if self.platform == "xcb" else super().paintEngine()

    def paintEvent(self, event) -> None:                    # noqa: N802
        if self.platform == "xcb":
            self.controller.request_frame(force=True)
            return
        super().paintEvent(event)

    def showEvent(self, event) -> None:                     # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.controller.attach)

    def hideEvent(self, event) -> None:                     # noqa: N802
        self.controller.detach()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:                   # noqa: N802
        super().resizeEvent(event)
        self.controller.request_frame(force=True)

    def closeEvent(self, event) -> None:                    # noqa: N802
        self.controller.set_enabled(False)
        super().closeEvent(event)

    def event(self, ev) -> bool:
        if ev.type() == QEvent.PlatformSurface and \
                ev.surfaceEventType() == ev.SurfaceEventType.SurfaceAboutToBeDestroyed:
            self.controller.detach()
        return super().event(ev)


class StereoController:
    """Settings, menu, the view's lifetime and its frames."""

    def __init__(self, app) -> None:
        self.app = app
        self.view = None
        self.layer = None
        self.error = None
        self._last = None
        self._pending = False
        self.frames = 0
        self.last_frame = None          # what the last frame handed over, for tests
        self.on_present = []            # callbacks(left, right, info), for tests
        self.x11_place = None           # X11 with rows chosen: the size shown
        self._proposal = None           # X11: the desktop's proposal to answer
        self._poll = QTimer()
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._poll_proposal)
        st = QSettings()
        self.lines = int(st.value(SETTINGS + "/lines", 0) or 0)
        if self.lines not in LINES:
            self.lines = 0
        self.enabled = str(st.value(SETTINGS + "/enabled", "false")).lower() == "true"
        self._build_menu()
        app.add_overlay(self._after_frame)
        if self.enabled:
            QTimer.singleShot(0, lambda: self.set_enabled(True))

    # ---- The three options ------------------------------------------------------
    def _build_menu(self) -> None:
        menu = self.app.add_menu(tr("Stereo 3D"))
        self.menu = menu
        if menu is None:
            self.enable_action = self.display_action = None
            self.resolution_actions = {}
            return
        self.enable_action = QAction(tr("Enable 3D"), menu)
        self.enable_action.setCheckable(True)
        self.enable_action.setChecked(self.enabled)
        self.enable_action.setStatusTip(tr(
            "Shows the model in stereo in a window of its own; the modelling stays in the main view."))
        self.enable_action.toggled.connect(self.set_enabled)
        menu.addAction(self.enable_action)
        sub = menu.addMenu(tr("Render resolution per eye"))
        sub.setStatusTip(tr(
            "How many pixels each eye is drawn with; the desktop resizes the eyes once, to the window."))
        self.resolution_menu = sub
        group = QActionGroup(sub)
        self.resolution_actions = {}
        for lines in (0,) + LINES:
            text = (tr("Follow the window") if lines == 0
                    else tr("{lines}p (the width follows the window)", lines=lines))
            act = QAction(text, sub)
            act.setCheckable(True)
            act.setChecked(lines == self.lines)
            act.triggered.connect(lambda _c=False, n=lines: self.set_lines(n))
            group.addAction(act)
            sub.addAction(act)
            self.resolution_actions[lines] = act
        self.display_action = QAction(tr("Display Settings…"), menu)
        self.display_action.setStatusTip(tr(
            "Opens the display settings, where each screen's 3D mode is chosen."))
        self.display_action.triggered.connect(self.open_display_settings)
        menu.addAction(self.display_action)

    def set_enabled(self, on: bool) -> None:
        on = bool(on)
        if self.enable_action is not None and self.enable_action.isChecked() != on:
            self.enable_action.blockSignals(True)
            self.enable_action.setChecked(on)
            self.enable_action.blockSignals(False)
        self.enabled = on
        QSettings().setValue(SETTINGS + "/enabled", "true" if on else "false")
        if on:
            if self.view is None:
                self.view = StereoView(self)
            self.view.show()
            self.view.raise_()
        elif self.view is not None:
            view, self.view = self.view, None
            view.hide()
            view.deleteLater()

    def set_lines(self, lines: int) -> None:
        view = self.view
        if view is not None and view.platform == "xcb":
            place = self.place_size()
            if lines:
                self.x11_place = place
            elif self.x11_place is not None:
                self.x11_place = None
                view.resize(*place)          # the window is the place again
        self.lines = int(lines)
        QSettings().setValue(SETTINGS + "/lines", self.lines)
        self.request_frame(force=True)

    def _poll_proposal(self) -> None:
        """X11: the desktop proposes a new place when the person resizes a
        window shown at a declared size (support version 7); the view
        renders for it and answers with the size it drew for."""
        layer = self.layer
        if layer is None or not hasattr(layer, "proposal") or not self.lines:
            return
        req = layer.proposal()
        if req is not None:
            self._proposal = req
            self.x11_place = (int(req.width), int(req.height))
            self.request_frame(force=True)

    def open_display_settings(self) -> bool:
        program, args = DISPLAY_SETTINGS
        return bool(QProcess.startDetached(program, args))

    # ---- The layer ---------------------------------------------------------------
    def attach(self) -> None:
        view = self.view
        if view is None or not view.isVisible() or self.layer is not None:
            return
        try:
            if view.platform == "wayland":
                from .layer_wayland import WaylandStereoLayer
                self.layer = WaylandStereoLayer(view.windowHandle())
            elif view.platform == "xcb":
                from .layer_x11 import X11StereoLayer
                self.layer = X11StereoLayer(int(view.winId()))
            else:
                raise StereoUnavailable("Qt platform %r has no stereo route"
                                        % view.platform)
        except StereoUnavailable as exc:
            self.error = str(exc)
            log.warning("stereo view unavailable: %s", exc)
            QMessageBox.information(self.app.window, tr("Stereo 3D"),
                                    tr("Stereo 3D is not available here: {reason}",
                                       reason=str(exc)))
            self.set_enabled(False)
            return
        self.error = None
        if view.platform == "xcb":
            self._poll.start()
        log.info("stereo view attached on %s", view.platform)
        self.request_frame(force=True)

    def detach(self) -> None:
        self._poll.stop()
        layer, self.layer = self.layer, None
        self._last = None
        if layer is not None:
            try:
                layer.close()
            except Exception:                               # noqa: BLE001
                log.exception("closing the stereo layer")

    # ---- Frames -----------------------------------------------------------------
    def place_size(self):
        """The size one eye is shown at, in logical pixels: the window's.
        On X11 with a chosen number of rows the window itself is one eye's
        render resolution (Stereo KWin shows it at the declared size), so
        the place is kept apart, and follows the desktop's proposals."""
        view = self.view
        if view.platform == "xcb" and self.lines and self.x11_place is not None:
            return self.x11_place
        return max(view.width(), 1), max(view.height(), 1)

    def eye_size(self):
        """One eye's render resolution: the window's own pixels, or the rows
        chosen with the width of the window's shape."""
        view = self.view
        pw, ph = self.place_size()
        dpr = view.devicePixelRatioF() if view.platform == "wayland" else 1.0
        w = max(int(round(pw * dpr)), 64)
        h = max(int(round(ph * dpr)), 64)
        if self.lines:
            w = max(int(round(self.lines * w / h)), 64)
            h = self.lines
        return w, h

    def _signature(self):
        vp = self.app.viewport
        cam = vp.camera
        t = cam.target
        sc = vp.scene
        shadows = getattr(sc, "shadows", None)
        return ((t.x(), t.y(), t.z(), cam.distance, cam.yaw, cam.pitch,
                 cam.fov_deg, cam.perspective, cam.two_point,
                 cam.up.x(), cam.up.y(), cam.up.z()),
                id(sc), sc.version, id(getattr(sc, "edit_group", None)),
                repr(getattr(sc, "display_style", None)),
                id(getattr(vp, "style_override", None)),
                repr(shadows.to_dict()) if shadows is not None else None,
                self.eye_size(), self.place_size(), (self.view.width(), self.view.height()))

    def _after_frame(self, _viewport, _painter) -> None:
        """Called after every frame of the main viewport (an overlay that
        draws nothing): the cue that the model or the camera may have
        changed."""
        if self.layer is not None and not self._pending \
                and self._signature() != self._last:
            self.request_frame()

    def request_frame(self, force: bool = False) -> None:
        if force:
            self._last = None
        if self._pending or self.view is None:
            return
        self._pending = True
        QTimer.singleShot(0, self.render)

    def render(self) -> None:
        self._pending = False
        view, layer = self.view, self.layer
        if view is None or layer is None or not view.isVisible():
            return
        sig = self._signature()
        if sig == self._last:
            return
        vp = self.app.viewport
        w, h = self.eye_size()
        if view.platform == "xcb":
            # The X11 window is one eye's render resolution as the program
            # asks for it: with rows chosen, it is resized to the eye (the
            # desktop doubles it and shows it at the place).
            if self.lines and (view.width(), view.height()) != (w, h):
                if self.x11_place is None:
                    self.x11_place = (view.width(), view.height())
                view.resize(w, h)
                self._last = None
                QTimer.singleShot(50, lambda: self.request_frame(force=True))
                return
        t0 = time.perf_counter()
        base = vp.camera
        left_cam, right_cam, separation = eye_pair(base, w, h)
        images = []
        try:
            for cam in (left_cam, right_cam):
                vp.camera = cam
                image = vp.render_image(w, h, overlays=False)
                if image is None or image.isNull():
                    return
                images.append(image)
        finally:
            vp.camera = base
        left, right = qimage_rgb32(images[0]), qimage_rgb32(images[1])
        if view.platform == "wayland":
            margins = view.windowHandle().frameMargins()
            layer.place(margins.left(), margins.top(), view.width(), view.height())
            layer.present(left, right)
        else:
            pw, ph = self.place_size()
            layer.show_at(pw, ph, w, h)
            if not layer.present(left, right):
                # Not doubled yet: the desktop may read the declaration late.
                QTimer.singleShot(50, lambda: self.request_frame(force=True))
                return
            if self._proposal is not None:
                layer.commit(self._proposal, pw, ph)
                self._proposal = None
        self._last = sig
        self.frames += 1
        info = {"eye": (w, h), "window": self.place_size(),
                "separation": separation, "zero_parallax": left_cam.zero_parallax,
                "ratio": SEPARATION_RATIO, "ms": (time.perf_counter() - t0) * 1000.0,
                "platform": view.platform, "base": base}
        self.last_frame = info
        for fn in list(self.on_present):
            try:
                fn(left, right, info)
            except Exception:                               # noqa: BLE001
                log.exception("stereo view frame listener")
        if view.platform == "wayland":
            view.update()           # a subsurface's place applies with its parent's commit


_controller = None


def setup(app) -> None:
    global _controller
    _controller = StereoController(app)
    app.window.__dict__["stereo_view"] = _controller


def controller():
    """The running extension (tests and the Python Console)."""
    return _controller
