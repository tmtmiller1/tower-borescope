"""Glare compression and the alternative display looks for the live view."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import lru_cache
from types import MappingProxyType
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from tower_borescope.image_types import BgrImage

VIEW_MODES: tuple[str, ...] = ("Normal", "Grayscale", "Inverted", "Edges", "Outline")

_GLARE_KNEE = 170.0
_GLARE_SLOPE = 0.7
_GLARE_CURVE = 0.15
_GLARE_CACHE_SIZE = 32
_OUTLINE_DIM = 0.18
_OUTLINE_MIN_POINTS = 12
_OUTLINE_EPSILON = 1.5
_OUTLINE_LONG_PX = 120
_OUTLINE_COLOR = (255, 200, 40)
_OUTLINE_LONG_COLOR = (255, 240, 120)
_EDGES_DIM = 0.35
_EDGES_COLOR = (0, 230, 255)


@lru_cache(maxsize=_GLARE_CACHE_SIZE)
def _glare_lut(amount: float) -> NDArray[np.uint8]:
    """Read-only 256-entry lookup table compressing levels above the knee."""
    levels = np.arange(256, dtype=np.float32)
    over = np.maximum(levels - _GLARE_KNEE, 0)
    compressed = (
        _GLARE_KNEE
        + over * (1 - _GLARE_SLOPE * amount)
        - (over**2 / (255 - _GLARE_KNEE)) * _GLARE_CURVE * amount
    )
    curve = np.where(levels > _GLARE_KNEE, compressed, levels)
    lut = np.clip(curve, 0, 255).astype(np.uint8)
    lut.setflags(write=False)
    return lut


def glare_reduce(image: BgrImage, amount: float) -> BgrImage:
    """Compress highlights above a knee so the LED hotspot stops clipping to white.

    Levels up to 170 pass through unchanged. Lookup tables are cached per amount,
    rounded to two decimals.

    Args:
        image: BGR frame.
        amount: Compression strength from 0 to 1; 0 or less returns ``image`` itself.

    Returns:
        The frame with highlights compressed.
    """
    rounded = round(float(amount), 2)
    if rounded <= 0:
        return image
    return cast(BgrImage, cv2.LUT(image, _glare_lut(rounded)))


def outline(image: BgrImage) -> BgrImage:
    """Trace the picture as clean polylines over a darkened copy.

    Args:
        image: BGR frame.

    Returns:
        A new frame with contours drawn; long contours are drawn thicker and brighter.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.bilateralFilter(gray, 7, 40, 7), 40, 110)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    canvas = (image * _OUTLINE_DIM).astype(np.uint8)
    polylines = [
        cv2.approxPolyDP(contour, _OUTLINE_EPSILON, False)
        for contour in contours
        if len(contour) >= _OUTLINE_MIN_POINTS
    ]
    cv2.polylines(canvas, polylines, False, _OUTLINE_COLOR, 1, cv2.LINE_AA)
    long_lines = [
        line for line in polylines if cv2.arcLength(line, False) > _OUTLINE_LONG_PX
    ]
    cv2.polylines(canvas, long_lines, False, _OUTLINE_LONG_COLOR, 2, cv2.LINE_AA)
    return canvas


def _grayscale(image: BgrImage) -> BgrImage:
    """Three-channel grayscale copy."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cast(BgrImage, cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))


def _inverted(image: BgrImage) -> BgrImage:
    """Photographic negative."""
    return cast(BgrImage, cv2.bitwise_not(image))


def _edges(image: BgrImage) -> BgrImage:
    """Canny edges painted over a darkened copy."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (0, 0), 1.2), 50, 130)
    canvas = (image * _EDGES_DIM).astype(np.uint8)
    canvas[edges > 0] = _EDGES_COLOR
    return canvas


_FILTERS: Mapping[str, Callable[[BgrImage], BgrImage]] = MappingProxyType(
    {"Grayscale": _grayscale, "Inverted": _inverted, "Edges": _edges, "Outline": outline}
)


def apply_view_mode(image: BgrImage, mode: str) -> BgrImage:
    """Render a frame in one of :data:`VIEW_MODES`.

    Args:
        image: BGR frame.
        mode: A name from :data:`VIEW_MODES`; "Normal" and unknown names change nothing.

    Returns:
        The rendered frame, or ``image`` itself for "Normal".
    """
    view_filter = _FILTERS.get(mode)
    return image if view_filter is None else view_filter(image)
