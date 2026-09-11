"""Frame encoding for model requests."""

from __future__ import annotations

import base64
from typing import cast

import cv2

from tower_borescope.image_types import BgrImage
from tower_borescope.jpeg import encode_jpeg

MODEL_JPEG_QUALITY = 88


def encode_for_model(image: BgrImage, max_width: int) -> bytes:
    """Encode a frame as JPEG, downscaled to ``max_width`` pixels when wider.

    Local models answer much faster on smaller images, and vision tokens scale with
    pixel count.

    Args:
        image: Frame to send.
        max_width: Widest image the backend should receive.

    Returns:
        JPEG bytes.
    """
    height, width = image.shape[:2]
    if width > max_width:
        size = (max_width, height * max_width // width)
        image = cast(BgrImage, cv2.resize(image, size, interpolation=cv2.INTER_AREA))
    return encode_jpeg(image, MODEL_JPEG_QUALITY)


def to_base64(data: bytes) -> str:
    """Standard base64 text for binary data such as a JPEG."""
    return base64.standard_b64encode(data).decode("ascii")
