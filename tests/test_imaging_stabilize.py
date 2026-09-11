"""Tests for tower_borescope.imaging.stabilize: shake removal and timing."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import cv2
import numpy as np

from synthetic import shifted, textured_frame
from tower_borescope.imaging.geometry import ANALYSIS_WIDTH, small_gray
from tower_borescope.imaging.stabilize import Stabilizer


def test_stabilizer_cancels_synthetic_shake():
    base = textured_frame()
    stabilizer = Stabilizer()
    height, width = base.shape[:2]
    margin_x, margin_y = (
        int(width * stabilizer.crop / 2),
        int(height * stabilizer.crop / 2),
    )
    cropped = base[margin_y : height - margin_y, margin_x : width - margin_x]
    reference = small_gray(cv2.resize(cropped, (width, height)))
    window = cv2.createHanningWindow(reference.shape[::-1], cv2.CV_32F)
    rng = np.random.default_rng(1)
    to_frame = width / ANALYSIS_WIDTH
    raw_positions, steady_positions = [], []
    for _ in range(40):
        jitter = rng.normal(0, 6, 2)
        steadied = stabilizer.apply(shifted(base, float(jitter[0]), float(jitter[1])))
        (dx, dy), _ = cv2.phaseCorrelate(reference, small_gray(steadied), window)
        raw_positions.append(jitter)
        steady_positions.append((dx * to_frame, dy * to_frame))
    raw_std = np.std(raw_positions[3:], axis=0).mean()
    steady_std = np.std(steady_positions[3:], axis=0).mean()
    assert steady_std < 0.3 * raw_std


def test_output_keeps_the_frame_size_and_reset_clears_the_path():
    base = textured_frame(640, 480)
    stabilizer = Stabilizer()
    for offset in range(5):
        steadied = stabilizer.apply(shifted(base, 3.0 * offset, 0.0))
        assert steadied.shape == base.shape
    stabilizer.reset()
    first = stabilizer.apply(base)
    assert first.shape == base.shape


def test_stabilizer_fits_the_frame_budget():
    base = textured_frame()
    frames = [shifted(base, float(k % 5), float(k % 3)) for k in range(12)]
    stabilizer = Stabilizer()
    stabilizer.apply(frames[0])
    samples = []
    for frame in frames * 2:
        start = perf_counter()
        stabilizer.apply(frame)
        samples.append((perf_counter() - start) * 1000)
    assert median(samples) < 50
