"""Synthetic images and camera traffic generated at test time.

The repository stores no photographs. Frames are drawn procedurally with enough texture
for alignment, focus, noise and motion measurements to behave as they do on real footage,
and camera packets are built byte for byte from the protocol description.
``inspection_scene`` draws a recognizable corroded pipe for live vision-model tests.
"""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from tower_borescope.image_types import BgrImage
from tower_borescope.jpeg import encode_jpeg

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
PACKET_PAYLOAD = 931
_MAGIC = b"\xaa\xbb"
_CAMERA_ID = 7
_BUTTON_FLAG = 0x02
_HEADER_AFTER_LENGTH = 7


def textured_frame(
    width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT, seed: int = 0
) -> BgrImage:
    """Draw a pipe-like scene: shaded background, rings, edges, text and sensor noise.

    Args:
        width: Frame width in pixels.
        height: Frame height in pixels.
        seed: Random seed; equal seeds give identical frames.

    Returns:
        A BGR frame.
    """
    rng = np.random.default_rng(seed)
    rows, cols = np.mgrid[0:height, 0:width].astype(np.float32)
    shade = 110 + 50 * np.sin(cols / 97.0) + 35 * np.cos(rows / 61.0)
    image = np.dstack([shade * 0.9, shade, shade * 1.1]).astype(np.float32)
    for _ in range(40):
        center = (int(rng.integers(0, width)), int(rng.integers(0, height)))
        color = tuple(float(c) for c in rng.integers(20, 235, 3))
        radius = int(rng.integers(6, 60))
        cv2.circle(image, center, radius, color, int(rng.integers(1, 5)))
    for _ in range(25):
        start = (int(rng.integers(0, width)), int(rng.integers(0, height)))
        end = (int(rng.integers(0, width)), int(rng.integers(0, height)))
        cv2.line(image, start, end, (30.0, 30.0, 30.0), 2)
    drawn = np.clip(image, 0, 255).astype(np.uint8)
    # OpenCV draws text only on 8-bit images, so the label goes on after conversion.
    cv2.putText(drawn, "M8 x 1.25", (width // 3, height // 2), 0, 2.0, (240, 240, 240), 3)
    noisy = drawn.astype(np.float32) + rng.normal(0, 4, drawn.shape).astype(np.float32)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def shifted(image: BgrImage, dx: float, dy: float) -> BgrImage:
    """Translate an image by ``(dx, dy)`` pixels, reflecting at the borders."""
    height, width = image.shape[:2]
    matrix = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)
    moved = cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REFLECT)
    return np.asarray(moved, dtype=np.uint8)


def jpeg_frames(
    count: int, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT, seed: int = 0
) -> list[bytes]:
    """Encode ``count`` frames of one scene panning two pixels per frame."""
    base = textured_frame(width, height, seed)
    return [encode_jpeg(shifted(base, 2.0 * index, 0.0), 80) for index in range(count)]


def camera_packets(jpeg: bytes, fid: int, button: bool = False) -> list[bytes]:
    """Split one JPEG into borescope bulk packets for frame id ``fid``.

    Each packet is a 5-byte USB header (magic, camera id, length) and a 7-byte camera
    header (frame id, camera number, flags, g-sensor) followed by a JPEG chunk.
    """
    packets: list[bytes] = []
    flags = _BUTTON_FLAG if button else 0
    for offset in range(0, len(jpeg), PACKET_PAYLOAD):
        chunk = jpeg[offset : offset + PACKET_PAYLOAD]
        length = _HEADER_AFTER_LENGTH + len(chunk)
        header = _MAGIC + bytes([_CAMERA_ID, length & 0xFF, length >> 8])
        camera = bytes([fid & 0xFF, 0, flags, 0, 0, 0, 0])
        packets.append(header + camera + chunk)
    return packets


SCENE_WIDTH = 640
SCENE_HEIGHT = 480
_SCENE_SEED = 7
_PIPE_TOP = 0.26
_PIPE_BOTTOM = 0.74
_CAVITY_BGR = (18.0, 16.0, 14.0)
_STEEL_TINT = (1.0, 1.0, 1.04)
_RUST_BGR = (28.0, 72.0, 150.0)
_CRACK_BGR = (10.0, 10.0, 12.0)
_BLOTCHES = 14
_CRACK_POINTS = 12


