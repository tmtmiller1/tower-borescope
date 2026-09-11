"""Tests for tower_borescope.imaging.enhance: sharpening, enhance and still finishing."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import cv2
import numpy as np

from synthetic import textured_frame
from tower_borescope.imaging.enhance import enhance, finish_still, unsharp


def _median_ms(action, runs=20):
    action()
    samples = []
    for _ in range(runs):
        start = perf_counter()
        action()
        samples.append((perf_counter() - start) * 1000)
    return median(samples)


def _sharpness(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def test_unsharp_increases_sharpness():
    frame = cv2.GaussianBlur(textured_frame(320, 240), (0, 0), 1.0)
    assert _sharpness(unsharp(frame)) > _sharpness(frame) * 1.2


def test_unsharp_with_zero_amount_is_unchanged():
    frame = textured_frame(160, 120)
    assert np.array_equal(unsharp(frame, 0.0), frame)


def test_enhance_keeps_shape_and_fits_the_frame_budget():
    frame = textured_frame()
    enhanced = enhance(frame)
    assert enhanced.shape == frame.shape
    assert enhanced.dtype == np.uint8
    assert not np.array_equal(enhanced, frame)
    assert _median_ms(lambda: enhance(frame)) < 50


def test_finish_still_uses_enhance_or_a_stronger_unsharp():
    still = textured_frame(320, 240)
    assert np.array_equal(finish_still(still, True), enhance(still))
    assert np.array_equal(finish_still(still, False), unsharp(still, 0.8, 1.5))
