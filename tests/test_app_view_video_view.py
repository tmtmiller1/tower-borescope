"""Tests for tower_borescope.app.view.video_view: state, freeze, compare, zoom, tools."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage

from synthetic import textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.app.view import video_view
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.measure.shapes import Measurement, OverlaySnapshot


def _info(seed=0, focus_raw=100.0):
    return FrameInfo(to_qimage(textured_frame(1280, 720, seed=seed)), focus_raw=focus_raw)


@pytest.fixture
def view(qapp):
    widget = VideoView()
    widget.resize(640, 360)
    yield widget
    widget.deleteLater()


def test_initial_state(view):
    frame_state = (view.image, view.live_image, view.info, view.live_badge_rect)
    assert frame_state == (None, None, None, None)
    assert view.status == video_view.CONNECTING_STATUS
    assert (view.zoom, view.compare_mode, view.compare_opacity) == (1.0, "off", 0.5)
    scale_state = (view.tool, view.mm_per_px, view.unit, view.scale_ok)
    assert scale_state == (None, None, "mm", None)
    assert (view.ai_boxes, view.minimumWidth(), view.minimumHeight()) == ([], 320, 180)
    assert (view.image_rect(), view.mapper()) == (QRectF(0, 0, 640, 360), None)


def test_qt_handlers_are_bound_by_class_attribute():
    assert VideoView.paintEvent is VideoView._paint_event
    assert VideoView.mousePressEvent is VideoView._mouse_press_event
    assert VideoView.mouseMoveEvent is VideoView._mouse_move_event
    assert VideoView.mouseReleaseEvent is VideoView._mouse_release_event
    assert VideoView.mouseDoubleClickEvent is VideoView._mouse_double_click_event
    assert VideoView.wheelEvent is VideoView._wheel_event


def test_freeze_holds_the_frame(view):
    first, second = _info(0, 10.0), _info(1, 20.0)
    view.set_frame(first)
    view.set_frozen(True)
    view.set_frame(second)
    assert view.frozen and view.image is first.image
    assert view.live_image is second.image and view.info is second
    assert view.focus_raw == 10.0
    view.set_frozen(False)
    assert view.image is second.image
    view.set_frame(_info(2, 30.0))
    assert view.focus_raw == 30.0


def test_compare_modes_paint(view):
    view.set_frame(_info())
    view.compare_image = QImage(view.image).convertToFormat(QImage.Format.Format_RGB888)
    for mode in ("off", "split", "overlay"):
        view.compare_mode = mode
        view.compare_opacity = 0.3
        assert not view.grab().isNull()


def test_set_zoom_clamps_anchors_and_resets_pan(view):
    zooms = []
    view.zoom_changed.connect(zooms.append)
    view.set_zoom(3.0)
    assert view.pan == QPointF()
    view.set_frame(_info())
    anchor = QPointF(500, 300)
    before = view.mapper().to_image(anchor)
    view.set_zoom(20.0, anchor)
    assert view.zoom == 8.0
    assert view.mapper().to_image(anchor) == pytest.approx(before)
    view.set_zoom(0.2, anchor)
    assert view.zoom == 1.0 and view.pan == QPointF()
    assert zooms == [3.0, 8.0, 1.0]


def test_set_tool_changes_cursor_and_drops_the_item_in_progress(view):
    view.overlays.current = Measurement("distance", [(1.0, 1.0)])
    view.set_tool("distance")
    assert view.tool == "distance" and view.overlays.current is None
    assert view.cursor().shape() == Qt.CursorShape.CrossCursor
    view.set_tool(None)
    assert view.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_overlay_snapshot_uses_scale_and_unit(view):
    view.mm_per_px = 0.02
    view.unit = "in"
    changed = []
    view.overlay_changed.connect(lambda: changed.append(True))
    view.overlays.finish_item(Measurement("distance", [(0.0, 0.0), (1270.0, 0.0)]))
    snapshot = view.overlay()
    assert isinstance(snapshot, OverlaySnapshot) and snapshot.has_items
    assert (snapshot.mm_per_px, snapshot.unit) == (0.02, "in")
    assert snapshot.measurements[0].label(snapshot.mm_per_px, snapshot.unit) == "1.000 in"
    view.overlays.clear()
    assert changed == [True, True]


def test_toast_and_housekeeping(view):
    view.toast("Snapshot saved", seconds=5.0)
    assert view.toasts.pending
    view._housekeeping()
    view.set_frame(_info())
    view.recording_since = 0.0
    view._housekeeping()
    assert not view.grab().isNull()
