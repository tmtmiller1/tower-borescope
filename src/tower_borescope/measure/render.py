"""Burning measurements and annotations into a frame for saving."""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

import cv2
import numpy as np

from tower_borescope.image_types import BgrImage
from tower_borescope.measure.shapes import Annotation, Measurement, OverlaySnapshot, Point

type Pixel = tuple[int, int]
type Color = tuple[int, int, int]

COLORS: Mapping[str, Color] = MappingProxyType(
    {"measure": (0, 220, 255), "annotate": (60, 90, 255), "text": (255, 255, 255)}
)

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_BASE_THICKNESS = 2
_BASE_FONT_SCALE = 0.6
_TEXT_FONT_FACTOR = 1.1
_DOT_EXTRA_RADIUS = 2
_LABEL_OFFSET = 8
_LABEL_PAD = 4
_LABEL_BASELINE_PAD = 2
_ARROW_TIP = 0.2
_LABEL_BACKGROUND = (0, 0, 0)


@dataclass(frozen=True)
class _Style:
    """Line thickness, font size and coordinate scale for one render."""

    scale: float
    thickness: int
    font_scale: float

    def pixel(self, point: Point) -> Pixel:
        """Image coordinates scaled to integer pixels of the output frame."""
        return round(point[0] * self.scale), round(point[1] * self.scale)


def _label(
    canvas: BgrImage, text: str, origin: Pixel, font_scale: float, color: Color
) -> None:
    """Draw text on a solid black box."""
    (width, height), baseline = cv2.getTextSize(text, _FONT, font_scale, 1)
    left, bottom = origin
    top_left = (left - _LABEL_PAD, bottom - height - _LABEL_PAD)
    bottom_right = (left + width + _LABEL_PAD, bottom + baseline + _LABEL_BASELINE_PAD)
    cv2.rectangle(canvas, top_left, bottom_right, _LABEL_BACKGROUND, -1)
    cv2.putText(canvas, text, origin, _FONT, font_scale, color, 1, cv2.LINE_AA)


def _draw_measurement(
    canvas: BgrImage, item: Measurement, overlay: OverlaySnapshot, style: _Style
) -> None:
    """Draw one measurement's lines, point markers and label."""
    pixels = [style.pixel(point) for point in item.points]
    color = COLORS["measure"]
    if item.kind == "area" and len(pixels) >= 2:
        outline = np.array(pixels, dtype=np.int32)
        cv2.polylines(canvas, [outline], item.closed, color, style.thickness, cv2.LINE_AA)
    else:
        for start, end in itertools.pairwise(pixels):
            cv2.line(canvas, start, end, color, style.thickness, cv2.LINE_AA)
    radius = style.thickness + _DOT_EXTRA_RADIUS
    for pixel in pixels:
        cv2.circle(canvas, pixel, radius, color, -1, cv2.LINE_AA)
    text = item.label(overlay.mm_per_px, overlay.unit)
    if text:
        anchor_x, anchor_y = style.pixel(item.anchor())
        origin = (anchor_x + _LABEL_OFFSET, anchor_y - _LABEL_OFFSET)
        _label(canvas, text, origin, style.font_scale, color)


def _draw_arrow(
    canvas: BgrImage, note: Annotation, pixels: list[Pixel], style: _Style
) -> None:
    """Arrow from the first point to the last."""
    if len(pixels) >= 2:
        cv2.arrowedLine(
            canvas,
            pixels[0],
            pixels[-1],
            COLORS["annotate"],
            style.thickness,
            cv2.LINE_AA,
            tipLength=_ARROW_TIP,
        )


def _draw_circle(
    canvas: BgrImage, note: Annotation, pixels: list[Pixel], style: _Style
) -> None:
    """Circle centred on the first point through the last."""
    if len(pixels) >= 2:
        radius = max(int(math.dist(pixels[0], pixels[-1])), 1)
        color = COLORS["annotate"]
        cv2.circle(canvas, pixels[0], radius, color, style.thickness, cv2.LINE_AA)


def _draw_freehand(
    canvas: BgrImage, note: Annotation, pixels: list[Pixel], style: _Style
) -> None:
    """Open polyline through every point."""
    if len(pixels) >= 2:
        stroke = np.array(pixels, dtype=np.int32)
        color = COLORS["annotate"]
        cv2.polylines(canvas, [stroke], False, color, style.thickness, cv2.LINE_AA)


def _draw_text(
    canvas: BgrImage, note: Annotation, pixels: list[Pixel], style: _Style
) -> None:
    """Note text at the first point."""
    if pixels:
        font_scale = style.font_scale * _TEXT_FONT_FACTOR
        _label(canvas, note.text, pixels[0], font_scale, COLORS["text"])


_ANNOTATION_DRAWERS: Mapping[
    str, Callable[[BgrImage, Annotation, list[Pixel], _Style], None]
] = MappingProxyType(
    {
        "arrow": _draw_arrow,
        "circle": _draw_circle,
        "freehand": _draw_freehand,
        "text": _draw_text,
    }
)


def render_overlay(
    image: BgrImage, overlay: OverlaySnapshot, scale: float = 1.0
) -> BgrImage:
    """Draw measurements and annotations onto a copy of a frame.

    Args:
        image: BGR frame. It is never modified.
        overlay: Items to draw, with the scale and unit for labels.
        scale: Output pixels per stored image pixel, for example 2 for stacked stills.

    Returns:
        A new frame with the overlay drawn.
    """
    canvas = image.copy()
    style = _Style(
        scale=scale,
        thickness=max(1, round(_BASE_THICKNESS * scale)),
        font_scale=_BASE_FONT_SCALE * scale,
    )
    for item in overlay.measurements:
        _draw_measurement(canvas, item, overlay, style)
    for note in overlay.annotations:
        drawer = _ANNOTATION_DRAWERS.get(note.kind)
        if drawer is not None:
            drawer(canvas, note, [style.pixel(point) for point in note.points], style)
    return canvas
