"""Tests for tower_borescope.imaging.view_modes: glare curve, looks and timing."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import numpy as np
import pytest

from synthetic import textured_frame
from tower_borescope.imaging.view_modes import (
    VIEW_MODES,
    apply_view_mode,
    glare_reduce,
    outline,
)


def _median_ms(action, runs=20):
    action()
    samples = []
    for _ in range(runs):
        start = perf_counter()
        action()
        samples.append((perf_counter() - start) * 1000)
    return median(samples)


def _ramp():
    levels = np.arange(256, dtype=np.uint8).reshape(1, 256, 1)
    return np.repeat(levels, 3, axis=2)


def test_glare_curve_is_monotonic_identity_below_knee_and_compresses_white():
    curve = glare_reduce(_ramp(), 0.6)[0, :, 0].astype(int)
    assert all(curve[level] <= curve[level + 1] for level in range(255))
    assert np.array_equal(curve[:171], np.arange(171))
    assert curve[100] == 100
    assert curve[255] < 230


def test_glare_amount_zero_returns_the_frame():
    frame = textured_frame(160, 120)
    assert glare_reduce(frame, 0) is frame
    assert glare_reduce(frame, 0.001) is frame


def test_view_mode_names():
    assert VIEW_MODES == ("Normal", "Grayscale", "Inverted", "Edges", "Outline")


def test_normal_and_unknown_modes_return_the_frame():
    frame = textured_frame(160, 120)
    assert apply_view_mode(frame, "Normal") is frame
    assert apply_view_mode(frame, "Sepia") is frame


def test_each_mode_renders_a_frame_of_the_same_shape():
    frame = textured_frame(320, 240)
    gray = apply_view_mode(frame, "Grayscale")
    assert np.array_equal(gray[..., 0], gray[..., 2])
    assert np.array_equal(apply_view_mode(frame, "Inverted"), 255 - frame)
    for mode in ("Edges", "Outline"):
        rendered = apply_view_mode(frame, mode)
        assert rendered.shape == frame.shape
        assert rendered.dtype == np.uint8
        assert not np.array_equal(rendered, frame)
    assert np.array_equal(outline(frame), apply_view_mode(frame, "Outline"))


@pytest.mark.parametrize("mode", VIEW_MODES)
def test_view_modes_fit_the_frame_budget(mode):
    frame = textured_frame()
    assert _median_ms(lambda: apply_view_mode(frame, mode)) < 50


def test_glare_reduce_fits_the_frame_budget():
    frame = textured_frame()
    assert _median_ms(lambda: glare_reduce(frame, 0.6)) < 50
