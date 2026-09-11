"""Motion-aware temporal noise reduction for the live view."""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np

from tower_borescope.image_types import BgrImage, FloatImage

_DIFF_SIGMA = 2
_MOTION_LEVELS = 24.0


class TemporalDenoise:
    """Averages frames over time where the picture is still and follows motion.

    Each pixel blends the running average with the new frame. Where the new frame
    differs little from the average, the average is kept, so static detail gets
    cleaner; where it differs a lot, the new frame wins, so motion does not smear.

    Attributes:
        strength: Largest weight of the running average, from 0 to 1.
    """

    def __init__(self, strength: float = 0.7) -> None:
        self.strength = strength
        self._average: FloatImage | None = None

    def reset(self) -> None:
        """Drop the running average so the next frame starts a new one."""
        self._average = None

    def apply(self, image: BgrImage) -> BgrImage:
        """Denoise one frame.

        Args:
            image: BGR frame, the next in the stream.

        Returns:
            The blended frame; the first frame of a stream is returned unchanged.
        """
        if self._average is None or self._average.shape != image.shape:
            self._average = image.astype(np.float32)
            return image
        current = cv2.convertScaleAbs(self._average)
        difference = cv2.cvtColor(cv2.absdiff(image, current), cv2.COLOR_BGR2GRAY)
        motion = cv2.GaussianBlur(difference, (0, 0), _DIFF_SIGMA).astype(np.float32)
        # Weight 1 keeps the average (still); weight 0 takes the new frame (moving).
        unclipped = self.strength * (1.0 - motion / _MOTION_LEVELS)
        keep = cast(FloatImage, cv2.threshold(unclipped, 0, 0, cv2.THRESH_TOZERO)[1])
        blended = cv2.blendLinear(
            self._average, image.astype(np.float32), keep, 1.0 - keep
        )
        self._average = cast(FloatImage, blended)
        return cast(BgrImage, cv2.convertScaleAbs(blended))
