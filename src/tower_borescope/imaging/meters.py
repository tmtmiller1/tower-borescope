"""Live meters: focus, histogram, clipped highlights, zebra stripes and motion."""

from __future__ import annotations

from functools import lru_cache
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from tower_borescope.image_types import BgrImage, FloatImage
from tower_borescope.imaging.geometry import small_gray

_PEAK_DECAY = 0.995
_STRIPE_PERIOD = 6
_STRIPE_CACHE_SIZE = 8
_ZEBRA_COLOR = (40, 40, 220)


def focus_score(image: BgrImage) -> float:
    """Sharpness of the central region as the variance of the Laplacian.

    Higher is sharper. The value only means something relative to other frames of the
    same scene.

    Args:
        image: BGR frame.

    Returns:
        The focus score of the middle half of the frame.
    """
    height, width = image.shape[:2]
    centre = image[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4]
    gray = cv2.cvtColor(centre, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


class FocusMeter:
    """Turns raw focus scores into a 0 to 1 reading against the best score seen recently.

    Attributes:
        peak: Best recent score; it decays slowly so a new scene re-scales the meter.
    """

    def __init__(self) -> None:
        self.peak = 1.0

    def update(self, score: float) -> float:
        """Record a score and return it relative to the recent peak.

        Args:
            score: Output of :func:`focus_score` for the latest frame.

        Returns:
            The reading from 0 to 1.
        """
        self.peak = max(score, self.peak * _PEAK_DECAY)
        return min(score / self.peak, 1.0) if self.peak > 0 else 0.0


def histogram(image: BgrImage, bins: int = 64) -> NDArray[np.float32]:
    """Luminance histogram scaled so the tallest bin is 1.

    Args:
        image: BGR frame.
        bins: Number of equal-width bins over the 0 to 255 range.

    Returns:
        A one-dimensional array of ``bins`` values from 0 to 1.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    counts = cv2.calcHist([gray], [0], None, [bins], [0, 256]).ravel()
    return cast(NDArray[np.float32], counts / max(float(counts.max()), 1.0))


def clipped_fraction(image: BgrImage, threshold: int = 250) -> float:
    """Fraction of pixels whose luminance reaches ``threshold``.

    Args:
        image: BGR frame.
        threshold: Luminance level counted as clipped.

    Returns:
        A value from 0 to 1.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float((gray >= threshold).mean())


@lru_cache(maxsize=_STRIPE_CACHE_SIZE)
def _stripes(height: int, width: int) -> NDArray[np.bool_]:
    """Read-only diagonal stripe mask for one frame size."""
    rows, cols = np.mgrid[0:height, 0:width]
    pattern = cast(
        NDArray[np.bool_], (((cols + rows) // _STRIPE_PERIOD) % 2).astype(bool)
    )
    pattern.setflags(write=False)
    return pattern


def zebra(image: BgrImage, threshold: int = 250) -> BgrImage:
    """Paint diagonal stripes over blown-out highlights, for display only.

    Args:
        image: BGR frame. It is never modified.
        threshold: Luminance level at which stripes appear.

    Returns:
        A striped copy, or ``image`` itself when nothing reaches the threshold.
    """
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = (gray >= threshold) & _stripes(height, width)
    if not mask.any():
        return image
    striped = image.copy()
    striped[mask] = _ZEBRA_COLOR
    return striped


class MotionDetector:
    """Mean absolute change between consecutive frames on a small grayscale copy.

    Attributes:
        threshold: Level above which the scene counts as moving.
        level: Latest mean absolute change, in 8-bit levels.
    """

    def __init__(self, threshold: float = 2.5) -> None:
        self.threshold = threshold
        self.level = 0.0
        self._prev: FloatImage | None = None
        self._still_since: float | None = None

    def update(self, image: BgrImage, now: float) -> float:
        """Measure motion against the previous frame.

        Args:
            image: BGR frame, the next in the stream.
            now: Monotonic time of the frame in seconds.

        Returns:
            The motion level.
        """
        gray = small_gray(image)
        if self._prev is not None and self._prev.shape == gray.shape:
            self.level = float(np.abs(gray - self._prev).mean())
        self._prev = gray
        if self.level > self.threshold:
            self._still_since = None
        elif self._still_since is None:
            self._still_since = now
        return self.level

    def still_seconds(self, now: float) -> float:
        """Seconds the scene has stayed below the motion threshold.

        Args:
            now: Monotonic time in seconds, on the same clock as :meth:`update`.

        Returns:
            The steady duration, or 0 while the scene moves.
        """
        return 0.0 if self._still_since is None else now - self._still_since