def _pipe_band(height: int) -> tuple[int, int]:
    """First row of the pipe and the row just below it."""
    return int(height * _PIPE_TOP), int(height * _PIPE_BOTTOM)


def _pipe(width: int, height: int) -> NDArray[np.float32]:
    """A dark cavity crossed by a horizontal steel pipe shaded as a cylinder."""
    image = np.empty((height, width, 3), np.float32)
    image[:] = _CAVITY_BGR
    top, bottom = _pipe_band(height)
    center = (top + bottom) / 2.0
    radius = (bottom - top) / 2.0
    offset = (np.arange(top, bottom, dtype=np.float32) - center) / radius
    facing = np.sqrt(np.clip(1.0 - offset**2, 0.0, 1.0))
    highlight = np.exp(-(((offset + 0.45) / 0.12) ** 2))
    level = 35.0 + 150.0 * facing + 70.0 * highlight
    image[top:bottom] = level[:, None, None] * np.array(_STEEL_TINT, np.float32)
    return image


def _corrosion(image: NDArray[np.float32]) -> None:
    """Blend blurred orange-brown blotches onto the pipe surface."""
    height, width = image.shape[:2]
    top, bottom = _pipe_band(height)
    rng = np.random.default_rng(_SCENE_SEED)
    layer = np.zeros((height, width), np.float32)
    for _ in range(_BLOTCHES):
        center = (int(rng.integers(0, width)), int(rng.integers(top + 12, bottom - 12)))
        axes = (
            int(rng.integers(width // 40, width // 12)),
            int(rng.integers(6, height // 14)),
        )
        angle = float(rng.integers(0, 180))
        cv2.ellipse(layer, center, axes, angle, 0.0, 360.0, 1.0, -1)
    sigma = width / 160.0
    blurred = np.asarray(cv2.GaussianBlur(layer, (0, 0), sigmaX=sigma), np.float32)
    blurred[:top] = 0.0
    blurred[bottom:] = 0.0
    mask = np.clip(blurred, 0.0, 1.0)[:, :, None]
    lighting = np.clip(image.mean(axis=2, keepdims=True) / 170.0, 0.3, 1.2)
    rust = np.array(_RUST_BGR, np.float32) * lighting
    image[:] = image * (1.0 - mask) + rust * mask


def _crack(image: NDArray[np.float32]) -> None:
    """Draw a thin, slightly wandering dark crack along the pipe."""
    height, width = image.shape[:2]
    rng = np.random.default_rng(_SCENE_SEED + 1)
    xs = np.linspace(width * 0.15, width * 0.85, _CRACK_POINTS)
    ys = height * 0.52 + np.cumsum(rng.normal(0.0, height * 0.012, _CRACK_POINTS))
    points = np.stack([xs, ys], axis=1).astype(np.int32).reshape(-1, 1, 2)
    thickness = max(2, width // 320)
    cv2.polylines(image, [points], False, _CRACK_BGR, thickness, cv2.LINE_AA)


def _vignette(image: NDArray[np.float32]) -> BgrImage:
    """Darken the corners as the light from the LED ring falls off."""
    height, width = image.shape[:2]
    rows, cols = np.mgrid[0:height, 0:width].astype(np.float32)
    across = (cols - width / 2) / (width / 2)
    down = (rows - height / 2) / (height / 2)
    falloff = np.clip(1.15 - 0.55 * np.hypot(across, down) ** 2, 0.25, 1.0)
    shaded: BgrImage = np.clip(image * falloff[:, :, None], 0, 255).astype(np.uint8)
    return shaded


def inspection_scene(width: int = SCENE_WIDTH, height: int = SCENE_HEIGHT) -> BgrImage:
    """Draw a borescope view of a corroded, cracked steel pipe.

    A dark cavity surrounds a large horizontal pipe with cylindrical shading and a
    specular highlight. Orange-brown corrosion blotches sit along the pipe, a thin dark
    crack runs across it, and a vignette darkens the corners. The drawing contains no
    text and no noise, so equal sizes give identical frames. A local vision model
    recognizes the subject and answers, where the noise of ``textured_frame`` leaves
    the thinking variant of qwen3-vl reasoning without producing an answer.

    Args:
        width: Frame width in pixels.
        height: Frame height in pixels.

    Returns:
        A BGR frame.
    """
    image = _pipe(width, height)
    _corrosion(image)
    _crack(image)
    return _vignette(image)
