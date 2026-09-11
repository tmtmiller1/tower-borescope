"""Tests for tower_borescope.imaging.geometry: zoom, orientation and analysis copies."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import numpy as np
import pytest

from synthetic import textured_frame
from tower_borescope.imaging.geometry import (
    ANALYSIS_WIDTH,
    ZOOM_STEPS,
    orient,
    small_gray,
    zoom,
)


def _median_ms(action, runs=20):
    action()
    samples = []
    for _ in range(runs):
        start = perf_counter()
        action()
        samples.append((perf_counter() - start) * 1000)
    return median(samples)


def test_zoom_steps_start_at_one_and_increase():
    assert ZOOM_STEPS[0] == 1.0
    assert list(ZOOM_STEPS) == sorted(ZOOM_STEPS)


def test_zoom_keeps_the_frame_size():
    frame = textured_frame()
    assert zoom(frame, 1.0) is frame
    assert zoom(frame, 0.5) is frame
    for factor in ZOOM_STEPS[1:]:
        assert zoom(frame, factor).shape == frame.shape


def test_zoom_magnifies_the_centre():
    frame = np.zeros((100, 100, 3), np.uint8)
    frame[40:60, 40:60] = 255
    zoomed = zoom(frame, 2.0)
    # The 20 px square doubles to 40 px, spanning rows and columns 30 to 70.
    assert zoomed[33:67, 33:67].mean() > 240
    assert zoomed[:25, :25].max() == 0


@pytest.mark.parametrize(
    ("rotation", "mirror", "shape"),
    [
        (0, False, (720, 1280, 3)),
        (1, False, (1280, 720, 3)),
        (2, True, (720, 1280, 3)),
        (3, True, (1280, 720, 3)),
        (5, False, (1280, 720, 3)),
    ],
)
def test_orient_shapes(rotation, mirror, shape):
    assert orient(textured_frame(), rotation, mirror).shape == shape


def test_orient_content():
    frame = textured_frame(160, 120)
    assert orient(frame, 0, False) is frame
    assert np.array_equal(orient(frame, 0, True), frame[:, ::-1])
    assert np.array_equal(orient(frame, 2, False), frame[::-1, ::-1])
    assert np.array_equal(orient(frame, 1, False), np.rot90(frame, k=-1))


def test_small_gray_is_float_at_analysis_width():
    gray = small_gray(textured_frame())
    assert gray.shape == (ANALYSIS_WIDTH * 720 // 1280, ANALYSIS_WIDTH)
    assert gray.dtype == np.float32


@pytest.mark.timing
def test_geometry_fits_the_frame_budget():
    frame = textured_frame()
    assert _median_ms(lambda: zoom(frame, 2.0)) < 50
    assert _median_ms(lambda: orient(frame, 1, True)) < 50
    assert _median_ms(lambda: small_gray(frame)) < 50
