"""Tests for tower_borescope.app.window.measure_controller: the AI scale estimate,
calibration from a clicked length, units, tool selection and the focus lock status."""

from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from conftest import wait_until
from fakes import SAMPLE_SCALE, FakeBackend
from tower_borescope.app.window.measure_controller import (
    FOCUS_OFF_TEXT,
    FOCUS_OK_TEXT,
    FOCUS_UNKNOWN_TEXT,
    calibration_text,
    focus_text,
)
from tower_borescope.measure.calibration import Calibration
from tower_borescope.measure.shapes import Annotation, Measurement


class NothingInView(FakeBackend):
    def scale(self, jpeg, prompt):
        return SAMPLE_SCALE.model_copy(
            update={"found": False, "span": None, "reasoning": "Only a blank wall."}
        )


@pytest.fixture
def window(window):
    window.ai.backend = FakeBackend()
    return window


def toasts(win):
    return win.view.toasts.visible(time.monotonic())


def test_ai_scale_estimate_is_applied_when_confirmed(window, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes
    )
    state = window.pipeline.state
    window.measure.scale.estimate()
    assert wait_until(lambda: state.calibration.source(state.mode) == "ai")
    expected = 15.875 / (0.4 * window.view.image.width())
    assert abs(state.calibration.mm_per_px(state.mode) - expected) < 1e-6
    assert window.view.mm_per_px == state.calibration.mm_per_px(state.mode)
    assert window.measure.group.scale_ai_btn.text() == "Estimate scale with AI"
    assert window.view.ai_boxes == []
    assert "estimated by AI" in window.measure.group.calibration_label.text()
    assert "720p" in window.ctx.prefs.values["calibration"]


def test_declined_estimate_keeps_the_view_uncalibrated(window, monkeypatch):
    asked = []

    def decline(*args):
        asked.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    window.measure.scale.estimate()
    assert wait_until(lambda: bool(asked))
    assert "Reference: 1/2 in copper pipe (5/8 in OD)" in asked[0]
    assert window.view.mm_per_px is None
    assert window.measure.group.scale_ai_btn.isEnabled()


def test_estimate_without_a_reference_explains_why(window, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[2]))
    window.ai.backend = NothingInView()
    window.measure.scale.estimate()
    assert wait_until(lambda: bool(shown))
    assert shown[0].endswith("Only a blank wall.")
    assert "AI found nothing of known size in this view" in toasts(window)


def test_calibration_from_a_clicked_length_in_inches(window, monkeypatch):
    answers = [(1.0, True), (5.0, False)]
    monkeypatch.setattr(QInputDialog, "getDouble", lambda *args: answers.pop(0))
    window.measure.group.unit_combo.setCurrentIndex(2)
    assert window.ctx.prefs.values["unit"] == "in"
    window.freeze.set_frozen(True)
    window.measure.calibrate_finish(254.0)
    assert window.view.mm_per_px == pytest.approx(0.1)
    label = window.measure.group.calibration_label.text()
    assert label.startswith("Scale calibrated for 1280x720")
    window.measure.calibrate_finish(10.0)
    assert window.view.mm_per_px == pytest.approx(0.1)


def test_calibrate_start_picks_the_tool_on_the_tools_tab(window):
    window.measure.calibrate_start()
    assert window.view.tool == "calibrate"
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Tools"


def test_new_tool_replaces_items_of_its_kind_unless_kept(window):
    overlays = window.view.overlays
    overlays.finish_item(Measurement("distance", [(1.0, 1.0), (9.0, 1.0)]))
    window.measure.set_tool("angle")
    assert overlays.measurements == []
    assert window.measure.group.tool_buttons["angle"].isChecked()
    overlays.finish_item(Annotation("arrow", [(1.0, 1.0), (5.0, 5.0)]))
    window.measure.group.keep_check.setChecked(True)
    window.measure.toggle_tool("arrow")
    assert len(overlays.annotations) == 1
    window.measure.toggle_tool("arrow")
    assert window.view.tool is None


def test_uncalibrated_distance_tool_warns(window):
    window.measure.set_tool("distance")
    assert "Not calibrated: values are in pixels (Tools > Calibrate Scale)" in toasts(
        window
    )


def test_focus_lock_status_follows_the_frozen_frame(window):
    state = window.pipeline.state
    window.freeze.set_frozen(True)
    state.calibration.set_from(state.mode, 100.0, 10.0, focus=50.0)
    window.view.focus_raw = 52.0
    window.measure.update_scale_state()
    assert window.measure.group.scale_state.text() == FOCUS_OK_TEXT
    assert window.view.scale_ok is True
    window.view.focus_raw = 5.0
    window.measure.update_scale_state()
    assert window.measure.group.scale_state.text().startswith("Check:")


def test_status_texts():
    assert focus_text(False, True) == ""
    assert focus_text(True, None) == FOCUS_UNKNOWN_TEXT
    assert focus_text(True, False) == FOCUS_OFF_TEXT
    calibration = Calibration()
    assert calibration_text(calibration, "480p", "mm").startswith("No scale for 640x480")
    calibration.set_from("480p", 64.0, 6.4)
    assert "field of view about 64.00 mm x 48.00 mm" in calibration_text(
        calibration, "480p", "mm"
    )


def test_mode_change_uses_the_scale_of_that_resolution(window):
    window.pipeline.state.calibration.set_from("480p", 100.0, 20.0)
    window.view.overlays.finish_item(Annotation("text", [(3.0, 3.0)], "note"))
    window.measure.mode_changed("480p")
    assert window.view.mm_per_px == pytest.approx(0.2)
    assert window.view.overlays.annotations == []
    assert "for 640x480" in window.measure.group.calibration_label.text()
