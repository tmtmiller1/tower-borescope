"""Tests for tower_borescope.app.frame_info: field order, defaults and slots."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtGui import QImage

from tower_borescope.app.frame_info import FrameInfo


def _image():
    return QImage(4, 3, QImage.Format.Format_RGB888)


def test_defaults_leave_meters_empty(qapp):
    image = _image()
    info = FrameInfo(image)
    assert info.image is image
    assert info.focus is None
    assert info.focus_raw is None
    assert info.hist is None
    assert info.clipped == 0.0
    assert info.motion == 0.0


def test_positional_order_matches_the_contract(qapp):
    hist = np.ones(64, np.float32)
    info = FrameInfo(_image(), 0.5, 120.0, hist, 0.1, 3.0)
    assert (info.focus, info.focus_raw, info.clipped, info.motion) == (
        0.5,
        120.0,
        0.1,
        3.0,
    )
    assert info.hist is hist


def test_readings_can_be_filled_in_later(qapp):
    info = FrameInfo(_image())
    info.focus = 0.9
    info.hist = np.zeros(8, np.float32)
    assert info.focus == 0.9
    assert info.hist.shape == (8,)


def test_unknown_fields_are_rejected(qapp):
    info = FrameInfo(_image())
    with pytest.raises(AttributeError):
        info.brightness = 3
