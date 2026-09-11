"""Application icon drawn by code: a camera lens on a rounded dark square.

No image file is stored in the repository. The build script writes the PNG with
:func:`write_icon_png` and converts it to an icon set; the running application draws
the same image for its window icon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

DEFAULT_SIZE: Final = 1024
BASE_SIZE: Final = 1024.0
SQUARE_MARGIN: Final = 110
CORNER_RADIUS: Final = 90
LENS_RADII: Final = (300, 230, 150)
HIGHLIGHT_CENTRE: Final = 420
HIGHLIGHT_RADIUS: Final = 60
SQUARE_COLOR: Final = (34, 32, 28, 255)
LENS_COLORS: Final = ((214, 111, 59, 255), (52, 40, 30, 255), (90, 70, 50, 255))
HIGHLIGHT_COLOR: Final = (255, 255, 255, 200)
FILLED: Final = -1

type BgraImage = NDArray[np.uint8]


def _scaled(value: float, size: int) -> int:
    """A coordinate of the 1024-pixel design scaled to ``size`` pixels."""
    return round(value * size / BASE_SIZE)


def _rounded_square_mask(size: int) -> NDArray[np.uint8]:
    """Mask of the rounded square that clips the icon background."""
    mask = np.zeros((size, size), np.uint8)
    low = _scaled(SQUARE_MARGIN, size)
    high = _scaled(BASE_SIZE - SQUARE_MARGIN, size)
    corner = _scaled(CORNER_RADIUS, size)
    cv2.rectangle(mask, (low + corner, low), (high - corner, high), 255, FILLED)
    cv2.rectangle(mask, (low, low + corner), (high, high - corner), 255, FILLED)
    for cx in (low + corner, high - corner):
        for cy in (low + corner, high - corner):
            cv2.circle(mask, (cx, cy), corner, 255, FILLED)
    return mask


def draw_icon(size: int = DEFAULT_SIZE) -> BgraImage:
    """Draw the lens icon.

    Args:
        size: Width and height in pixels.

    Returns:
        A ``size`` by ``size`` BGRA image with a transparent surround.
    """
    image = np.zeros((size, size, 4), np.uint8)
    low = _scaled(SQUARE_MARGIN, size)
    high = _scaled(BASE_SIZE - SQUARE_MARGIN, size)
    cv2.rectangle(image, (low, low), (high, high), SQUARE_COLOR, FILLED)
    image[_rounded_square_mask(size) == 0] = 0
    centre = (size // 2, size // 2)
    for radius, color in zip(LENS_RADII, LENS_COLORS, strict=True):
        cv2.circle(image, centre, _scaled(radius, size), color, FILLED)
    highlight = _scaled(HIGHLIGHT_CENTRE, size)
    cv2.circle(
        image,
        (highlight, highlight),
        _scaled(HIGHLIGHT_RADIUS, size),
        HIGHLIGHT_COLOR,
        FILLED,
    )
    return image


def write_icon_png(path: Path, size: int = DEFAULT_SIZE) -> Path:
    """Write the icon as a PNG, creating the parent folder.

    Args:
        path: Destination file.
        size: Width and height in pixels.

    Returns:
        The written path.

    Raises:
        OSError: When the file cannot be written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), draw_icon(size)):
        raise OSError(f"Could not write the icon to {path}")
    return path
