"""Processed frame and meter readings passed from the pipeline to the view."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PySide6.QtGui import QImage


@dataclass(slots=True)
class FrameInfo:
    """One processed frame plus the meter readings that go with it.

    Attributes:
        image: Display image that owns its pixels, with zebra stripes when enabled.
        focus: Focus reading from 0 to 1 against the recent peak, or None with meters off.
        focus_raw: Focus score of the unprocessed frame, used by the scale focus lock.
        hist: Luminance histogram with the tallest bin at 1, or None with meters off.
        clipped: Fraction of pixels with clipped highlights.
        motion: Mean absolute change against the previous frame, in 8-bit levels.
    """

    image: QImage
    focus: float | None = None
    focus_raw: float | None = None
    hist: NDArray[np.float32] | None = None
    clipped: float = 0.0
    motion: float = 0.0
