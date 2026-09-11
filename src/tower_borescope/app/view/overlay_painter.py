"""Drawing of measurements and annotations over the video.

Measurements are yellow with point markers and a label badge. When the image is
calibrated but the focus no longer matches the calibration, length and area labels
get an approximation marker and a warning note.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from tower_borescope.app.view.badges import draw_badge, shade
from tower_borescope.app.view.geometry import ImageMapper
from tower_borescope.app.view.tools import AREA_TOOL
from tower_borescope.measure.shapes import Annotation, Measurement

if TYPE_CHECKING:
    from tower_borescope.app.view.video_view import VideoView

MEASURE_COLOR = "#ffd400"
ANNOTATE_COLOR = "#ff5a3c"
AREA_FILL = QColor(255, 212, 0, 40)
DOUBT_BACKGROUND = QColor(120, 70, 0, 200)
LABEL_ALPHA = 180
MEASURE_PEN_WIDTH = 2.0
ANNOTATE_PEN_WIDTH = 2.5
POINT_RADIUS = 4.0
LABEL_OFFSET_X = 8.0
LABEL_OFFSET_Y = 30.0
LABEL_FONT_SIZE = 12
NOTE_FONT_SIZE = 13
ARROW_HEAD = 14.0
ARROW_SPREAD = 0.6
MIN_ARROW_LENGTH = 1e-6
MIN_LINE_POINTS = 2
ANGLE_KIND = "angle"
DOUBT_MARKER = "≈ "
DOUBT_NOTE = "  (focus differs from calibration)"

type Drawer = Callable[[QPainter, list[QPointF], Annotation], None]


def is_doubtful(mm_per_px: float | None, scale_ok: bool | None, kind: str) -> bool:
    """Whether a measurement label is uncertain because focus left the calibration.

    Args:
        mm_per_px: Image scale, or None when uncalibrated.
        scale_ok: Focus lock result: True, False, or None when unknown.
        kind: Measurement kind; angles do not depend on the scale.

    Returns:
        True for calibrated lengths and areas while the focus lock fails.
    """
    return bool(mm_per_px) and scale_ok is False and kind != ANGLE_KIND


def measurement_text(label: str, doubtful: bool) -> str:
    """Label text, marked as approximate when ``doubtful``."""
    return f"{DOUBT_MARKER}{label}{DOUBT_NOTE}" if doubtful else label


def paint_overlays(view: VideoView, painter: QPainter, mapper: ImageMapper) -> None:
    """Draw finished and in-progress measurements, then annotations.

    Args:
        view: Widget being painted.
        painter: Active painter on ``view``.
        mapper: Image to widget coordinate mapping.
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    overlays = view.overlays
    current = overlays.current
    measurements = list(overlays.measurements)
    if isinstance(current, Measurement):
        measurements.append(current)
    for item in measurements:
        _paint_measurement(view, painter, mapper, item)
    notes = list(overlays.annotations)
    if isinstance(current, Annotation):
        notes.append(current)
    for note in notes:
        paint_annotation(painter, mapper, note)


def paint_annotation(painter: QPainter, mapper: ImageMapper, note: Annotation) -> None:
    """Draw one arrow, circle, freehand stroke or text note.

    Args:
        painter: Active painter.
        mapper: Image to widget coordinate mapping.
        note: Annotation to draw.
    """
    painter.setPen(QPen(QColor(ANNOTATE_COLOR), ANNOTATE_PEN_WIDTH))
    drawer = _ANNOTATION_DRAWERS.get(note.kind)
    if drawer is not None:
        drawer(painter, [mapper.to_view(point) for point in note.points], note)


