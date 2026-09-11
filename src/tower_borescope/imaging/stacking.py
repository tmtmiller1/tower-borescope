"""Multi-frame stacking: sub-pixel alignment and averaging on an upscaled grid.

Averaging N aligned frames cuts sensor noise by about the square root of N, and slight
hand movement between frames recovers a little real detail on the finer grid.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from tower_borescope.errors import BorescopeError
from tower_borescope.image_types import BgrImage, FloatImage

STACK_FRAMES = 16
_ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
_ECC_GAUSSIAN_SIZE = 5
_MIN_CORRELATION = 0.8
_MAX_SHIFT_PX = 20
_ALIGN_FAILED = "Could not align frames for stacking. Hold the scope steadier."


def _gray(image: BgrImage) -> FloatImage:
    """Float32 grayscale copy for ECC alignment."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _translation(reference: FloatImage, image: BgrImage) -> NDArray[np.float32] | None:
    """Translation of ``image`` relative to ``reference``, or None when it does not align.

    Args:
        reference: Grayscale reference frame.
        image: BGR frame to align.

    Returns:
        A 2 by 3 affine matrix, or None when ECC fails, correlates poorly, or finds a
        shift larger than the alignment limit.
    """
    initial = np.eye(2, 3, dtype=np.float32)
    # A mask of ones matches OpenCV's behaviour for an empty mask; the typed overload
    # that accepts the Gaussian filter size does not accept None.
    everywhere = np.ones(reference.shape, dtype=np.uint8)
    try:
        correlation, found = cv2.findTransformECC(
            reference,
            _gray(image),
            initial,
            cv2.MOTION_TRANSLATION,
            _ECC_CRITERIA,
            everywhere,
            _ECC_GAUSSIAN_SIZE,
        )
    except cv2.error:
        return None
    warp = cast(NDArray[np.float32], found)
    too_far = abs(warp[0, 2]) > _MAX_SHIFT_PX or abs(warp[1, 2]) > _MAX_SHIFT_PX
    if correlation < _MIN_CORRELATION or too_far:
        return None
    return warp


def _upscaled_aligned(
    image: BgrImage, warp: NDArray[np.float32], scale: int
) -> FloatImage:
    """Upscale ``image`` by ``scale`` and undo its measured translation."""
    height, width = image.shape[:2]
    size = (width * scale, height * scale)
    upscaled = cv2.resize(image, size, interpolation=cv2.INTER_CUBIC).astype(np.float32)
    shift = np.array(
        [[1, 0, warp[0, 2] * scale], [0, 1, warp[1, 2] * scale]], dtype=np.float32
    )
    flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
    aligned = cv2.warpAffine(
        upscaled, shift, size, flags=flags, borderMode=cv2.BORDER_REFLECT
    )
    return cast(FloatImage, aligned)


def stack_frames(frames: Sequence[BgrImage], scale: int = 2) -> tuple[BgrImage, int]:
    """Align frames by sub-pixel translation and average them on an upscaled grid.

    The middle frame is the reference. Frames that moved too far or correlate poorly
    are skipped.

    Args:
        frames: BGR frames of one scene, all the same size.
        scale: Integer upscale factor of the output.

    Returns:
        The stacked still and the number of frames that went into it.

    Raises:
        BorescopeError: When ``frames`` is empty or no frame aligns.
    """
    if not frames:
        raise BorescopeError(_ALIGN_FAILED)
    reference = _gray(frames[len(frames) // 2])
    height, width = reference.shape
    total = np.zeros((height * scale, width * scale, 3), np.float32)
    used = 0
    for image in frames:
        warp = _translation(reference, image)
        if warp is None:
            continue
        total += _upscaled_aligned(image, warp, scale)
        used += 1
    if used == 0:
        raise BorescopeError(_ALIGN_FAILED)
    return np.clip(total / used, 0, 255).astype(np.uint8), used
