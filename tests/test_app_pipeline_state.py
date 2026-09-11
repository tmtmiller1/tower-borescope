"""Tests for tower_borescope.app.pipeline.state: settings parsing and capture metadata."""

from __future__ import annotations

from tower_borescope.app.pipeline import state as state_module
from tower_borescope.app.pipeline.state import (
    AUTO_STACK_STILL_SECONDS,
    BURST_FRAMES,
    MOTION_COOLDOWN_SECONDS,
    PREROLL_SECONDS,
    PipelineState,
)
from tower_borescope.device.constants import DEFAULT_MODE


def test_timing_constants_match_the_original_application():
    assert PREROLL_SECONDS == 10
    assert BURST_FRAMES == 10
    assert AUTO_STACK_STILL_SECONDS == 1.2
    assert MOTION_COOLDOWN_SECONDS == 3.0
    assert state_module.NORMAL_VIEW == "Normal"


def test_empty_settings_give_defaults():
    state = PipelineState.from_settings({})
    assert state.mode == DEFAULT_MODE
    assert state.grade.is_default()
    assert (state.enhanced, state.rotation, state.mirror) == (False, 0, False)
    assert (state.raw_recording, state.preroll_enabled, state.audio_device) == (
        False,
        True,
        None,
    )
    assert (state.stabilize, state.denoise, state.glare) == (False, 0.0, 0.0)
    assert (state.view_mode, state.zebra, state.meters) == ("Normal", False, True)
    assert (state.auto_stack, state.motion_trigger) == (False, False)
    assert (state.timelapse_interval, state.want_vcam) == (0.0, False)
    assert state.calibration.entries == {}


def test_saved_settings_are_applied():
    settings = {
        "mode": "480p",
        "brightness": 12,
        "awb": True,
        "enhance": True,
        "rotation": 5,
        "mirror": True,
        "raw": True,
        "preroll": False,
        "audio_device": 2,
        "stabilize": True,
        "denoise": 0.6,
        "glare": 0.4,
        "view_mode": "Edges",
        "zebra": True,
        "meters": False,
        "calibration": {"480p": {"mm_per_px": 0.05, "focus": 100.0}},
    }
    state = PipelineState.from_settings(settings)
    flags = (state.enhanced, state.mirror, state.raw_recording, state.preroll_enabled)
    assert flags == (True, True, True, False)
    assert (state.stabilize, state.zebra, state.meters) == (True, True, False)
    assert (state.mode, state.rotation, state.audio_device) == ("480p", 1, 2)
    assert (state.grade.brightness, state.grade.awb) == (12, True)
    assert (state.denoise, state.glare, state.view_mode) == (0.6, 0.4, "Edges")
    assert state.calibration.mm_per_px("480p") == 0.05


def test_unusable_values_fall_back():
    settings = {
        "mode": "999p",
        "rotation": "sideways",
        "denoise": None,
        "glare": "bright",
        "audio_device": "2",
        "calibration": [1, 2],
    }
    state = PipelineState.from_settings(settings)
    assert state.mode == DEFAULT_MODE
    assert state.rotation == 0
    assert (state.denoise, state.glare) == (0.0, 0.0)
    assert state.audio_device is None
    assert state.calibration.entries == {}
    assert PipelineState.from_settings({"audio_device": True}).audio_device is None


def test_capture_metadata_records_the_settings():
    state = PipelineState.from_settings({"mode": "720p", "enhance": True, "glare": 0.3})
    state.calibration.set_from("720p", 400.0, 20.0)
    meta = state.capture_metadata()
    assert meta["camera"] == "1280x720"
    assert meta["mode"] == "720p"
    assert meta["enhance"] is True
    assert meta["glare"] == 0.3
    assert meta["mm_per_px"] == 0.05
    for key in ("brightness", "contrast", "saturation", "awb", "stabilize", "denoise"):
        assert key in meta
    for key in ("view_mode", "rotation", "mirror"):
        assert key in meta


def test_capture_metadata_follows_the_mode():
    state = PipelineState()
    state.mode = "240p"
    meta = state.capture_metadata()
    assert meta["camera"] == "320x240"
    assert meta["mm_per_px"] is None
