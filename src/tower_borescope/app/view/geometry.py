"""Zoom limits, pan clamping and mapping between widget and image coordinates.

The image is fitted inside the widget and scaled by the zoom factor. While the zoomed
image is larger than the widget, the pan offset moves it, clamped so no gap opens at
an edge; along an axis where it fits, it stays centred.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize

from tower_borescope.measure.shapes import Point

ZOOM_MIN = 1.0
ZOOM_MAX = 8.0
WHEEL_STEP_DEGREES = 120.0
WHEEL_ZOOM_BASE = 1.15
SPLIT_MIN = 0.05
SPLIT_MAX = 0.95


def clamp_zoom(zoom: float) -> float:
    """Limit a zoom factor to the range 1 to 8."""
    return max(ZOOM_MIN, min(ZOOM_MAX, zoom))


def wheel_zoom(zoom: float, angle_delta: float) -> float:
    """Zoom factor after a wheel movement, before clamping.

    Args:
        zoom: Current zoom factor.
        angle_delta: Vertical wheel angle in eighths of a degree, as Qt reports it.

    Returns:
        The zoom multiplied by 1.15 for each standard wheel step.
    """
    return float(zoom * WHEEL_ZOOM_BASE ** (angle_delta / WHEEL_STEP_DEGREES))


def _panned(offset: float, pan: float, view_extent: float, drawn_extent: float) -> float:
    """Offset moved by ``pan`` and clamped so the image covers the widget edge to edge."""
    if drawn_extent <= view_extent:
        return offset
    return min(0.0, max(view_extent - drawn_extent, offset + pan))


def image_rect(
    widget: QSize, image: QSize, zoom: float, pan: QPointF | None = None
) -> QRectF:
    """Where the image is drawn inside the widget.

    Args:
        widget: Widget size.
        image: Image size in pixels.
        zoom: Zoom factor.
        pan: Pan offset in widget pixels, or None for the centred layout without pan.

    Returns:
        The drawn rectangle in widget coordinates.
    """
    scale = min(widget.width() / image.width(), widget.height() / image.height()) * zoom
    drawn_w, drawn_h = image.width() * scale, image.height() * scale
    left = (widget.width() - drawn_w) / 2
    top = (widget.height() - drawn_h) / 2
    if pan is not None:
        left = _panned(left, pan.x(), widget.width(), drawn_w)
        top = _panned(top, pan.y(), widget.height(), drawn_h)
    return QRectF(left, top, drawn_w, drawn_h)


def anchored_pan(anchor: QPointF, before: QRectF, after: QRectF) -> QPointF:
    """Pan offset that keeps the image point under ``anchor`` in place across a zoom.

    Args:
        anchor: Widget position, normally the mouse pointer.
        before: Drawn rectangle at the old zoom.
        after: Drawn rectangle at the new zoom without pan.

    Returns:
        The pan offset for the new zoom.
    """
    rel_x = (anchor.x() - before.left()) / before.width()
    rel_y = (anchor.y() - before.top()) / before.height()
    return QPointF(
        anchor.x() - rel_x * after.width() - after.left(),
        anchor.y() - rel_y * after.height() - after.top(),
    )


def split_position(rect: QRectF, split: float) -> float:
    """Widget x coordinate of the split-compare divider.

    Args:
        rect: Drawn image rectangle.
        split: Divider position as a fraction of the image width.

    Returns:
        The divider's x coordinate.
    """
    return rect.left() + rect.width() * split


def split_fraction(rect: QRectF, x: float) -> float:
    """Divider fraction for a widget x coordinate, kept between 0.05 and 0.95."""
    return min(SPLIT_MAX, max(SPLIT_MIN, (x - rect.left()) / rect.width()))


@dataclass(frozen=True, slots=True)
class ImageMapper:
    """Converts between widget positions and image pixel coordinates.

    Attributes:
        rect: Drawn image rectangle in widget coordinates.
        image: Image size in pixels.
    """

    rect: QRectF
    image: QSize

    def to_image(self, pos: QPointF) -> Point:
        """Image pixel coordinates under a widget position."""
        rect = self.rect
        return (
            (pos.x() - rect.left()) / rect.width() * self.image.width(),
            (pos.y() - rect.top()) / rect.height() * self.image.height(),
        )

    def to_view(self, point: Point) -> QPointF:
        """Widget position of an image pixel coordinate."""
        rect = self.rect
        return QPointF(
            rect.left() + point[0] / self.image.width() * rect.width(),
            rect.top() + point[1] / self.image.height() * rect.height(),
        )
