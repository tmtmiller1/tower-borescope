"""Tests for tower_borescope.app.view.painter: meters, grid, AI boxes, full paint."""

from __future__ import annotations

import time

import numpy as np
import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from synthetic import textured_frame
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.app.view.ai_boxes import AiBox
from tower_borescope.app.view.painter import (
    clipped_text,
    focus_color,
    paint_ai_boxes,
    paint_grid,
    paint_view,
)
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.measure.shapes import Annotation, Measurement


def _info():
    hist = np.linspace(0, 1, 64).astype(np.float32)
    image = to_qimage(textured_frame(1280, 720))
    return FrameInfo(image, focus=0.7, focus_raw=150.0, hist=hist, clipped=0.03)


@pytest.mark.parametrize(
    ("focus", "color"),
    [
        (0.9, "#38c172"),
        (0.85, "#f0b429"),
        (0.51, "#f0b429"),
        (0.5, "#e3342f"),
        (0, "#e3342f"),
    ],
)
def test_focus_bar_thresholds(focus, color):
    assert focus_color(focus) == color


def test_clipped_caption():
    assert clipped_text(0.0153) == "clipped 1.5%"


def test_grid_and_boxes_draw_on_an_image(qapp):
    canvas = QImage(320, 180, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.black)
    blank = QImage(canvas)
    painter = QPainter(canvas)
    rect = QRectF(0, 0, 320, 180)
    paint_grid(painter, rect)
    boxes = [
        AiBox(0.1, 0.4, 0.5, 0.8, "rust", "high"),
        AiBox(0.6, 0.0, 0.9, 0.2, "x", "?"),
    ]
    paint_ai_boxes(painter, rect, boxes)
    painter.end()
    assert canvas != blank
    bracket = canvas.pixelColor(40, 72)
    assert (bracket.red(), bracket.green(), bracket.blue()) == (255, 90, 60)


def test_painting_every_overlay_does_not_raise(qapp):
    view = VideoView()
    view.resize(800, 450)
    view.set_frame(_info())
    view.grid = True
    view.ai_boxes = [AiBox(0.42, 0.30, 0.68, 0.55, "Mineral deposits", "medium")]
    view.mm_per_px, view.scale_ok = 0.05, False
    view.overlays.finish_item(Measurement("distance", [(100.0, 100.0), (500.0, 100.0)]))
    view.overlays.finish_item(
        Measurement("angle", [(600.0, 200.0), (500.0, 300.0), (700.0, 300.0)])
    )
    closed = Measurement("area", [(100.0, 400.0), (300.0, 400.0), (300.0, 600.0)], True)
    view.overlays.finish_item(closed)
    for note in (
        Annotation("arrow", [(200.0, 300.0), (400.0, 380.0)]),
        Annotation("circle", [(900.0, 400.0), (950.0, 450.0)]),
        Annotation("text", [(600.0, 500.0)], "crack here"),
        Annotation("freehand", [(50.0, 600.0), (80.0, 650.0), (120.0, 640.0)]),
    ):
        view.overlays.finish_item(note)
    view.recording_since = time.monotonic() - 75
    view.set_tool("area")
    view.set_zoom(1.5)
    view.toast("Snapshot saved")
    view.set_frozen(True)
    plain = view.grab().toImage()
    assert not plain.isNull() and view.live_badge_rect is not None
    view.compare_image = to_qimage(textured_frame(1280, 720, seed=4))
    for mode in ("overlay", "split"):
        view.compare_mode = mode
        assert not view.grab().isNull()
    view.status = "Scope disconnected"
    view.info.hist = None
    assert not view.grab().isNull()
    view.deleteLater()


def test_paint_view_without_an_image_shows_the_status(qapp):
    view = VideoView()
    view.resize(400, 200)
    canvas = QImage(400, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(canvas)
    paint_view(view, painter)
    painter.end()
    assert view.live_badge_rect is None
    colors = {canvas.pixelColor(x, 100).name() for x in range(0, 400, 2)}
    assert len(colors) > 1
    view.deleteLater()
