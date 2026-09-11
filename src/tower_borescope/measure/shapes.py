"""Measurements, annotations and the overlay snapshot handed to rendering.

Geometry is stored in image pixel coordinates. The view draws it scaled to the widget,
and :mod:`tower_borescope.measure.render` burns it into a frame for saving.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np

from tower_borescope.measure.units import format_area, format_length

type Point = tuple[float, float]

MEASURE_KINDS: Mapping[str, int] = MappingProxyType(
    {"distance": 2, "angle": 3, "area": 0}
)
ANNOTATE_KINDS: tuple[str, ...] = ("arrow", "circle", "text", "freehand")

_MIN_POINTS: Mapping[str, int] = MappingProxyType({"distance": 2, "angle": 3, "area": 3})
_VERTEX_INDEX = 1
_MIN_NORM = 1e-9


def _distance(points: Sequence[Point]) -> float:
    """Length between the first two points."""
    return math.dist(points[0], points[1])


def _angle(points: Sequence[Point]) -> float:
    """Angle in degrees at the second point, between the first and third."""
    first, vertex, last = (np.array(point) for point in points[:3])
    arm_a, arm_b = first - vertex, last - vertex
    norms = max(float(np.linalg.norm(arm_a) * np.linalg.norm(arm_b)), _MIN_NORM)
    cosine = float(np.dot(arm_a, arm_b)) / norms
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _area(points: Sequence[Point]) -> float:
    """Polygon area by the shoelace formula."""
    xs = np.array([point[0] for point in points])
    ys = np.array([point[1] for point in points])
    return 0.5 * abs(float(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1))))


_MEASURERS: Mapping[str, Callable[[Sequence[Point]], float]] = MappingProxyType(
    {"distance": _distance, "angle": _angle, "area": _area}
)


@dataclass(eq=False)
class Measurement:
    """A distance, angle or area measurement built point by point.

    Instances compare by identity, so an overlay list can remove one of two
    measurements with identical points.

    Attributes:
        kind: A key of :data:`MEASURE_KINDS`.
        points: Clicked points in image pixels. For an angle the second is the vertex.
        closed: Whether an area outline has been closed.
    """

    kind: str
    points: list[Point] = field(default_factory=list)
    closed: bool = False

    def __post_init__(self) -> None:
        """Reject kinds outside :data:`MEASURE_KINDS`."""
        if self.kind not in MEASURE_KINDS:
            raise ValueError(f"unknown measurement kind: {self.kind}")

    @property
    def complete(self) -> bool:
        """True once enough points are placed, or once an area is closed."""
        need = MEASURE_KINDS[self.kind]
        return self.closed if need == 0 else len(self.points) >= need

    def add_point(self, point: Point) -> None:
        """Append a point unless the measurement is already complete."""
        if not self.complete:
            self.points.append((float(point[0]), float(point[1])))

    def pixel_value(self) -> float | None:
        """Pixel length, angle in degrees, or square-pixel area; None until measurable."""
        if len(self.points) < _MIN_POINTS[self.kind]:
            return None
        return _MEASURERS[self.kind](self.points)

    def label(self, mm_per_px: float | None, unit: str = "mm") -> str:
        """Display text for the measurement.

        Args:
            mm_per_px: Image scale, or None to report pixels.
            unit: A key of :data:`tower_borescope.measure.units.UNITS`.

        Returns:
            Text such as "12.70 mm", "45.0°" or "300 px", or an empty string while
            there are too few points.
        """
        value = self.pixel_value()
        if value is None:
            return ""
        if self.kind == "angle":
            return f"{value:.1f}°"
        if self.kind == "distance":
            return (
                format_length(value * mm_per_px, unit) if mm_per_px else f"{value:.0f} px"
            )
        if mm_per_px:
            return format_area(value * mm_per_px * mm_per_px, unit)
        return f"{value:.0f} px²"

    def anchor(self) -> Point:
        """Where the label goes: the vertex of an angle, otherwise the centroid."""
        if self.kind == "angle" and len(self.points) > _VERTEX_INDEX:
            return self.points[_VERTEX_INDEX]
        if not self.points:
            return (0.0, 0.0)
        centre = np.mean(self.points, axis=0)
        return (float(centre[0]), float(centre[1]))


@dataclass(eq=False)
class Annotation:
    """An arrow, circle, text note or freehand stroke.

    Attributes:
        kind: A name from :data:`ANNOTATE_KINDS`.
        points: Points in image pixels. Arrows and circles use the first and last.
        text: Note text for the "text" kind.
    """

    kind: str
    points: list[Point] = field(default_factory=list)
    text: str = ""

    def __post_init__(self) -> None:
        """Reject kinds outside :data:`ANNOTATE_KINDS`."""
        if self.kind not in ANNOTATE_KINDS:
            raise ValueError(f"unknown annotation kind: {self.kind}")


@dataclass(frozen=True)
class OverlaySnapshot:
    """Everything needed to draw the measurement overlay onto a frame.

    Attributes:
        measurements: Measurements to draw.
        annotations: Annotations to draw.
        mm_per_px: Image scale for labels, or None to label in pixels.
        unit: A key of :data:`tower_borescope.measure.units.UNITS`.
    """

    measurements: list[Measurement]
    annotations: list[Annotation]
    mm_per_px: float | None
    unit: str

    @property
    def has_items(self) -> bool:
        """True when there is at least one measurement or annotation."""
        return bool(self.measurements or self.annotations)
