"""Tests for tower_borescope.app.window.freeze_controller and compare_controller: every
way back to live after an AI analysis (Back to live, Esc in a text field, the FROZEN
badge, Space after clicking Analyze), focus policies and reference images."""

from __future__ import annotations

import time

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QFileDialog, QPushButton

from conftest import wait_until
from fakes import FakeBackend
from tower_borescope.app.window import compare_controller
from tower_borescope.app.window.freeze_controller import FROZEN_TOAST, LIVE_TOAST

INACTIVE_REASON = "the test window could not become the active application"


@pytest.fixture
def window(window):
    window.raise_()
    window.activateWindow()
    window.ai.backend = FakeBackend()
    window.tabs.setCurrentIndex(1)
    return window


def analyze(win):
    win.ai.analyze()
    return wait_until(lambda: win.view.frozen and bool(win.view.ai_boxes))


def is_live(win):
    view = win.view
    wait_until(lambda: False, 0.5)
    return (not view.frozen) and not view.ai_boxes and view.image is view.live_image


def press_shortcut(win, key):
    """Send ``key`` to the view while ``win`` is the active window, or skip.

    Application shortcuts only match while one of the application's windows is
    active, and another process can take activation away in the middle of a test.
    """
    if not win.isActiveWindow():
        win.activateWindow()
        if not QTest.qWaitForWindowActive(win, 2000):
            pytest.skip(INACTIVE_REASON)
    QTest.keyClick(win.view, key)


def test_back_to_live_button_clears_boxes_and_resumes(window):
    assert analyze(window)
    back = [b for b in window.findChildren(QPushButton) if b.text() == "Back to live"]
    assert len(back) == 1
    back[0].click()
    assert is_live(window)


def test_escape_from_the_follow_up_field_returns_to_live(qapp, window):
    assert analyze(window)
    window.ai.panel.question.setFocus()
    qapp.processEvents()
    QTest.keyClick(window.ai.panel.question, Qt.Key.Key_Escape)
    assert is_live(window)


def test_clicking_the_frozen_badge_returns_to_live(window):
    assert analyze(window)
    window.view.repaint()
    rect = window.view.live_badge_rect
    assert rect is not None
    point = QPoint(int(rect.center().x()), int(rect.center().y()))
    QTest.mouseClick(
        window.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
    )
    assert is_live(window)


def test_sidebar_controls_refuse_keyboard_focus(window):
    buttons = window.findChildren(QPushButton)
    boxes = window.findChildren(QCheckBox)
    assert buttons and boxes
    assert all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in buttons)
    assert all(c.focusPolicy() == Qt.FocusPolicy.NoFocus for c in boxes)
    assert window.ai.panel.browser.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_clicking_analyze_leaves_focus_off_the_button(window):
    assert analyze(window)
    window.ai.panel.analyze_btn.click()
    assert wait_until(lambda: not window.ai.runner.busy())
    assert QApplication.focusWidget() is not window.ai.panel.analyze_btn
    window.back_to_live()
    assert is_live(window)


def test_space_and_escape_shortcuts_return_to_live(window):
    if not QTest.qWaitForWindowActive(window, 2000):
        pytest.skip(INACTIVE_REASON)
    assert analyze(window)
    window.ai.panel.analyze_btn.click()
    assert wait_until(lambda: not window.ai.runner.busy())
    press_shortcut(window, Qt.Key.Key_Space)
    assert is_live(window)
    assert analyze(window)
    press_shortcut(window, Qt.Key.Key_Escape)
    assert is_live(window)


def test_toggle_freeze_keeps_indicators_in_step(window):
    window.freeze.toggle_freeze()
    assert window.freeze.frozen_frame is not None
    assert window.compare.group.freeze_btn.isChecked()
    assert window.menu_actions.freeze.isChecked()
    assert FROZEN_TOAST in window.view.toasts.visible(time.monotonic())
    window.freeze.toggle_freeze()
    assert not window.menu_actions.freeze.isChecked()
    assert LIVE_TOAST in window.view.toasts.visible(time.monotonic())


def test_pick_reference_loads_the_chosen_file(window, tmp_path, monkeypatch):
    reference = tmp_path / "before.png"
    cv2.imwrite(str(reference), np.full((40, 60, 3), 200, np.uint8))
    answers = [(str(reference), "Images"), ("", "")]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: answers.pop(0))
    window.compare.pick_reference()
    assert window.compare.group.compare_label.text() == "Reference: before.png"
    assert window.view.compare_mode == "split"
    window.compare.pick_reference()
    assert window.compare.group.compare_label.text() == "Reference: before.png"
    assert compare_controller.COMPARE_MODES == ("off", "split", "overlay")


def test_reference_errors_are_reported(window, tmp_path):
    window.compare.set_reference(str(tmp_path / "missing.png"))
    assert "Could not load that image" in window.view.toasts.visible(time.monotonic())
    window.compare.set_mode(1)
    assert "Choose a reference image first" in window.view.toasts.visible(
        time.monotonic()
    )
    window.compare.set_opacity(25.0)
    assert window.view.compare_opacity == 0.25
