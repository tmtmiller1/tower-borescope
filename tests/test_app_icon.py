"""Tests for tower_borescope.app.icon: the drawn lens icon and its PNG."""

from __future__ import annotations

import cv2
import numpy as np

from tower_borescope.app.icon import draw_icon, write_icon_png


def test_icon_is_square_bgra():
    icon = draw_icon()
    assert icon.shape == (1024, 1024, 4)
    assert icon.dtype == np.uint8


def test_alpha_is_transparent_outside_and_opaque_on_the_lens():
    icon = draw_icon()
    assert icon[0, 0, 3] == 0
    assert icon[115, 115, 3] == 0
    assert icon[512, 512, 3] == 255
    assert icon[150, 512, 3] == 255
    assert icon[420, 420, 3] == 200
    assert tuple(icon[512, 512, :3]) == (90, 70, 50)


def test_drawing_is_deterministic_and_scales():
    assert np.array_equal(draw_icon(), draw_icon())
    small = draw_icon(64)
    assert small.shape == (64, 64, 4)
    assert small[32, 32, 3] == 255
    assert small[0, 0, 3] == 0


def test_write_icon_png_round_trips(tmp_path):
    target = tmp_path / "build" / "icon.png"
    written = write_icon_png(target, size=128)
    assert written == target
    loaded = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
    assert loaded is not None
    assert np.array_equal(loaded, draw_icon(128))
