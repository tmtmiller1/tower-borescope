"""Tests for tower_borescope.measure.render: overlay drawing onto frames."""

from __future__ import annotations

import numpy as np

from tower_borescope.measure.render import COLORS, render_overlay
from tower_borescope.measure.shapes import Annotation, Measurement, OverlaySnapshot


def _blank(size=200):
    return np.zeros((size, size, 3), np.uint8)


def _snapshot(measurements=(), annotations=(), mm_per_px=None):
    return OverlaySnapshot(list(measurements), list(annotations), mm_per_px, "mm")


def _changed(before, after, rows, cols):
    return bool(np.any(before[rows, cols] != after[rows, cols]))


def test_measurements_draw_where_their_shapes_are():
    frame = _blank()
    distance = Measurement("distance", [(20.0, 150.0), (180.0, 150.0)])
    area = Measurement("area", [(30.0, 30.0), (90.0, 30.0), (90.0, 90.0)], closed=True)
    drawn = render_overlay(frame, _snapshot([distance, area], mm_per_px=0.1))
    assert drawn is not frame
    assert not frame.any()
    assert tuple(drawn[150, 60]) == COLORS["measure"]
    assert tuple(drawn[30, 60]) == COLORS["measure"]
    assert not drawn[180:, :].any()
    assert _changed(frame, drawn, slice(120, 142), slice(100, 170))


def test_annotations_draw_where_their_shapes_are():
    frame = _blank(300)
    notes = [
        Annotation("arrow", [(20.0, 20.0), (120.0, 20.0)]),
        Annotation("circle", [(220.0, 60.0), (250.0, 60.0)]),
        Annotation("freehand", [(20.0, 200.0), (60.0, 220.0), (100.0, 200.0)]),
        Annotation("text", [(150.0, 280.0)], "crack"),
    ]
    drawn = render_overlay(frame, _snapshot(annotations=notes))
    assert tuple(drawn[20, 70]) == COLORS["annotate"]
    assert tuple(drawn[60, 250]) == COLORS["annotate"]
    assert _changed(frame, drawn, slice(195, 225), slice(20, 100))
    assert _changed(frame, drawn, slice(260, 290), slice(150, 220))
    assert not drawn[100:180, 100:200].any()


def test_scale_maps_stored_coordinates_to_output_pixels():
    frame = _blank(400)
    line = Measurement("distance", [(50.0, 50.0), (150.0, 50.0)])
    drawn = render_overlay(frame, _snapshot([line]), scale=2.0)
    assert tuple(drawn[100, 200]) == COLORS["measure"]
    assert not drawn[50, 100:300].any()


def test_empty_overlay_returns_an_unchanged_copy():
    frame = _blank()
    frame[10, 10] = (1, 2, 3)
    drawn = render_overlay(frame, _snapshot())
    assert drawn is not frame
    assert np.array_equal(drawn, frame)
