"""Tests for tower_borescope.app.view.badges: badge drawing, toasts and the HUD."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from synthetic import textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.app.view.badges import (
    FROZEN_TEXT,
    MAX_TOASTS,
    TOOL_HINTS,
    Toasts,
    draw_badge,
    paint_hud,
    recording_text,
    tool_hint,
)
from tower_borescope.app.view.video_view import VideoView


def test_frozen_text_is_plain():
    assert FROZEN_TEXT == "FROZEN: click or Esc for live"
    assert all(ord(character) < 128 for character in FROZEN_TEXT)


def test_recording_and_tool_hint_text():
    assert recording_text(65.9) == "REC  01:05"
    assert recording_text(0) == "REC  00:00"
    assert (
        tool_hint("area") == "area: click corners, double-click to close   (Esc cancels)"
    )
    assert tool_hint("unknown") == "unknown:    (Esc cancels)"
    assert set(TOOL_HINTS) >= {"distance", "angle", "calibrate", "text", "freehand"}


def test_draw_badge_fills_a_rectangle_around_the_text(qapp):
    canvas = QImage(300, 80, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    rect = draw_badge(painter, "hello", QPointF(10, 10), QColor("#ff0000"))
    painter.end()
    assert rect.left() == 10 and rect.top() == 10
    assert rect.width() > 20 and rect.height() > 10
    assert canvas.pixelColor(12, int(rect.center().y())) == QColor("#ff0000")


def test_toasts_replace_duplicates_expire_and_show_three():
    toasts = Toasts()
    assert not toasts.pending
    for index, text in enumerate(("a", "b", "c", "d")):
        toasts.add(text, 3.0, now=float(index))
    toasts.add("b", 3.0, now=4.0)
    assert toasts.visible(now=4.5) == ["c", "d", "b"][-MAX_TOASTS:]
    assert toasts.visible(now=6.5) == ["b"]
    assert toasts.visible(now=8.0) == []
    assert not toasts.pending


def test_hud_places_the_frozen_badge_and_other_badges(qapp):
    view = VideoView()
    view.resize(640, 360)
    view.set_frame(FrameInfo(to_qimage(textured_frame(640, 360))))
    canvas = QImage(640, 360, QImage.Format.Format_ARGB32)
    painter = QPainter(canvas)
    assert paint_hud(view, painter) is None
    view.set_frozen(True)
    view.set_zoom(2.0)
    view.set_tool("distance")
    view.recording_since = 0.0
    view.toast("one")
    view.toast("two")
    rect = paint_hud(view, painter)
    view.compare_mode = "split"
    split_rect = paint_hud(view, painter)
    painter.end()
    assert rect is not None and (rect.left(), rect.top()) == (16, 16)
    assert split_rect is None
    view.deleteLater()
