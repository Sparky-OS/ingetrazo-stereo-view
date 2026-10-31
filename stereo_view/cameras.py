# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Campos Ramos (Capitain Jack) and Sparky Stereo OS contributors.
"""The two eye cameras of one model.

One world, two cameras: the scene, its lights and its sun shadow map exist
once; only what each camera sees is drawn per eye. Each eye is the
viewport's own camera moved sideways along the camera's right, with
parallel axes (never toe-in, which makes keystone and vertical disparity),
and its frustum shifted so the plane through the orbit target stays at
screen depth: the point you orbit around is where the screen is, nearer
things come out of it, farther ones go in.

- Perspective (and two-point perspective): the standard asymmetric
  frustum. The eye at ``offset`` metres along the right (negative for the
  left eye) sees the near-plane window shifted by ``-offset * near / C``,
  ``C`` the target's depth, so a point at depth ``Z`` lands
  ``offset * (1 - C / Z)`` metres (measured on the target's plane) from
  where the viewport shows it.
- Parallel: moving an orthographic camera only slides the picture, so the
  eye is the same view sheared about the target's plane,
  ``x' = x + (offset / C) * (Z - C)``: the same disparity per metre of
  depth as the perspective at the target, zero on the target's plane.

The separation follows the stereographers' rule of thumb: the two cameras
are one thirtieth of the distance to the point of interest apart
(``SEPARATION_RATIO``), so on a 16:9 view of 45 degrees a point at infinity
lies 2.3 % of the view's width behind the screen in each eye's direction.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QMatrix4x4, QVector3D

from core.camera import OrbitCamera

#: Interaxial over the distance to the zero-parallax plane (the 1/30 rule).
SEPARATION_RATIO = 1.0 / 30.0

#: Fields of the viewport's camera an eye copies (its whole pose and lens).
_POSE = ("target", "distance", "yaw", "pitch", "up", "fov_deg", "aspect",
         "znear", "zfar", "perspective", "two_point")


def camera_right(camera: OrbitCamera) -> QVector3D:
    """The camera's own right on screen, as its view matrix has it."""
    level = camera._level_forward()
    forward = level if level is not None else camera.forward()
    up = QVector3D(0.0, 0.0, 1.0) if level is not None else camera.up_vector()
    r = QVector3D.crossProduct(forward, up)
    if r.lengthSquared() < 1e-18:
        return QVector3D(1.0, 0.0, 0.0)
    return r.normalized()


def convergence(camera: OrbitCamera) -> float:
    """The depth of the orbit target along the line of sight: the plane
    shown at screen depth."""
    if not camera.perspective:
        return camera.distance
    level = camera._level_forward()
    if level is not None:
        return max(QVector3D.dotProduct(camera.target - camera.eye(), level),
                   1e-9)
    return camera.distance


class EyeCamera(OrbitCamera):
    """One eye of the pair, built from the viewport's camera."""

    def __init__(self, base: OrbitCamera, offset: float,
                 zero_parallax: float | None = None) -> None:
        super().__init__()
        for name in _POSE:
            value = getattr(base, name)
            setattr(self, name, QVector3D(value) if isinstance(value, QVector3D)
                    else value)
        self.offset = float(offset)
        self.zero_parallax = float(zero_parallax if zero_parallax is not None
                                   else convergence(base))
        self.right = camera_right(base)
        if self.perspective:
            # Parallel axes: eye and target move together.
            self.target = self.target + self.right * self.offset

    def projection_matrix(self) -> QMatrix4x4:
        if not self.perspective:
            m = QMatrix4x4()
            half_h = self.distance * math.tan(math.radians(self.fov_deg) / 2.0)
            half_w = half_h * self.aspect
            far = self.far_plane()
            m.ortho(-half_w, half_w, -half_h, half_h, -far, far)
            k = self.offset / self.zero_parallax
            shear = QMatrix4x4(1.0, 0.0, -k, -self.offset,
                               0.0, 1.0, 0.0, 0.0,
                               0.0, 0.0, 1.0, 0.0,
                               0.0, 0.0, 0.0, 1.0)
            return m * shear
        near = self.near_plane()
        half_h = near * math.tan(math.radians(self.fov_deg) / 2.0)
        half_w = half_h * self.aspect
        shift_x = -self.offset * near / self.zero_parallax
        shift_y = 0.0
        level = self._level_forward()
        if level is not None:
            rel = self.target - self.eye()
            depth = QVector3D.dotProduct(rel, level)
            shift_y = rel.z() * near / depth
        m = QMatrix4x4()
        m.frustum(-half_w + shift_x, half_w + shift_x,
                  -half_h + shift_y, half_h + shift_y, near, self.far_plane())
        return m


def eye_pair(base: OrbitCamera, width: int, height: int,
             ratio: float = SEPARATION_RATIO):
    """The left and right eye cameras for a picture of ``width`` x
    ``height`` pixels, and the separation used (metres)."""
    c = convergence(base)
    separation = c * ratio
    eyes = []
    for sign in (-1.0, 1.0):
        eye = EyeCamera(base, sign * separation / 2.0, c)
        eye.set_aspect(width, height)
        eyes.append(eye)
    return eyes[0], eyes[1], separation


def predicted_disparity_px(base: OrbitCamera, point: QVector3D, width: int,
                           ratio: float = SEPARATION_RATIO) -> float:
    """Closed-form horizontal disparity (right eye minus left eye, in
    pixels of one eye ``width`` wide) of a world point, independent of the
    matrices above: positive behind the screen, negative in front of it."""
    c = convergence(base)
    e = c * ratio
    level = base._level_forward()
    forward = level if level is not None else base.forward()
    if not base.perspective:
        z = QVector3D.dotProduct(point - base.eye(), forward)
        half_w = (base.distance * math.tan(math.radians(base.fov_deg) / 2.0)
                  * base.aspect)
        world = e * (z - c) / c
        return world / (2.0 * half_w) * width
    z = QVector3D.dotProduct(point - base.eye(), forward)
    half_w = c * math.tan(math.radians(base.fov_deg) / 2.0) * base.aspect
    world = e * (1.0 - c / z)
    return world / (2.0 * half_w) * width
