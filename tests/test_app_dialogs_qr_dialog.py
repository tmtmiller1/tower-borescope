"""Tests for tower_borescope.app.dialogs.qr_dialog: the painted phone monitor code."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF

from tower_borescope.app.dialogs.qr_dialog import (
    HEIGHT,
    HINT_RECT,
    URL_FONT_SIZE,
    URL_RECT,
    WIDTH,
    QrDialog,
)
from tower_borescope.app.style import BACKGROUND
from tower_borescope.remote.qr import qr_matrix

ADDRESS = "http://192.168.1.20:8765/?key=Q2x8mVn4Rt7Kp1Ws9Yb3Hd6J"
LONGEST_ADDRESS = "http://192.168.100.200:65535/?key=Q2x8mVn4Rt7Kp1Ws9Yb3Hd6J"


@pytest.fixture
def painted(qapp):
    image = QrDialog(ADDRESS).grab().toImage()
    ratio = image.devicePixelRatio()

    def color(x, y):
        return image.pixelColor(int(x * ratio), int(y * ratio)).name()

    return color


def test_dialog_holds_the_matrix_at_a_fixed_size(qapp):
    dialog = QrDialog(ADDRESS)
    assert dialog.windowTitle() == "Phone monitor"
    assert dialog.matrix == qr_matrix(ADDRESS)
    assert (dialog.width(), dialog.height()) == (WIDTH, HEIGHT)
    assert QrDialog.paintEvent is QrDialog._paint_event


def test_keyed_address_wraps_inside_its_area(qapp):
    dialog = QrDialog(LONGEST_ADDRESS)
    font = QFont(dialog.font().family(), URL_FONT_SIZE, QFont.Weight.DemiBold)
    flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
    area = QRectF(*URL_RECT)
    bounds = QFontMetricsF(font).boundingRect(area, int(flags.value), dialog.url)
    assert area.contains(bounds)
    assert area.bottom() <= HINT_RECT[1] <= HEIGHT - HINT_RECT[3]


def test_paint_draws_background_and_quiet_zone(painted):
    assert painted(4, 4) == QColor(BACKGROUND).name()
    assert painted(24, 24) == "#ffffff"


def test_paint_draws_dark_and_light_modules(painted):
    code = {painted(x, y) for x in range(30, 330, 3) for y in range(30, 330, 3)}
    assert {"#000000", "#ffffff"} <= code


def test_paint_draws_the_address_text(painted):
    band = {painted(x, y) for x in range(0, WIDTH, 2) for y in range(350, 372, 2)}
    assert len(band) > 1