def draw_arrow(painter: QPainter, start: QPointF, end: QPointF) -> None:
    """Line from ``start`` to ``end`` with a filled head in the pen color.

    Args:
        painter: Active painter.
        start: Tail position.
        end: Head position.
    """
    painter.drawLine(start, end)
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = max(math.hypot(dx, dy), MIN_ARROW_LENGTH)
    ux, uy = dx / length, dy / length
    left = QPointF(
        end.x() - ARROW_HEAD * (ux - uy * ARROW_SPREAD),
        end.y() - ARROW_HEAD * (uy + ux * ARROW_SPREAD),
    )
    right = QPointF(
        end.x() - ARROW_HEAD * (ux + uy * ARROW_SPREAD),
        end.y() - ARROW_HEAD * (uy - ux * ARROW_SPREAD),
    )
    head = QPainterPath(end)
    head.lineTo(left)
    head.lineTo(right)
    head.closeSubpath()
    painter.fillPath(head, painter.pen().color())


def _paint_measurement(
    view: VideoView, painter: QPainter, mapper: ImageMapper, item: Measurement
) -> None:
    """Lines, point markers and label of one measurement."""
    color = QColor(MEASURE_COLOR)
    points = [mapper.to_view(point) for point in item.points]
    preview = list(points)
    hover = view.overlays.hover
    if item is view.overlays.current and hover is not None:
        preview.append(mapper.to_view(hover))
    painter.setPen(QPen(color, MEASURE_PEN_WIDTH))
    _paint_measure_path(painter, item, preview)
    painter.setBrush(color)
    for point in points:
        painter.drawEllipse(point, POINT_RADIUS, POINT_RADIUS)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _paint_measure_label(view, painter, mapper, item)


def _paint_measure_path(
    painter: QPainter, item: Measurement, preview: Sequence[QPointF]
) -> None:
    """Area outline, filled once closed, or the segments between points."""
    if item.kind == AREA_TOOL and len(preview) >= MIN_LINE_POINTS:
        polygon = QPolygonF(list(preview))
        if item.closed:
            painter.setBrush(AREA_FILL)
            painter.drawPolygon(polygon)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.drawPolyline(polygon)
        return
    for start, end in itertools.pairwise(preview):
        painter.drawLine(start, end)


def _paint_measure_label(
    view: VideoView, painter: QPainter, mapper: ImageMapper, item: Measurement
) -> None:
    """Label badge next to a completed measurement."""
    label = item.label(view.mm_per_px, view.unit)
    if not label or not item.complete:
        return
    anchor = mapper.to_view(item.anchor())
    doubtful = is_doubtful(view.mm_per_px, view.scale_ok, item.kind)
    background = DOUBT_BACKGROUND if doubtful else shade(LABEL_ALPHA)
    origin = QPointF(anchor.x() + LABEL_OFFSET_X, anchor.y() - LABEL_OFFSET_Y)
    text = measurement_text(label, doubtful)
    draw_badge(painter, text, origin, background, LABEL_FONT_SIZE)


def _draw_arrow_note(painter: QPainter, points: list[QPointF], note: Annotation) -> None:
    """Arrow from the first point to the last."""
    if len(points) >= MIN_LINE_POINTS:
        draw_arrow(painter, points[0], points[-1])


def _draw_circle_note(painter: QPainter, points: list[QPointF], note: Annotation) -> None:
    """Circle centred on the first point through the last."""
    if len(points) >= MIN_LINE_POINTS:
        centre, edge = points[0], points[-1]
        radius = math.hypot(centre.x() - edge.x(), centre.y() - edge.y())
        painter.drawEllipse(centre, radius, radius)


def _draw_freehand_note(
    painter: QPainter, points: list[QPointF], note: Annotation
) -> None:
    """Open polyline through every point."""
    if len(points) >= MIN_LINE_POINTS:
        painter.drawPolyline(QPolygonF(points))


def _draw_text_note(painter: QPainter, points: list[QPointF], note: Annotation) -> None:
    """Note text badge at the first point."""
    if points:
        draw_badge(painter, note.text, points[0], shade(LABEL_ALPHA), NOTE_FONT_SIZE)


_ANNOTATION_DRAWERS: Mapping[str, Drawer] = MappingProxyType(
    {
        "arrow": _draw_arrow_note,
        "circle": _draw_circle_note,
        "freehand": _draw_freehand_note,
        "text": _draw_text_note,
    }
)
