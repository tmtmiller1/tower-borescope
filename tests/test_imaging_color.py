"""Tests for tower_borescope.imaging.color: grading math, settings and timing."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import cv2
import numpy as np

from synthetic import textured_frame
from tower_borescope.imaging.color import COLOR_DEFAULTS, ColorGrade

FULL_GRADE = {"brightness": 24, "contrast": 1.3, "saturation": 1.4, "awb": True}


def _median_ms(action, runs=30):
    action()
    samples = []
    for _ in range(runs):
        start = perf_counter()
        action()
        samples.append((perf_counter() - start) * 1000)
    return median(samples)


def test_default_grade_is_a_bit_exact_no_op():
    frame = textured_frame()
    grade = ColorGrade()
    assert grade.is_default()
    assert grade.describe() == ""
    assert grade.to_dict() == dict(COLOR_DEFAULTS)
    assert np.array_equal(grade.apply(frame), frame)


def test_full_grade_keeps_shape_and_fits_the_20_ms_budget():
    frame = textured_frame()
    grade = ColorGrade.from_settings(FULL_GRADE)
    for _ in range(20):
        graded = grade.apply(frame)
    assert graded.shape == frame.shape
    assert graded.dtype == np.uint8
    assert _median_ms(lambda: grade.apply(frame), runs=50) < 20


def test_white_balance_converges_channel_means():
    tinted = textured_frame().astype(np.float32) * np.array([0.7, 1.0, 1.3])
    frame = np.clip(tinted, 0, 255).astype(np.uint8)
    awb = ColorGrade(awb=True)
    balanced = awb.apply(frame)
    for _ in range(39):
        balanced = awb.apply(frame)
    means_in = cv2.mean(frame)[:3]
    means_out = cv2.mean(balanced)[:3]
    assert max(means_out) - min(means_out) < (max(means_in) - min(means_in)) * 0.5 + 1


def test_contrast_pivots_on_mid_grey():
    flat = np.full((8, 8, 3), 128, np.uint8)
    assert abs(int(ColorGrade(contrast=1.8).apply(flat)[0, 0, 0]) - 128) <= 1


def test_brightness_and_saturation_change_the_frame():
    frame = textured_frame(160, 120)
    brighter = ColorGrade(brightness=20).apply(frame)
    assert brighter.mean() > frame.mean() + 15
    desaturated = ColorGrade(saturation=0.0).apply(frame)
    channels = desaturated.astype(np.int16)
    assert np.abs(channels[..., 0] - channels[..., 2]).max() <= 1


def test_settings_round_trip_and_describe():
    grade = ColorGrade.from_settings({**FULL_GRADE, "enhance": True, "rotation": 1})
    assert grade.to_dict() == FULL_GRADE
    assert ColorGrade.from_settings(grade.to_dict()).to_dict() == grade.to_dict()
    assert grade.describe() == "AWB  bright +24  contrast 1.3  sat 1.4"
    assert not grade.is_default()


def test_unusable_settings_fall_back_to_defaults():
    grade = ColorGrade.from_settings({"brightness": "bright", "contrast": None})
    assert grade.is_default()


def test_reset_restores_defaults():
    grade = ColorGrade.from_settings(FULL_GRADE)
    grade.apply(textured_frame(160, 120))
    grade.reset()
    assert grade.is_default()
