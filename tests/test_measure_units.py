"""Tests for tower_borescope.measure.units: conversion and display formatting."""

from __future__ import annotations

import pytest

from tower_borescope.measure.units import (
    MM_PER_INCH,
    UNITS,
    format_area,
    format_length,
    to_mm,
    unit_name,
)


@pytest.mark.parametrize(
    ("mm", "unit", "text"),
    [
        (12.7, "mm", "12.70 mm"),
        (12.7, "cm", "1.27 cm"),
        (12.7, "in", "0.500 in"),
        (12.7, "frac", '1/2"'),
        (1.53 * MM_PER_INCH, "frac", '1 17/32"'),
        (76.2, "frac", '3"'),
        (25.37, "frac", '1"'),
        (381.0, "ftin", "1' 3\""),
        (311.15, "ftin", "1' 1/4\""),
        (101.6, "ftin", '4"'),
        (12.7, "unknown", "12.70 mm"),
    ],
)
def test_format_length(mm, unit, text):
    assert format_length(mm, unit) == text


@pytest.mark.parametrize(
    ("mm2", "unit", "text"),
    [
        (12.0, "mm", "12.00 mm²"),
        (12.0, "cm", "0.12 cm²"),
        (645.16, "in", "1.000 sq in"),
        (645.16, "frac", "1.000 sq in"),
        (645.16 * 100, "ftin", "100.000 sq in"),
        (645.16 * 216, "ftin", "1.500 sq ft"),
    ],
)
def test_format_area(mm2, unit, text):
    assert format_area(mm2, unit) == text


def test_to_mm_and_unit_names():
    assert abs(to_mm(1.5, "in") - 38.1) < 1e-9
    assert to_mm(2.0, "cm") == 20.0
    assert to_mm(3.0, "mm") == 3.0
    assert [unit_name(unit) for unit in UNITS] == [
        "mm",
        "cm",
        "inches",
        "inches",
        "inches",
    ]
    with pytest.raises(KeyError):
        to_mm(1.0, "furlong")


def test_units_have_display_names():
    assert list(UNITS) == ["mm", "cm", "in", "frac", "ftin"]
    assert UNITS["ftin"] == "Feet and inches"
