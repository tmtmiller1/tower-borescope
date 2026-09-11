"""Tests for tower_borescope.app.window.context: saved preferences and the shared window
state helpers."""

from __future__ import annotations

import json
import time

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow

from fakes import FakeReader
from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.app.window.context import ORGANIZATION, Preferences, WindowContext
from tower_borescope.config import SettingsStore, data_paths


def test_preferences_merge_and_save(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save({"mode": "480p"})
    prefs = Preferences(store)
    assert prefs.values == {"mode": "480p"}
    prefs.remember(unit="in", mirror=True)
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved == {"mode": "480p", "unit": "in", "mirror": True}
    assert ORGANIZATION == "tower_borescope"


def make_context(tmp_path):
    prefs = Preferences(SettingsStore(tmp_path / "settings.json"))
    pipeline = Pipeline(prefs.values, FakeReader)
    return WindowContext(QMainWindow(), pipeline, VideoView(), prefs, data_paths())


def test_context_toasts_and_capture_folders(qapp, tmp_path):
    ctx = make_context(tmp_path)
    ctx.toast("Hello")
    assert "Hello" in ctx.view.toasts.visible(time.monotonic())
    paths = data_paths()
    assert ctx.capture_folders() == [paths.pictures, paths.movies]


def test_open_path_creates_folders_and_reports_missing_files(qapp, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", opened.append)
    ctx = make_context(tmp_path)
    folder = tmp_path / "new_folder"
    ctx.open_path(folder)
    assert folder.is_dir()
    assert opened[0].toLocalFile() == str(folder)
    ctx.open_path(tmp_path / "missing.png")
    assert len(opened) == 1
    assert "File no longer exists" in ctx.view.toasts.visible(time.monotonic())
