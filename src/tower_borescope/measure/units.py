"""Length and area units: conversion of typed lengths and display formatting."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

MM_PER_INCH = 25.4
UNITS: Mapping[str, str] = MappingProxyType(
    {
        "mm": "Millimetres",
        "cm": "Centimetres",
        "in": "Inches (decimal)",
        "frac": "Inches (fractions)",
        "ftin": "Feet and inches",
    }
)

_MM_PER_UNIT: Mapping[str, float] = MappingProxyType(
    {"mm": 1.0, "cm": 10.0, "in": MM_PER_INCH, "frac": MM_PER_INCH, "ftin": MM_PER_INCH}
)
_UNIT_NAMES: Mapping[str, str] = MappingProxyType(
    {"mm": "mm", "cm": "cm", "in": "inches", "frac": "inches", "ftin": "inches"}
)
_INCH_UNITS = frozenset({"in", "frac", "ftin"})
_INCHES_PER_FOOT = 12
_SQ_IN_PER_SQ_FT = 144
_FRACTION_DENOMINATOR = 32
_FEET_FRACTION_DENOMINATOR = 16


def to_mm(value: float, unit: str) -> float:
    """Convert a length typed in ``unit`` to millimetres.

    Args:
        value: The typed length.
        unit: A key of :data:`UNITS`.

    Returns:
        The length in millimetres.

    Raises:
        KeyError: When ``unit`` is not a key of :data:`UNITS`.
    """
    return value * _MM_PER_UNIT[unit]


def unit_name(unit: str) -> str:
    """Name of the unit a length is typed in, such as "mm" or "inches".

    Args:
        unit: A key of :data:`UNITS`.

    Returns:
        The short unit name for input prompts.

    Raises:
        KeyError: When ``unit`` is not a key of :data:`UNITS`.
    """
    return _UNIT_NAMES[unit]


def _fraction(inches: float, denominator: int = _FRACTION_DENOMINATOR) -> str:
    """Inches as a reduced mixed fraction: 1.53 gives '1 17/32', 0.5 gives '1/2'."""
    whole = int(inches)
    numerator = round((inches - whole) * denominator)
    if numerator == denominator:
        whole, numerator = whole + 1, 0
    reduced = denominator
    while numerator and numerator % 2 == 0:
        numerator //= 2
        reduced //= 2
    if numerator == 0:
        return f"{whole}"
    return f"{whole} {numerator}/{reduced}" if whole else f"{numerator}/{reduced}"


def _feet_and_inches(mm: float) -> str:
    """Feet and inches to the nearest sixteenth, such as 1' 3"."""
    feet, remainder = divmod(mm / MM_PER_INCH, _INCHES_PER_FOOT)
    inches = _fraction(remainder, _FEET_FRACTION_DENOMINATOR)
    return f"{int(feet)}' {inches}\"" if feet >= 1 else f'{inches}"'


def format_length(mm: float, unit: str) -> str:
    """Format a length for display.

    Args:
        mm: Length in millimetres.
        unit: A key of :data:`UNITS`; unknown units format as millimetres.

    Returns:
        Text such as "12.70 mm", "1.27 cm", "0.500 in", '1/2"' or "1' 3\"".
    """
    if unit == "cm":
        return f"{mm / 10:.2f} cm"
    if unit == "in":
        return f"{mm / MM_PER_INCH:.3f} in"
    if unit == "frac":
        return _fraction(mm / MM_PER_INCH) + '"'
    if unit == "ftin":
        return _feet_and_inches(mm)
    return f"{mm:.2f} mm"


def format_area(mm2: float, unit: str) -> str:
    """Format an area for display.

    Args:
        mm2: Area in square millimetres.
        unit: A key of :data:`UNITS`; inch units give square inches, and feet and
            inches give square feet above 144 square inches.

    Returns:
        Text such as "12.00 mm²", "0.12 cm²", "0.019 sq in" or "1.500 sq ft".
    """
    if unit == "cm":
        return f"{mm2 / 100:.2f} cm²"
    if unit in _INCH_UNITS:
        sq_in = mm2 / MM_PER_INCH**2
        if unit == "ftin" and sq_in > _SQ_IN_PER_SQ_FT:
            return f"{sq_in / _SQ_IN_PER_SQ_FT:.3f} sq ft"
        return f"{sq_in:.3f} sq in"
    return f"{mm2:.2f} mm²"
