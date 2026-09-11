"""Tests for tower_borescope.measure.shapes: measurements, annotations and snapshots."""

from __future__ import annotations

import pytest

from tower_borescope.measure.shapes import (
    ANNOTATE_KINDS,
    MEASURE_KINDS,
    Annotation,
    Measurement,
    OverlaySnapshot,
)


def _measurement(kind, points):
    item = Measurement(kind)
    for point in points:
        item.add_point(point)
    return item


def test_distance_measurement():
    item = _measurement("distance", [(0, 0), (3, 4), (9, 9)])
    assert item.complete
    assert item.points == [(0.0, 0.0), (3.0, 4.0)]
    assert item.pixel_value() == 5.0
    assert item.label(None) == "5 px"
    assert item.label(2.0) == "10.00 mm"
    assert item.label(2.54, "in") == "0.500 in"
    assert item.anchor() == (1.5, 2.0)


def test_angle_measurement_uses_the_second_point_as_vertex():
    right = _measurement("angle", [(10, 0), (0, 0), (0, 10)])
    assert right.pixel_value() == pytest.approx(90.0)
    assert right.label(None) == "90.0°"
    assert right.anchor() == (0.0, 0.0)
    other_vertex = _measurement("angle", [(0, 0), (10, 0), (0, 10)])
    assert other_vertex.pixel_value() == pytest.approx(45.0)
    assert other_vertex.anchor() == (10.0, 0.0)


def test_area_measurement_closes_and_measures_the_polygon():
    item = _measurement("area", [(0, 0), (10, 0), (10, 10), (0, 10)])
    assert not item.complete
    item.closed = True
    assert item.complete
    item.add_point((50, 50))
    assert len(item.points) == 4
    assert item.pixel_value() == pytest.approx(100.0)
    assert item.label(None) == "100 px²"
    assert item.label(0.5) == "25.00 mm²"
    assert item.anchor() == (5.0, 5.0)


def test_incomplete_measurements_have_no_value_or_label():
    item = _measurement("angle", [(0, 0), (1, 1)])
    assert item.pixel_value() is None
    assert item.label(1.0) == ""
    assert Measurement("area").anchor() == (0.0, 0.0)


def test_kinds_are_validated():
    assert dict(MEASURE_KINDS) == {"distance": 2, "angle": 3, "area": 0}
    assert ANNOTATE_KINDS == ("arrow", "circle", "text", "freehand")
    with pytest.raises(ValueError, match="measurement"):
        Measurement("volume")
    with pytest.raises(ValueError, match="annotation"):
        Annotation("stamp")


def test_items_compare_by_identity():
    first = _measurement("distance", [(0, 0), (1, 1)])
    second = _measurement("distance", [(0, 0), (1, 1)])
    items = [first, second]
    items.remove(second)
    assert items == [first]


def test_annotation_defaults_and_overlay_snapshot():
    note = Annotation("text", [(4.0, 5.0)], "crack")
    assert Annotation("arrow").points == []
    assert Annotation("arrow").text == ""
    assert not OverlaySnapshot([], [], None, "mm").has_items
    assert OverlaySnapshot([], [note], 0.1, "in").has_items
    assert OverlaySnapshot([Measurement("area")], [], None, "mm").has_items
