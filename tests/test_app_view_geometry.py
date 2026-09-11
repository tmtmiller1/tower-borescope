"""Tests for tower_borescope.app.view.geometry: fit, pan clamping, zoom anchoring."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, QSize

from tower_borescope.app.view.geometry import (
    ZOOM_MAX,
    ZOOM_MIN,
    ImageMapper,
    anchored_pan,
    clamp_zoom,
    image_rect,
    split_fraction,
    split_position,
    wheel_zoom,
)

WIDGET = QSize(640, 360)
IMAGE = QSize(1280, 720)


def test_zoom_is_clamped_between_one_and_eight():
    assert (ZOOM_MIN, ZOOM_MAX) == (1.0, 8.0)
    assert clamp_zoom(0.3) == 1.0
    assert clamp_zoom(20.0) == 8.0
    assert clamp_zoom(2.5) == 2.5


def test_wheel_steps_multiply_the_zoom():
    assert wheel_zoom(1.0, 120) == pytest.approx(1.15)
    assert wheel_zoom(2.0, -240) == pytest.approx(2.0 / 1.15**2)


def test_image_fits_and_centres_in_the_widget():
    assert image_rect(WIDGET, IMAGE, 1.0) == QRectF(0, 0, 640, 360)
    tall = image_rect(QSize(640, 640), IMAGE, 1.0)
    assert tall == QRectF(0, 140, 640, 360)


def test_pan_is_clamped_to_the_zoomed_image():
    centred = image_rect(WIDGET, IMAGE, 2.0)
    assert centred == QRectF(-320, -180, 1280, 720)
    assert image_rect(WIDGET, IMAGE, 2.0, QPointF(100, -50)).topLeft() == QPointF(
        -220, -230
    )
    assert image_rect(WIDGET, IMAGE, 2.0, QPointF(5000, 5000)).topLeft() == QPointF(0, 0)
    far = image_rect(WIDGET, IMAGE, 2.0, QPointF(-5000, -5000)).topLeft()
    assert far == QPointF(-640, -360)


def test_pan_is_ignored_along_an_axis_that_fits():
    rect = image_rect(QSize(640, 640), IMAGE, 1.5, QPointF(40, 500))
    assert rect.top() == pytest.approx((640 - 540) / 2)
    assert rect.left() == pytest.approx(-160 + 40)


def test_zoom_anchor_keeps_the_point_under_the_pointer():
    anchor = QPointF(160, 90)
    before = image_rect(WIDGET, IMAGE, 1.0, QPointF())
    point = ImageMapper(before, IMAGE).to_image(anchor)
    pan = anchored_pan(anchor, before, image_rect(WIDGET, IMAGE, 2.0))
    after = image_rect(WIDGET, IMAGE, 2.0, pan)
    assert ImageMapper(after, IMAGE).to_image(anchor) == pytest.approx(point)
    assert point == pytest.approx((320.0, 180.0))


def test_mapper_round_trips():
    mapper = ImageMapper(QRectF(-100, 20, 1280, 720), IMAGE)
    view = mapper.to_view((640.0, 360.0))
    assert (view.x(), view.y()) == (540.0, 380.0)
    assert mapper.to_image(view) == pytest.approx((640.0, 360.0))


def test_split_divider_position_and_limits():
    rect = QRectF(20, 0, 600, 300)
    assert split_position(rect, 0.5) == 320
    assert split_fraction(rect, 470) == pytest.approx(0.75)
    assert split_fraction(rect, -100) == 0.05
    assert split_fraction(rect, 900) == 0.95
