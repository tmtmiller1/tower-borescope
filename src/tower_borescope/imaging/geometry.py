"""Digital zoom, rotation and mirroring, and the small grayscale copy for analysis."""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np

from tower_borescope.image_types import BgrImage, FloatImage

ZOOM_STEPS: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0)
ROTATIONS: tuple[int | None, ...] = (
    None,
    cv2.ROTATE_90_CLOCKWISE,
    cv2.ROTATE_180,
    cv2.ROTATE_90_COUNTERCLOCKWISE,
)
ANALYSIS_WIDTH = 320
_MIRROR_HORIZONTAL = 1


def zoom(image: BgrImage, factor: float) -> BgrImage:
    """Crop the centre by ``factor`` and scale it back to the original size.

    Args:
        image: BGR frame.
        factor: Magnification; values of 1 or less return ``image`` itself.

    Returns:
        The zoomed frame with the same width and height as ``image``.
    """
    if factor <= 1:
        return image
    height, width = image.shape[:2]
    crop_h, crop_w = int(height / factor), int(width / factor)
    top, left = (height - crop_h) // 2, (width - crop_w) // 2
    centre = image[top : top + crop_h, left : left + crop_w]
    return cast(
        BgrImage, cv2.resize(centre, (width, height), interpolation=cv2.INTER_CUBIC)
    )


def orient(image: BgrImage, rotation: int, mirror: bool) -> BgrImage:
    """Rotate in quarter turns and optionally mirror left to right.

    Args:
        image: BGR frame.
        rotation: Clockwise quarter turns; taken modulo 4.
        mirror: Whether to flip horizontally after rotating.

    Returns:
        The oriented frame, or ``image`` itself when no change applies.
    """
    code = ROTATIONS[rotation % len(ROTATIONS)]
    oriented = image if code is None else cast(BgrImage, cv2.rotate(image, code))
    if mirror:
        return cast(BgrImage, cv2.flip(oriented, _MIRROR_HORIZONTAL))
    return oriented


def small_gray(image: BgrImage) -> FloatImage:
    """Grayscale copy scaled to :data:`ANALYSIS_WIDTH` for motion and shake analysis.

    Args:
        image: BGR frame.

    Returns:
        A float32 grayscale image keeping the frame's aspect ratio.
    """
    height, width = image.shape[:2]
    size = (ANALYSIS_WIDTH, max(1, height * ANALYSIS_WIDTH // width))
    small = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
