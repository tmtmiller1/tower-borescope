"""Sharpening and the enhance filter for live frames and stacked stills."""

from __future__ import annotations

from functools import cache
from typing import cast

import cv2

from tower_borescope.image_types import BgrImage

_CLAHE_CLIP_LIMIT = 1.2
_CLAHE_TILES = (16, 16)
_BILATERAL_DIAMETER = 7
_BILATERAL_SIGMA_COLOR = 40
_BILATERAL_SIGMA_SPACE = 7
_STILL_AMOUNT = 0.8
_STILL_SIGMA = 1.5


@cache
def _clahe() -> cv2.CLAHE:
    """Shared contrast-limited adaptive histogram equalizer, created on first use."""
    return cv2.createCLAHE(clipLimit=_CLAHE_CLIP_LIMIT, tileGridSize=_CLAHE_TILES)


def unsharp(image: BgrImage, amount: float = 0.4, sigma: float = 1.6) -> BgrImage:
    """Sharpen by subtracting a Gaussian-blurred copy.

    Args:
        image: BGR image.
        amount: Strength of the sharpening; 0 returns an unchanged copy.
        sigma: Gaussian blur radius in pixels.

    Returns:
        The sharpened image.
    """
    blurred = cv2.GaussianBlur(image, (0, 0), sigma)
    return cast(BgrImage, cv2.addWeighted(image, 1 + amount, blurred, -amount, 0))


def enhance(image: BgrImage) -> BgrImage:
    """Soften JPEG blocking and noise, lift local contrast slightly, then sharpen.

    The settings come from measuring 8 by 8 block edges against retained detail and cost
    about 13 ms at 720p.

    Args:
        image: BGR frame.

    Returns:
        The enhanced frame.
    """
    smoothed = cv2.bilateralFilter(
        image, _BILATERAL_DIAMETER, _BILATERAL_SIGMA_COLOR, _BILATERAL_SIGMA_SPACE
    )
    lum, chroma_a, chroma_b = cv2.split(cv2.cvtColor(smoothed, cv2.COLOR_BGR2LAB))
    merged = cv2.merge((_clahe().apply(lum), chroma_a, chroma_b))
    return unsharp(cast(BgrImage, cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)))


def finish_still(image: BgrImage, enhanced: bool) -> BgrImage:
    """Final sharpening for a stacked still.

    Args:
        image: Stacked, graded still.
        enhanced: Whether the enhance filter is on for the live view.

    Returns:
        The enhanced still, or a stronger unsharp mask when enhance is off.
    """
    if enhanced:
        return enhance(image)
    return unsharp(image, _STILL_AMOUNT, _STILL_SIGMA)
