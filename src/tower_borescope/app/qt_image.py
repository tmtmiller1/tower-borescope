"""Conversion from OpenCV BGR images to Qt images."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage

from tower_borescope.image_types import BgrImage

_RGB_CHANNELS = 3


def to_qimage(image: BgrImage) -> QImage:
    """Convert a BGR frame to an RGB888 QImage.

    Args:
        image: BGR frame. It is never modified.

    Returns:
        A QImage holding its own copy of the pixels, so it stays valid after the array
        is released or reused.
    """
    rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    height, width = rgb.shape[:2]
    wrapped = QImage(
        rgb.data, width, height, _RGB_CHANNELS * width, QImage.Format.Format_RGB888
    )
    return wrapped.copy()
