"""Tests for tower_borescope.measure.calibration: storage formats and focus lock."""

from __future__ import annotations

from tower_borescope.measure.calibration import FOCUS_TOLERANCE, Calibration


def test_legacy_bare_number_format_loads():
    calibration = Calibration({"720p": 0.05})
    assert calibration.mm_per_px("720p") == 0.05
    assert calibration.source("720p") == "measured"
    assert calibration.focus_ok("720p", 3.0) is None


def test_set_from_and_focus_lock():
    calibration = Calibration({"720p": 0.05})
    calibration.set_from("720p", 400, 20, focus=3.0, source="ai")
    assert calibration.source("720p") == "ai"
    assert calibration.focus_ok("720p", 3.2) is True
    assert calibration.focus_ok("720p", 1.0) is False
    assert calibration.focus_ok("720p", None) is None
    assert FOCUS_TOLERANCE == Calibration.FOCUS_TOLERANCE == 0.35


def test_round_trip_through_to_dict():
    calibration = Calibration()
    calibration.set_from("720p", 400, 20, focus=3.0, source="ai")
    saved = calibration.to_dict()
    assert saved == {"720p": {"mm_per_px": 0.05, "focus": 3.0, "source": "ai"}}
    restored = Calibration(saved)
    assert restored.mm_per_px("720p") == 0.05
    assert restored.to_dict() == saved
    saved["720p"]["mm_per_px"] = 9.0
    assert calibration.mm_per_px("720p") == 0.05


def test_uncalibrated_and_invalid_inputs():
    calibration = Calibration({"480p": "not a number", "240p": {"focus": 2.0}})
    assert calibration.entries == {}
    assert calibration.mm_per_px("720p") is None
    assert calibration.source("720p") is None
    calibration.set_from("720p", 0, 20)
    calibration.set_from("720p", 100, -1)
    assert calibration.mm_per_px("720p") is None
