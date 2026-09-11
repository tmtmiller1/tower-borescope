"""Tests for tower_borescope.app.view.overlay_painter: labels and annotation drawing."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from synthetic import textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.app.view.geometry import ImageMapper
from tower_borescope.app.view.overlay_painter import (
    draw_arrow,
    is_doubtful,
    measurement_text,
    paint_annotation,
)
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.measure.shapes import Annotation, Measurement

MAPPER = ImageMapper(QRectF(0, 0, 200, 100), QSize(400, 200))


def _canvas():
    canvas = QImage(200, 100, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.black)
    return canvas


@pytest.mark.parametrize(
    ("mm_per_px", "scale_ok", "kind", "expected"),
    [
        (0.05, False, "distance", True),
        (0.05, False, "area", True),
        (0.05, False, "angle", False),
        (0.05, True, "distance", False),
        (0.05, None, "distance", False),
        (None, False, "distance", False),
    ],
)
def test_doubt_needs_a_scale_and_a_failed_focus_lock(mm_per_px, scale_ok, kind, expected):
    assert is_doubtful(mm_per_px, scale_ok, kind) is expected


def test_doubtful_labels_carry_the_marker():
    assert measurement_text("5.00 mm", False) == "5.00 mm"
    text = measurement_text("5.00 mm", True)
    assert text == "≈ 5.00 mm  (focus differs from calibration)"


@pytest.mark.parametrize(
    "note",
    [
        Annotation("arrow", [(20.0, 20.0), (300.0, 150.0)]),
        Annotation("circle", [(200.0, 100.0), (260.0, 100.0)]),
        Annotation("freehand", [(20.0, 20.0), (80.0, 60.0), (160.0, 20.0)]),
        Annotation("text", [(40.0, 40.0)], "seam"),
    ],
)
def test_each_annotation_kind_draws(qapp, note):
    canvas = _canvas()
    blank = QImage(canvas)
    painter = QPainter(canvas)
    paint_annotation(painter, MAPPER, note)
    painter.end()
    assert canvas != blank


def test_annotations_with_one_point_draw_nothing(qapp):
    canvas = _canvas()
    blank = QImage(canvas)
    painter = QPainter(canvas)
    for kind in ("arrow", "circle", "freehand"):
        paint_annotation(painter, MAPPER, Annotation(kind, [(10.0, 10.0)]))
    painter.end()
    assert canvas == blank


def test_arrow_head_is_filled_in_the_pen_color(qapp):
    canvas = _canvas()
    painter = QPainter(canvas)
    painter.setPen(QPen(QColor("#00ff00"), 1))
    draw_arrow(painter, QPointF(10, 50), QPointF(190, 50))
    draw_arrow(painter, QPointF(100, 90), QPointF(100, 90))
    painter.end()
    assert canvas.pixelColor(185, 50) == QColor("#00ff00")
    assert canvas.pixelColor(182, 46).green() > 0


def test_measurements_paint_in_yellow_on_the_view(qapp):
    view = VideoView()
    view.resize(640, 360)
    view.set_frame(FrameInfo(to_qimage(textured_frame(1280, 720))))
    view.mm_per_px = 0.05
    view.scale_ok = False
    view.overlays.finish_item(Measurement("distance", [(100.0, 300.0), (1100.0, 300.0)]))
    view.overlays.current = Measurement("area", [(100.0, 500.0), (400.0, 500.0)])
    view.overlays.hover = (400.0, 700.0)
    pixmap = view.grab()
    ratio = pixmap.devicePixelRatio()
    color = pixmap.toImage().pixelColor(int(300 * ratio), int(150 * ratio))
    assert (color.red(), color.green(), color.blue()) == (255, 212, 0)
    view.deleteLater()
