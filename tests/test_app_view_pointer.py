"""Tests for tower_borescope.app.view.pointer: badge click, wheel, pan, split drag."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from synthetic import textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.app.view.pointer import SPLIT_GRAB_PIXELS, PointerHandler
from tower_borescope.app.view.video_view import VideoView

LEFT = Qt.MouseButton.LeftButton
NONE = Qt.MouseButton.NoButton
PRESS = QEvent.Type.MouseButtonPress
MOVE = QEvent.Type.MouseMove
RELEASE = QEvent.Type.MouseButtonRelease


def _send(view, kind, pos, button=LEFT, held=None):
    point = QPointF(*pos)
    buttons = button if held is None else held
    modifiers = Qt.KeyboardModifier.NoModifier
    event = QMouseEvent(kind, point, view.mapToGlobal(point), button, buttons, modifiers)
    QApplication.sendEvent(view, event)


def _wheel(view, x, y, degrees):
    pos = QPointF(x, y)
    event = QWheelEvent(
        pos,
        view.mapToGlobal(pos),
        QPoint(),
        QPoint(0, degrees),
        NONE,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view, event)


@pytest.fixture
def view(qapp):
    widget = VideoView()
    widget.resize(640, 360)
    widget.set_frame(FrameInfo(to_qimage(textured_frame(1280, 720))))
    yield widget
    widget.deleteLater()


def test_clicking_the_frozen_badge_requests_live(view):
    requested = []
    view.live_requested.connect(lambda: requested.append(True))
    view.set_frozen(True)
    view.grab()
    rect = view.live_badge_rect
    assert rect is not None and rect.left() == 16
    centre = QPoint(int(rect.center().x()), int(rect.center().y()))
    QTest.mouseClick(view, LEFT, Qt.KeyboardModifier.NoModifier, centre)
    assert requested == [True]
    QTest.mouseClick(view, LEFT, Qt.KeyboardModifier.NoModifier, QPoint(600, 300))
    assert requested == [True]


def test_badge_is_not_clickable_while_live(view):
    requested = []
    view.live_requested.connect(lambda: requested.append(True))
    view.grab()
    assert view.live_badge_rect is None
    _send(view, PRESS, (30, 25))
    assert requested == []


def test_wheel_zooms_about_the_pointer(view):
    zooms = []
    view.zoom_changed.connect(zooms.append)
    point = view.mapper().to_image(QPointF(160, 90))
    _wheel(view, 160, 90, 240)
    assert view.zoom == pytest.approx(1.15**2) and zooms == [pytest.approx(1.15**2)]
    assert view.mapper().to_image(QPointF(160, 90)) == pytest.approx(point)


def test_drag_pans_only_while_zoomed(view):
    _send(view, PRESS, (320, 180))
    _send(view, MOVE, (420, 180), NONE, LEFT)
    _send(view, RELEASE, (420, 180), LEFT, NONE)
    assert view.pan == QPointF()
    view.set_zoom(2.0)
    _send(view, PRESS, (320, 180))
    _send(view, MOVE, (420, 180), NONE, LEFT)
    assert view.image_rect().left() == -220
    _send(view, MOVE, (2000, 180), NONE, LEFT)
    _send(view, RELEASE, (2000, 180), LEFT, NONE)
    assert view.image_rect().left() == 0


def test_double_click_resets_the_zoom(view):
    view.set_zoom(3.0, QPointF(100, 100))
    _send(view, QEvent.Type.MouseButtonDblClick, (100, 100))
    assert view.zoom == 1.0 and view.pan == QPointF()


def test_split_divider_drags_and_changes_the_cursor(view):
    view.compare_image = QImage(view.image)
    view.compare_mode = "split"
    _send(view, MOVE, (320, 100), NONE, NONE)
    assert view.cursor().shape() == Qt.CursorShape.SplitHCursor
    _send(view, MOVE, (320 + SPLIT_GRAB_PIXELS * 4, 100), NONE, NONE)
    assert view.cursor().shape() == Qt.CursorShape.OpenHandCursor
    _send(view, PRESS, (322, 100))
    _send(view, MOVE, (480, 100), NONE, LEFT)
    _send(view, RELEASE, (480, 100), LEFT, NONE)
    assert view.split == pytest.approx(0.75)
    view.set_frozen(True)
    view.grab()
    assert view.live_badge_rect is None


def test_split_cursor_shows_the_tool_away_from_the_divider(view):
    view.compare_image = QImage(view.image)
    view.compare_mode = "split"
    view.set_tool("distance")
    _send(view, MOVE, (100, 100), NONE, NONE)
    assert view.cursor().shape() == Qt.CursorShape.CrossCursor


def test_right_click_without_a_tool_does_nothing(view):
    _send(view, PRESS, (100, 100), Qt.MouseButton.RightButton)
    assert (view.zoom, view.overlays.current, view.live_badge_rect) == (1.0, None, None)


def test_events_without_an_image_are_ignored(qapp):
    empty = VideoView()
    handler = PointerHandler(empty)
    assert handler is not None
    _send(empty, PRESS, (10, 10))
    _send(empty, MOVE, (20, 20), NONE, LEFT)
    _wheel(empty, 10, 10, 120)
    assert empty.zoom == 1.0
    empty.deleteLater()
