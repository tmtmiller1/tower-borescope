"""Tests for tower_borescope.imaging.meters: focus, histogram, clipping, zebra, motion."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import cv2
import numpy as np
import pytest

from synthetic import shifted, textured_frame
from tower_borescope.imaging.meters import (
    FocusMeter,
    MotionDetector,
    clipped_fraction,
    focus_score,
    histogram,
    zebra,
)


def _median_ms(action, runs=20):
    action()
    samples = []
    for _ in range(runs):
        start = perf_counter()
        action()
        samples.append((perf_counter() - start) * 1000)
    return median(samples)


def _half_white(width=320, height=240):
    frame = np.full((height, width, 3), 60, np.uint8)
    frame[:, width // 2 :] = 255
    return frame


def test_sharp_focus_score_is_more_than_twice_a_blurred_one():
    frame = textured_frame()
    sharp = focus_score(frame)
    blurred = focus_score(cv2.GaussianBlur(frame, (0, 0), 2))
    assert sharp > blurred * 2


def test_focus_meter_reads_against_the_decaying_peak():
    meter = FocusMeter()
    assert meter.update(10.0) == 1.0
    assert meter.peak == 10.0
    assert meter.update(5.0) == pytest.approx(5.0 / 9.95)
    assert meter.update(20.0) == 1.0


def test_histogram_is_normalised_to_the_tallest_bin():
    hist = histogram(textured_frame(320, 240))
    assert hist.shape == (64,)
    assert hist.max() == pytest.approx(1.0)
    white = histogram(np.full((10, 10, 3), 255, np.uint8), bins=16)
    assert white[-1] == 1.0
    assert white[:-1].sum() == 0


def test_clipped_fraction_counts_pixels_at_threshold():
    assert clipped_fraction(_half_white()) == pytest.approx(0.5)
    assert clipped_fraction(_half_white(), threshold=50) == 1.0


def test_zebra_stripes_only_clipped_highlights():
    frame = _half_white()
    striped = zebra(frame)
    assert np.array_equal(frame, _half_white())
    changed = np.any(striped != frame, axis=2)
    assert not changed[:, :160].any()
    assert 0.4 < changed[:, 160:].mean() < 0.6
    assert tuple(striped[changed][0]) == (40, 40, 220)
    dark = np.full((240, 320, 3), 60, np.uint8)
    assert zebra(dark) is dark


def test_motion_detector_tracks_still_time():
    frame = textured_frame(640, 360)
    detector = MotionDetector()
    assert detector.threshold == 2.5
    for now in (0.0, 1.0, 2.0):
        assert detector.update(frame, now) == 0.0
    assert detector.still_seconds(2.5) == 2.5
    moved = shifted(frame, 60.0, 40.0)
    assert detector.update(moved, 3.0) > detector.threshold
    assert detector.still_seconds(3.0) == 0.0
    detector.update(moved, 4.0)
    assert detector.level == 0.0
    assert detector.still_seconds(6.0) == 2.0


@pytest.mark.timing
def test_meters_fit_the_frame_budget():
    frame = textured_frame()
    detector = MotionDetector()
    assert _median_ms(lambda: focus_score(frame)) < 50
    assert _median_ms(lambda: histogram(frame)) < 50
    assert _median_ms(lambda: clipped_fraction(frame)) < 50
    assert _median_ms(lambda: zebra(frame, 200)) < 50
    assert _median_ms(lambda: detector.update(frame, perf_counter())) < 50
