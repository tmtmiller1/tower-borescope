"""Tests for tower_borescope.imaging.stacking: alignment, upscaling and failure."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from synthetic import shifted, textured_frame
from tower_borescope.errors import BorescopeError
from tower_borescope.imaging.stacking import STACK_FRAMES, stack_frames

OFFSETS = [(0.0, 0.0), (1.4, -0.6), (-2.2, 1.1), (0.7, 2.5), (3.1, -1.8), (-1.0, -2.4)]


def test_stack_frames_count_is_sixteen():
    assert STACK_FRAMES == 16


def test_stacking_aligns_shifted_frames_and_upscales_2x():
    base = textured_frame(320, 240, seed=3)
    frames = [shifted(base, dx, dy) for dx, dy in OFFSETS]
    still, used = stack_frames(frames)
    assert used == len(OFFSETS)
    assert still.shape == (480, 640, 3)
    assert still.dtype == np.uint8
    reference = frames[len(frames) // 2]
    restored = cv2.resize(still, (320, 240), interpolation=cv2.INTER_AREA)
    inner = (slice(20, 220), slice(20, 300))
    error = np.abs(restored[inner].astype(np.int16) - reference[inner]).mean()
    assert error < 6


def test_scale_three_gives_a_three_times_larger_still():
    base = textured_frame(160, 120, seed=4)
    still, used = stack_frames([base, shifted(base, 0.5, 0.5)], scale=3)
    assert still.shape == (360, 480, 3)
    assert used == 2


def test_unrelated_frame_is_skipped():
    base = textured_frame(320, 240, seed=5)
    frames = [shifted(base, dx, dy) for dx, dy in OFFSETS[:3]]
    frames.append(textured_frame(320, 240, seed=99))
    _, used = stack_frames(frames)
    assert used == 3


def test_nothing_to_align_raises():
    with pytest.raises(BorescopeError):
        stack_frames([])
    flat = np.full((120, 160, 3), 90, np.uint8)
    with pytest.raises(BorescopeError):
        stack_frames([flat, flat.copy()])
