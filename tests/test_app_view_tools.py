"""Tests for tower_borescope.app.view.tools: every tool through real mouse events."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QInputDialog

from synthetic import textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.app.view import tools
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.measure.shapes import Annotation, Measurement

LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
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


def _click(view, pos, button=LEFT):
    _send(view, PRESS, pos, button)
    _send(view, RELEASE, pos, button, NONE)


def _drag(view, points):
    _send(view, PRESS, points[0])
    for pos in points[1:]:
        _send(view, MOVE, pos, NONE, LEFT)
    _send(view, RELEASE, points[-1], LEFT, NONE)


@pytest.fixture
def view(qapp):
    widget = VideoView()
    widget.resize(640, 360)
    widget.set_frame(FrameInfo(to_qimage(textured_frame(1280, 720))))
    widget.finished = []
    widget.calibrated = []
    widget.changes = []
    widget.tool_finished.connect(lambda: widget.finished.append(True))
    widget.calibrate_measured.connect(lambda pixels: widget.calibrated.append(pixels))
    widget.overlay_changed.connect(lambda: widget.changes.append(True))
    yield widget
    widget.deleteLater()


@pytest.mark.parametrize(
    ("tool", "clicks", "value"),
    [
        ("distance", [(50, 50), (250, 50)], 400.0),
        ("angle", [(250, 50), (50, 50), (50, 150)], 90.0),
    ],
)
def test_measurement_tools_finish_after_enough_clicks(view, tool, clicks, value):
    view.set_tool(tool)
    for pos in clicks:
        _click(view, pos)
    assert len(view.overlays.measurements) == 1
    item = view.overlays.measurements[0]
    assert item.kind == tool and item.pixel_value() == pytest.approx(value)
    assert view.overlays.current is None and view.finished == [True]


def test_area_closes_on_double_click(view):
    view.set_tool("area")
    for pos in ((50, 50), (250, 50), (250, 150)):
        _click(view, pos)
    assert isinstance(view.overlays.current, Measurement)
    _send(view, QEvent.Type.MouseButtonDblClick, (250, 150))
    area = view.overlays.measurements[0]
    assert area.closed and area.pixel_value() == pytest.approx(0.5 * 400 * 200)
    assert view.finished == [True] and view.overlays.current is None


def test_area_closes_on_right_click_and_short_outlines_cancel(view):
    view.set_tool("area")
    for pos in ((50, 50), (250, 50), (250, 150)):
        _click(view, pos)
    _send(view, PRESS, (10, 10), RIGHT)
    assert len(view.overlays.measurements) == 1
    for pos in ((50, 50), (250, 50)):
        _click(view, pos)
    _send(view, PRESS, (10, 10), RIGHT)
    assert len(view.overlays.measurements) == 1 and view.overlays.current is None


def test_calibrate_emits_pixels_without_adding_a_measurement(view):
    view.set_tool("calibrate")
    _click(view, (50, 100))
    _click(view, (50, 250))
    assert view.calibrated == [pytest.approx(300.0)]
    assert view.overlays.measurements == [] and view.finished == [True]


@pytest.mark.parametrize("tool", ["arrow", "circle"])
def test_drag_annotations_keep_start_and_end(view, tool):
    view.set_tool(tool)
    _drag(view, [(50, 50), (100, 80), (150, 100)])
    note = view.overlays.annotations[0]
    assert note.kind == tool and note.points == [(100.0, 100.0), (300.0, 200.0)]
    assert view.overlays.current is None


def test_freehand_follows_the_pointer(view):
    view.set_tool("freehand")
    _drag(view, [(50, 50), (60, 55), (70, 60), (80, 70)])
    assert len(view.overlays.annotations[0].points) == 4


def test_click_without_drag_keeps_nothing(view):
    view.set_tool("arrow")
    _click(view, (50, 50))
    assert view.overlays.annotations == [] and view.overlays.current is None


def test_text_tool_places_a_note(view, monkeypatch):
    answers = iter(["crack here", None])
    monkeypatch.setattr(tools, "ask_text", lambda parent: next(answers))
    view.set_tool("text")
    _click(view, (100, 100))
    _click(view, (200, 100))
    assert len(view.overlays.annotations) == 1
    note = view.overlays.annotations[0]
    assert isinstance(note, Annotation) and note.text == "crack here"
    assert note.points == [(200.0, 200.0)]


def test_ask_text_strips_and_rejects_blank_input(qapp, monkeypatch):
    replies = iter([("  seam  ", True), ("   ", True), ("typed", False)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: next(replies))
    assert tools.ask_text(None) == "seam"
    assert tools.ask_text(None) is None
    assert tools.ask_text(None) is None


def test_measurement_preview_tracks_the_pointer(view):
    view.set_tool("distance")
    _click(view, (50, 50))
    _send(view, MOVE, (100, 100), NONE, NONE)
    assert view.overlays.hover == (200.0, 200.0)
    assert view.grab().isNull() is False


def test_undo_removes_the_last_item(view):
    view.set_tool("distance")
    for pos in ((10, 10), (60, 10), (10, 80), (60, 80)):
        _click(view, pos)
    view.set_tool("arrow")
    _drag(view, [(100, 100), (200, 200)])
    assert (len(view.overlays.measurements), len(view.overlays.annotations)) == (2, 1)
    view.overlays.undo()
    assert (len(view.overlays.measurements), len(view.overlays.annotations)) == (2, 0)
    view.overlays.undo()
    assert len(view.overlays.measurements) == 1
    assert len(view.changes) == 5
