# SPDX-License-Identifier: GPL-3.0-or-later
"""The eye cameras against a closed-form prediction.

Run from IngeTrazo's folder (its ``core`` on the path) with this
repository's folder on ``PYTHONPATH``::

    INGETRAZO=/path/to/ingetrazo python3 -m pytest tests

Each case projects a few thousand points with the two eye cameras' own
matrices and compares their horizontal disparity with
``predicted_disparity_px`` (pinhole and shear geometry, no matrices); the
vertical disparity must be zero and the orbit target at screen depth.
"""
import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.environ.get("INGETRAZO", "."))

from PySide6.QtGui import QVector3D, QVector4D  # noqa: E402

from core.camera import OrbitCamera  # noqa: E402
from stereo_view.cameras import (EyeCamera, convergence, eye_pair,  # noqa: E402
                                 predicted_disparity_px)

W, H = 1920, 1080
#: QMatrix4x4 computes in float32: a thousandth of a pixel is its noise here.
TOL = 1e-3


def project(cam, p):
    clip = (cam.projection_matrix() * cam.view_matrix()).map(
        QVector4D(p.x(), p.y(), p.z(), 1.0))
    if clip.w() <= 1e-12:
        return None
    return ((clip.x() / clip.w() * 0.5 + 0.5) * W,
            (1.0 - (clip.y() / clip.w() * 0.5 + 0.5)) * H)


def base_camera(mode, yaw, pitch, distance=20.0):
    cam = OrbitCamera()
    cam.target = QVector3D(3.0, -2.0, 1.5)
    cam.distance = distance
    cam.yaw, cam.pitch = math.radians(yaw), math.radians(pitch)
    cam.set_projection(mode)
    cam.set_aspect(W, H)
    return cam


def sight(cam):
    level = cam._level_forward()
    return level if level is not None else cam.forward()


def visible_points(cam, n, rng):
    """Points inside the mono view between 0.3 and 3 times the target's
    depth (in front of the near plane, inside the frame)."""
    # Around the line through the target (the middle of the frame in every
    # projection, two-point included), at depths along the line of sight.
    s = sight(cam)
    to_target = (cam.target - cam.eye()).normalized()
    r = QVector3D.crossProduct(cam.forward(), cam.up_vector()).normalized()
    u = QVector3D.crossProduct(r, to_target).normalized()
    c = convergence(cam)
    out = []
    tries = 0
    while len(out) < n:
        tries += 1
        assert tries < 50 * n, "the generator finds no visible points"
        z = c * rng.uniform(0.3, 3.0)
        along = z / max(QVector3D.dotProduct(to_target, s), 1e-9)
        span = 0.35 * (z if cam.perspective else c)
        p = cam.eye() + to_target * along + r * (rng.uniform(-1, 1) * span * cam.aspect) \
            + u * (rng.uniform(-1, 1) * span)
        q = project(cam, p)
        if q is not None and 0 <= q[0] <= W and 0 <= q[1] <= H:
            out.append(p)
    return out


CASES = [(mode, yaw, pitch)
         for mode in ("perspective", "two_point", "parallel")
         for yaw, pitch in ((-45, 30), (10, 5), (120, -20), (-90, 60))]


@pytest.mark.parametrize("mode,yaw,pitch", CASES)
def test_disparity_matches_prediction(mode, yaw, pitch):
    rng = random.Random(296)
    cam = base_camera(mode, yaw, pitch)
    left, right, sep = eye_pair(cam, W, H)
    assert sep == pytest.approx(convergence(cam) / 30.0)
    worst_h = worst_v = 0.0
    near_crossed = far_uncrossed = 0
    for p in visible_points(cam, 3000, rng):
        a, b = project(left, p), project(right, p)
        measured = b[0] - a[0]
        predicted = predicted_disparity_px(cam, p, W)
        worst_h = max(worst_h, abs(measured - predicted))
        worst_v = max(worst_v, abs(b[1] - a[1]))
        depth = QVector3D.dotProduct(p - cam.eye(), sight(cam))
        if depth < convergence(cam) * 0.99:
            near_crossed += measured < 0
        elif depth > convergence(cam) * 1.01:
            far_uncrossed += measured > 0
    assert worst_h < TOL
    assert worst_v < TOL
    assert near_crossed > 100 and far_uncrossed > 100


@pytest.mark.parametrize("mode", ["perspective", "two_point", "parallel"])
def test_target_at_screen_depth(mode):
    cam = base_camera(mode, -45, 30)
    left, right, _ = eye_pair(cam, W, H)
    a, b = project(left, cam.target), project(right, cam.target)
    assert abs(a[0] - b[0]) < TOL and abs(a[1] - b[1]) < TOL
    mono = project(cam, cam.target)
    assert abs(a[0] - mono[0]) < TOL and abs(a[1] - mono[1]) < TOL


@pytest.mark.parametrize("mode", ["perspective", "two_point", "parallel"])
def test_zero_offset_is_the_viewport(mode):
    cam = base_camera(mode, 30, 20)
    eye = EyeCamera(cam, 0.0)
    a = (eye.projection_matrix() * eye.view_matrix()).data()
    b = (cam.projection_matrix() * cam.view_matrix()).data()
    assert max(abs(x - y) for x, y in zip(a, b)) < 1e-6


def test_parallel_axes_and_eye_positions():
    cam = base_camera("perspective", -45, 30)
    left, right, sep = eye_pair(cam, W, H)
    assert (right.eye() - left.eye()).length() == pytest.approx(sep, rel=1e-5)
    assert QVector3D.dotProduct(left.forward(), right.forward()) == pytest.approx(1.0, abs=1e-6)
    assert QVector3D.dotProduct(right.eye() - left.eye(), cam.forward()) == pytest.approx(0.0, abs=1e-5)


def test_top_view_has_no_vertical_disparity():
    cam = base_camera("perspective", 0, 0)
    cam.set_view("top")
    left, right, _ = eye_pair(cam, W, H)
    rng = random.Random(7)
    for p in visible_points(cam, 500, rng):
        a, b = project(left, p), project(right, p)
        assert abs(a[1] - b[1]) < TOL
        assert abs((b[0] - a[0]) - predicted_disparity_px(cam, p, W)) < TOL


def test_the_mono_camera_is_left_alone():
    cam = base_camera("perspective", -45, 30)
    before = (cam.projection_matrix() * cam.view_matrix()).data()
    eye_pair(cam, W, H)
    after = (cam.projection_matrix() * cam.view_matrix()).data()
    assert before == after
