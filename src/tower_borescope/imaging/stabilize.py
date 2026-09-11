"""Handheld shake removal for the live view."""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from tower_borescope.image_types import BgrImage, FloatImage
from tower_borescope.imaging.geometry import ANALYSIS_WIDTH, small_gray

_MIN_RESPONSE = 0.15
_MAX_JUMP_FRACTION = 0.25


class Stabilizer:
    """Removes handheld shake from a stream of frames.

    Frame-to-frame translation comes from phase correlation on a small grayscale copy.
    The accumulated camera path is smoothed, each frame is shifted onto the smoothed
    path, and a slight crop hides the edges the shift reveals.

    Attributes:
        smoothing: Weight of the previous smoothed position, from 0 to 1.
        max_shift: Largest correction as a fraction of the frame size.
        crop: Fraction of width and height trimmed to hide shifted edges.
    """

    def __init__(
        self, smoothing: float = 0.9, max_shift: float = 0.08, crop: float = 0.06
    ) -> None:
        self.smoothing = smoothing
        self.max_shift = max_shift
        self.crop = crop
        self._prev: FloatImage | None = None
        self._window: FloatImage | None = None
        self._path: NDArray[np.float64] = np.zeros(2)
        self._smooth: NDArray[np.float64] = np.zeros(2)

    def reset(self) -> None:
        """Forget the camera path, for example after a scene cut or a mode change."""
        self._prev = None
        self._window = None
        self._path = np.zeros(2)
        self._smooth = np.zeros(2)

    def apply(self, image: BgrImage) -> BgrImage:
        """Stabilize one frame.

        Args:
            image: BGR frame, the next in the stream.

        Returns:
            A frame of the same size, shifted onto the smoothed path and cropped.
        """
        gray = small_gray(image)
        self._track(gray, image.shape[1])
        self._prev = gray
        return self._corrected(image)

    def _track(self, gray: FloatImage, frame_width: int) -> None:
        """Add the motion since the previous frame to the camera path."""
        if self._window is None or self._window.shape != gray.shape:
            window = cv2.createHanningWindow(gray.shape[::-1], cv2.CV_32F)
            self._window = cast(FloatImage, window)
        if self._prev is None or self._prev.shape != gray.shape:
            return
        (dx, dy), response = cv2.phaseCorrelate(self._prev, gray, self._window)
        scale = frame_width / ANALYSIS_WIDTH
        if response < _MIN_RESPONSE or abs(dx) * scale > frame_width * _MAX_JUMP_FRACTION:
            self.reset()  # scene cut or lost track
            return
        self._path += (dx * scale, dy * scale)
        memory = self.smoothing
        self._smooth = memory * self._smooth + (1 - memory) * self._path

    def _corrected(self, image: BgrImage) -> BgrImage:
        """Shift the frame onto the smoothed path, then crop and rescale."""
        height, width = image.shape[:2]
        limit = np.array([width, height]) * self.max_shift
        shift = np.clip(self._smooth - self._path, -limit, limit)
        # Keeps the smoothed path from drifting away from the real one over time.
        self._smooth = self._path + shift
        matrix = np.array([[1, 0, shift[0]], [0, 1, shift[1]]], dtype=np.float32)
        moved = cv2.warpAffine(
            image,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        margin_x, margin_y = int(width * self.crop / 2), int(height * self.crop / 2)
        trimmed = moved[margin_y : height - margin_y, margin_x : width - margin_x]
        resized = cv2.resize(trimmed, (width, height), interpolation=cv2.INTER_LINEAR)
        return cast(BgrImage, resized)
