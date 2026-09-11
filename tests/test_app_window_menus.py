"""Tests for tower_borescope.app.window.menus, camera_controller and image_controller:
menu items and shortcuts as documented, menu-driven image and tool changes, the
shortcut summary and the statistics line."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import QMessageBox

from conftest import wait_until
from tower_borescope.app.window.menus import SHORTCUTS_TEXT, SHORTCUTS_TITLE
from tower_borescope.config import data_paths

EXPECTED = (
    ("File", "Snapshot", "S"),
    ("File", "Stacked Still", "P"),
    ("File", "Burst", "B"),
    ("File", "Start Recording", "V"),
    ("File", "Start/Stop Time-lapse", "Shift+T"),
    ("File", "Gallery...", "Ctrl+G"),
    ("File", "Open Pictures Folder", "Ctrl+Shift+P"),
    ("File", "Open Movies Folder", "Ctrl+Shift+M"),
    ("File", "Quit", QKeySequence.StandardKey.Quit),
    ("Camera", "1280 x 720  (best detail)", "1"),
    ("Camera", "160 x 120", "5"),
    ("Image", "Enhance", "E"),
    ("Image", "Auto White Balance", "W"),
    ("Image", "Stabilize", "Shift+S"),
    ("Image", "Brighter", "."),
    ("Image", "Darker", ","),
    ("Image", "More Contrast", ">"),
    ("Image", "Less Contrast", "<"),
    ("Image", "More Saturation", "'"),
    ("Image", "Less Saturation", ";"),
    ("Image", "Reset Image Settings", "Shift+C"),
    ("Tools", "Freeze", "Space"),
    ("Tools", "Measure Distance", "M"),
    ("Tools", "Measure Angle", "Shift+M"),
    ("Tools", "Measure Area", "Ctrl+M"),
    ("Tools", "Arrow", "A"),
    ("Tools", "Circle", "O"),
    ("Tools", "Text", "T"),
    ("Tools", "Draw", "D"),
    ("Tools", "Cancel Tool", "Esc"),
    ("Tools", "Undo", QKeySequence.StandardKey.Undo),
    ("Tools", "Clear Measurements and Annotations", "Ctrl+Backspace"),
    ("Tools", "Calibrate Scale...", "Ctrl+K"),
    ("View", "Rotate Clockwise", "R"),
    ("View", "Rotate Counter-clockwise", "Shift+R"),
    ("View", "Mirror", "F"),
    ("View", "Grid and Crosshair", "G"),
    ("View", "Focus Meter and Histogram", "I"),
    ("View", "Zoom In", "+"),
    ("View", "Zoom Out", "-"),
    ("View", "Reset Zoom", "0"),
    ("View", "Show Controls", "Ctrl+\\"),
    ("View", "Full Screen", "Ctrl+Meta+F"),
    ("AI", "Analyze What's in View", "Ctrl+Shift+A"),
    ("AI", "Ask a Follow-up...", "Ctrl+L"),
    ("AI", "Estimate Scale from View", "Ctrl+Shift+K"),
    ("AI", "Add View to Report", "Ctrl+Shift+R"),
    ("AI", "Write Inspection Report...", None),
    ("AI", "AI Settings...", None),
    ("Help", "Keyboard Shortcuts", "?"),
)
DASHES = (chr(0x2013), chr(0x2014))


def menu_items(win):
    items = {}
    for top in win.menuBar().actions():
        for action in top.menu().actions():
            if not action.isSeparator():
                items[(top.text(), action.text(), action.shortcut().toString())] = action
    return items


def trigger(win, menu, text):
    matches = [a for (m, t, _), a in menu_items(win).items() if (m, t) == (menu, text)]
    matches[0].trigger()


def test_menu_items_and_shortcuts_match_the_user_guide(window):
    found = menu_items(window)
    expected = {
        (menu, text, QKeySequence(key).toString() if key is not None else "")
        for menu, text, key in EXPECTED
    }
    assert expected - set(found) == set()
    contexts = {action.shortcutContext() for action in found.values()}
    assert contexts == {Qt.ShortcutContext.ApplicationShortcut}


def test_image_menu_toggles_and_nudges(window):
    trigger(window, "Image", "Enhance")
    panel = window.image.panel
    assert panel.enhance_check.isChecked() and window.pipeline.state.enhanced
    trigger(window, "Image", "Brighter")
    assert window.pipeline.state.grade.brightness == 8
    trigger(window, "Image", "Less Contrast")
    assert window.pipeline.state.grade.contrast == pytest.approx(0.9)
    trigger(window, "Image", "Reset Image Settings")
    assert (panel.brightness.value(), window.pipeline.state.grade.contrast) == (0, 1.0)
    assert not panel.enhance_check.isChecked()
    assert window.ctx.prefs.values["enhance"] is False


def test_camera_menu_switches_resolution(window):
    trigger(window, "Camera", "640 x 480  (wider view)")
    assert window.camera.panel.res_combo.currentData() == "480p"
    assert window.menu_actions.resolutions.checkedAction().text().startswith("640 x 480")
    assert wait_until(lambda: window.pipeline.state.mode == "480p")


def test_tools_and_view_menu_actions(window):
    trigger(window, "Tools", "Measure Angle")
    assert window.view.tool == "angle"
    trigger(window, "Tools", "Cancel Tool")
    assert window.view.tool is None
    trigger(window, "Tools", "Freeze")
    assert window.view.frozen and window.menu_actions.freeze.isChecked()
    trigger(window, "View", "Zoom In")
    assert window.view.zoom == pytest.approx(1.25)
    trigger(window, "View", "Reset Zoom")
    assert window.view.zoom == 1.0
    trigger(window, "View", "Focus Meter and Histogram")
    assert not window.pipeline.state.meters and not window.view.show_meters


def test_keyboard_shortcut_summary(window, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[1:]))
    trigger(window, "Help", "Keyboard Shortcuts")
    assert shown == [(SHORTCUTS_TITLE, SHORTCUTS_TEXT)]
    assert "1 to 5 resolution" in SHORTCUTS_TEXT
    assert not any(dash in SHORTCUTS_TEXT for dash in DASHES)


def test_file_menu_opens_folders_and_the_gallery(window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", opened.append)
    trigger(window, "File", "Open Pictures Folder")
    assert data_paths().pictures.is_dir()
    assert opened[0].toLocalFile() == str(data_paths().pictures)
    trigger(window, "File", "Gallery...")
    assert window.gallery is not None and window.gallery.isVisible()
    window.gallery.close()


def test_statistics_line_shows_status_rate_and_drops(window):
    camera = window.camera
    camera.on_stats(0.0, 0, "Scope disconnected. Plug it back in...")
    assert camera.panel.stats_label.text() == "Scope disconnected. Plug it back in..."
    assert window.view.status == camera.status_left.text()
    camera.on_size_changed(640, 480)
    camera.on_stats(19.5, 3, "")
    assert camera.panel.stats_label.text() == "640x480   19.5 fps   dropped 3"
    assert camera.status_left.text() == "Streaming"
    camera.set_resolution(window.pipeline.state.mode)
    assert window.ctx.prefs.values.get("mode") is None


def test_image_controller_validates_names_and_resets_denoise(window):
    with pytest.raises(ValueError, match="unknown color control"):
        window.image.set_grade("gamma", 1.0)
    with pytest.raises(ValueError, match="unknown filter"):
        window.image.set_filter("blur", 1.0)
    window.image.panel.denoise.set_value(40)
    assert window.pipeline.state.denoise == pytest.approx(0.4)
    window.image.panel.mode_combo.setCurrentText("Edges")
    assert window.ctx.prefs.values["view_mode"] == "Edges"
    window.image.meters.zebra_check.setChecked(True)
    assert window.pipeline.state.zebra
