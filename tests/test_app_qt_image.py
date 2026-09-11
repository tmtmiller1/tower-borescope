"""Tests for tower_borescope.app.qt_image: channel order, size and buffer ownership."""

from __future__ import annotations

import gc

import numpy as np
from PySide6.QtGui import QColor, QImage

from synthetic import textured_frame
from tower_borescope.app.qt_image import to_qimage


def test_bgr_pixels_become_rgb(qapp):
    image = np.zeros((2, 3, 3), np.uint8)
    image[0, 0] = (255, 0, 0)
    image[1, 2] = (0, 0, 255)
    converted = to_qimage(image)
    assert (converted.width(), converted.height()) == (3, 2)
    assert converted.format() == QImage.Format.Format_RGB888
    assert QColor(converted.pixel(0, 0)) == QColor(0, 0, 255)
    assert QColor(converted.pixel(2, 1)) == QColor(255, 0, 0)


def test_odd_widths_keep_rows_aligned(qapp):
    image = np.zeros((3, 5, 3), np.uint8)
    image[:, 4] = (0, 255, 0)
    converted = to_qimage(image)
    assert all(QColor(converted.pixel(4, row)) == QColor(0, 255, 0) for row in range(3))
    assert all(QColor(converted.pixel(3, row)) == QColor(0, 0, 0) for row in range(3))


def test_image_owns_its_pixels(qapp):
    frame = textured_frame(64, 48)
    converted = to_qimage(frame)
    before = converted.pixel(10, 10)
    frame[:] = 0
    del frame
    gc.collect()
    assert converted.pixel(10, 10) == before


def test_non_contiguous_views_convert(qapp):
    frame = textured_frame(64, 48)
    view = frame[::2, ::2]
    converted = to_qimage(view)
    assert (converted.width(), converted.height()) == (32, 24)
    blue, green, red = (int(value) for value in view[5, 7])
    assert QColor(converted.pixel(7, 5)) == QColor(red, green, blue)
