"""Tests for tower_borescope.app.window.capture_controller: scope button gestures, the
recording and time-lapse controls, capture switches, microphone choice, folders and the
recent captures strip."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PySide6.QtGui import QDesktopServices

from conftest import wait_until
from tower_borescope.app.window.recent_panel import KEEP_LIMIT, RecentPanel
from tower_borescope.capture.ffmpeg import AudioDevice
from tower_borescope.config import data_paths


def toasts(win):
    return win.view.toasts.visible(time.monotonic())


def test_short_press_takes_a_snapshot_shown_first_in_the_strip(window):
    window.pipeline.button.emit("short")
    recent = window.capture.feedback.recent
    assert wait_until(lambda: len(recent.paths()) == 1)
    assert recent.paths()[0].name.startswith("scope_")
    assert recent.paths()[0].parent == data_paths().pictures


def test_long_press_starts_recording(window, monkeypatch):
    requests = []
    monkeypatch.setattr(window.pipeline, "set_recording", requests.append)
    window.capture.on_scope_button("long")
    assert requests == [True]
    assert window.capture.panel.record_btn.isChecked()
    assert window.capture.panel.record_btn.text() == "Starting..."
    window.capture.on_scope_button("double")
    assert requests == [True]


def test_recording_state_updates_the_controls(window):
    feedback = window.capture.feedback
    feedback.on_recording_changed(True, "/captures/scope_1.mp4")
    assert window.menu_actions.record.text() == "Stop Recording"
    assert not window.camera.panel.res_combo.isEnabled()
    assert "Recording to scope_1.mp4" in toasts(window)
    assert window.view.recording_since is not None
    assert wait_until(lambda: window.capture.panel.record_btn.text().startswith("Stop"))
    feedback.on_recording_changed(False, "")
    assert window.capture.panel.record_btn.text() == "Record"
    assert window.capture.panel.audio_combo.isEnabled()
    assert window.view.recording_since is None


def test_stack_progress_and_timelapse_labels(window):
    feedback, panel = window.capture.feedback, window.capture.panel
    feedback.on_stack_progress(4, 16)
    assert panel.stack_btn.text() == "Stacking 4/16" and not panel.stack_btn.isEnabled()
    feedback.on_stack_progress(0, 0)
    assert panel.stack_btn.text() == "Stacked still" and panel.stack_btn.isEnabled()
    feedback.on_timelapse_changed(True, 3)
    assert panel.timelapse_btn.text() == "Stop time-lapse (3)"
    assert not panel.timelapse_spin.isEnabled()
    feedback.on_timelapse_changed(False, 3)
    assert panel.timelapse_btn.text() == "Start time-lapse"


def test_toggle_timelapse_sets_the_interval(window):
    window.capture.panel.timelapse_spin.setValue(7)
    window.capture.toggle_timelapse()
    assert window.pipeline.state.timelapse_interval == 7.0
    assert window.capture.panel.timelapse_btn.isChecked()
    window.capture.toggle_timelapse()
    assert window.pipeline.state.timelapse_interval == 0.0


def test_switches_update_state_and_settings(window):
    panel, state = window.capture.panel, window.pipeline.state
    panel.preroll_check.setChecked(False)
    panel.raw_check.setChecked(True)
    panel.auto_stack_check.setChecked(True)
    panel.motion_check.setChecked(True)
    assert not state.preroll_enabled and state.raw_recording
    assert state.auto_stack and state.motion_trigger
    assert window.ctx.prefs.values["preroll"] is False
    assert window.ctx.prefs.values["raw"] is True


@pytest.mark.parametrize("audio_devices", [[AudioDevice(3, "Test Microphone")]])
def test_microphone_choice_disables_the_preroll(window):
    panel = window.capture.panel
    assert panel.audio_combo.count() == 2
    panel.audio_combo.setCurrentIndex(1)
    assert window.pipeline.state.audio_device == 3
    assert not panel.preroll_check.isEnabled()
    assert window.ctx.prefs.values["audio_device"] == 3
    panel.audio_combo.setCurrentIndex(0)
    assert window.pipeline.state.audio_device is None and panel.preroll_check.isEnabled()


def test_snapshot_without_burn_in_sends_no_overlay(window, monkeypatch):
    overlays = []
    monkeypatch.setattr(window.pipeline, "snapshot", overlays.append)
    window.capture.snapshot()
    window.measure.group.burn_check.setChecked(False)
    window.capture.snapshot()
    assert overlays[0] is not None and overlays[1] is None


def test_folder_buttons_and_missing_files(window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", opened.append)
    window.capture.open_movies()
    assert data_paths().movies.is_dir()
    assert opened[0].toLocalFile() == str(data_paths().movies)
    window.ctx.open_path(data_paths().pictures / "gone.png")
    assert "File no longer exists" in toasts(window)


def test_recent_strip_loads_the_newest_captures(qapp, tmp_path):
    folder = tmp_path / "captures"
    folder.mkdir()
    stamp = time.time()
    for index in range(14):
        path = folder / f"scope_{index:02d}.png"
        cv2.imwrite(str(path), np.zeros((9, 16, 3), np.uint8))
        path.touch()
        import os

        os.utime(path, (stamp + index, stamp + index))
    strip = RecentPanel(lambda path: None)
    strip.load([folder])
    assert len(strip.paths()) == 12
    assert strip.paths()[0].name == "scope_13.png"


def test_recent_strip_keeps_a_limited_number(qapp, tmp_path):
    opened = []
    strip = RecentPanel(opened.append)
    for index in range(KEEP_LIMIT + 3):
        strip.add(tmp_path / f"scope_{index}.png", front=True)
    assert len(strip.paths()) == KEEP_LIMIT
    assert strip.paths()[0] == tmp_path / f"scope_{KEEP_LIMIT + 2}.png"
    strip.list.itemDoubleClicked.emit(strip.list.item(0))
    assert opened == [Path(tmp_path / f"scope_{KEEP_LIMIT + 2}.png")]
