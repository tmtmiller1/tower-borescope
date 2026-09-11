"""Tests for tower_borescope.app.style: palette constants and the style sheet."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QWidget

from tower_borescope.app import style

COLOR_NAMES = (
    "ACCENT",
    "RECORD_RED",
    "BACKGROUND",
    "PANEL_BACKGROUND",
    "BORDER",
    "TEXT",
    "MUTED_TEXT",
    "ERROR_TEXT",
    "LINK_TEXT",
)


def test_palette_entries_are_hex_colors():
    for name in COLOR_NAMES:
        assert re.fullmatch(r"#[0-9a-f]{6}", getattr(style, name)), name


def test_style_sheet_uses_the_palette_and_object_names():
    sheet = style.STYLE_SHEET
    assert style.ACCENT in sheet
    assert style.RECORD_RED in sheet
    for selector in ("QPushButton#primary", "QPushButton#record:checked", "QLabel#small"):
        assert selector in sheet
    assert "{{" not in sheet


def test_style_sheet_applies_to_a_widget(qapp):
    widget = QWidget()
    widget.setStyleSheet(style.STYLE_SHEET)
    assert widget.styleSheet() == style.STYLE_SHEET
    assert style.PANEL_BACKGROUND in style.AI_PANEL_STYLE
    assert style.BORDER in style.DIVIDER_STYLE
