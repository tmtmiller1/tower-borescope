"""JPEG helpers shared by the camera driver, image processing and AI layers."""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np

from tower_borescope.image_types import BgrImage

DEFAULT_QUALITY = 90
_MARKER_PREFIX = 0xFF
_START_OF_FRAME = 0xC0
_START_OF_SCAN = 0xDA
_FIRST_SEGMENT = 2
_SOF_HEADER_BYTES = 9


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Read width and height from a baseline JPEG header without decoding it.

    Args:
        data: Complete JPEG file contents.

    Returns:
        ``(width, height)`` from the SOF0 segment, or None when the scan data
        starts before any SOF0 segment or the header is truncated.
    """
    index = _FIRST_SEGMENT
    while index + _SOF_HEADER_BYTES < len(data) and data[index] == _MARKER_PREFIX:
        marker = data[index + 1]
        length = (data[index + 2] << 8) | data[index + 3]
        if marker == _START_OF_FRAME:
            height = (data[index + 5] << 8) | data[index + 6]
            width = (data[index + 7] << 8) | data[index + 8]
            return width, height
        if marker == _START_OF_SCAN:
            return None
        index += 2 + length
    return None


def decode_bgr(data: bytes) -> BgrImage | None:
    """Decode JPEG bytes to a BGR image.

    Args:
        data: JPEG file contents.

    Returns:
        The decoded image, or None when the bytes are not a decodable JPEG.
    """
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        return None
    return cast(BgrImage, image)


def encode_jpeg(image: BgrImage, quality: int = DEFAULT_QUALITY) -> bytes:
    """Encode a BGR image as JPEG.

    Args:
        image: Image to encode.
        quality: libjpeg quality from 0 to 100.

    Returns:
        The JPEG file contents.

    Raises:
        ValueError: When OpenCV cannot encode the image.
    """
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("image could not be encoded as JPEG")
    return bytes(buffer.tobytes())
