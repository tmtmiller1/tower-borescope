"""Tests for tower_borescope.app.widgets.layout: containers and unfocusable controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from tower_borescope.app.widgets.layout import (
    button,
    checkbox,
    column,
    group,
    row,
    scrolled,
    small_label,
)


def test_button_refuses_focus_and_calls_its_slot(qapp):
    clicks = []
    push = button("Snapshot", lambda: clicks.append(1), tip="Saves", name="primary")
    assert push.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert push.toolTip() == "Saves"
    assert push.objectName() == "primary"
    assert not push.isCheckable()
    push.click()
    assert clicks == [1]


def test_checkable_button(qapp):
    push = button("Record", lambda: None, checkable=True, name="record")
    assert push.isCheckable()
    push.click()
    assert push.isChecked()


def test_checkbox_refuses_focus_and_reports_toggles(qapp):
    states = []
    box = checkbox("Mirror", True, states.append, tip="Flip")
    assert box.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert box.isChecked()
    assert states == []
    assert box.toolTip() == "Flip"
    box.toggle()
    assert states == [False]


def test_group_row_and_column_hold_their_widgets(qapp):
    first, second = QLabel("a"), QLabel("b")
    box = group("CAPTURE", first, second)
    assert box.title() == "CAPTURE"
    assert isinstance(box.layout(), QVBoxLayout)
    assert box.layout().count() == 2
    line = row(QLabel("c"), QLabel("d"))
    assert isinstance(line.layout(), QHBoxLayout)
    assert line.layout().count() == 2
    stack = column(QLabel("e"))
    assert stack.layout().count() == 2


def test_scrolled_never_scrolls_sideways(qapp):
    inner = QLabel("content")
    area = scrolled(inner)
    assert area.widget() is inner
    assert area.widgetResizable()
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_small_label(qapp):
    label = small_label("hint")
    assert label.objectName() == "small"
    assert label.wordWrap()
    assert not small_label("x", wrap=False).wordWrap()
