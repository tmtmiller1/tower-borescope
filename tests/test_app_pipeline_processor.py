"""Tests for tower_borescope.app.pipeline.processor: image chain, filters and meters."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QColor

from synthetic import shifted, textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.pipeline.processor import FrameProcessor
from tower_borescope.app.pipeline.state import PipelineState

WIDTH = 320
HEIGHT = 240


def _processor(**changes):
    state = PipelineState()
    for name, value in changes.items():
        setattr(state, name, value)
    return FrameProcessor(state)


def test_default_settings_pass_the_frame_through():
    frame = textured_frame(WIDTH, HEIGHT)
    assert _processor().process_static(frame) is frame


def test_rotation_and_mirror_orient_the_frame():
    frame = textured_frame(WIDTH, HEIGHT)
    rotated = _processor(rotation=1).process_static(frame)
    assert rotated.shape == (WIDTH, HEIGHT, 3)
    mirrored = _processor(mirror=True).process_static(frame)
    assert np.array_equal(mirrored, frame[:, ::-1])


def test_filters_change_the_picture():
    frame = textured_frame(WIDTH, HEIGHT)
    for changes in ({"enhanced": True}, {"glare": 0.8}, {"view_mode": "Inverted"}):
        processed = _processor(**changes).process_static(frame)
        assert processed.shape == frame.shape
        assert not np.array_equal(processed, frame), changes
    gray = _processor(view_mode="Grayscale").process_static(frame)
    assert np.array_equal(gray[..., 0], gray[..., 2])


def test_state_changes_apply_to_the_next_frame():
    processor = _processor()
    frame = textured_frame(WIDTH, HEIGHT)
    processor.state.rotation = 2
    assert np.array_equal(processor.process_static(frame), frame[::-1, ::-1])


def test_live_filters_run_and_reset():
    processor = _processor(stabilize=True, denoise=0.7)
    base = textured_frame(WIDTH, HEIGHT)
    outputs = [processor.process_live(shifted(base, dx, 0.0)) for dx in (0, 1, 2, 3)]
    assert all(output.shape == base.shape for output in outputs)
    processor.reset_stabilizer()
    processor.reset_denoiser()
    processor.reset_filters()
    first = processor.process_live(base)
    assert first.shape == base.shape


def test_finish_stack_keeps_size_and_orients():
    stacked = textured_frame(WIDTH * 2, HEIGHT * 2)
    still = _processor(rotation=1, glare=0.5).finish_stack(stacked)
    assert still.shape == (WIDTH * 2, HEIGHT * 2, 3)


def test_frame_info_with_meters():
    processor = _processor()
    frame = textured_frame(WIDTH, HEIGHT)
    info = processor.frame_info(frame, frame, 1.5)
    assert isinstance(info, FrameInfo)
    assert (info.image.width(), info.image.height()) == (WIDTH, HEIGHT)
    assert info.focus_raw > 0
    assert 0.0 < info.focus <= 1.0
    assert info.hist.shape == (64,)
    assert 0.0 <= info.clipped <= 1.0
    assert info.motion == 1.5


def test_frame_info_without_meters_keeps_the_focus_score():
    processor = _processor(meters=False)
    frame = textured_frame(WIDTH, HEIGHT)
    info = processor.frame_info(frame, frame, 0.0)
    assert info.focus is None and info.hist is None and info.clipped == 0.0
    assert info.focus_raw > 0


def test_zebra_marks_only_the_display_image():
    processor = _processor(zebra=True)
    frame = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)
    info = processor.frame_info(frame, frame, 0.0)
    colors = {QColor(info.image.pixel(x, 10)).name() for x in range(12)}
    assert len(colors) == 2
    assert np.all(frame == 255)
