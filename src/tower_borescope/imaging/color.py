"""Software color controls: grey-world white balance, brightness, contrast, saturation.

The borescope does not expose color controls of its own, so these run on every decoded
frame. A full grade costs about 2 ms at 720p, and the default grade returns the input
unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from tower_borescope.image_types import BgrImage

COLOR_DEFAULTS: Mapping[str, int | float | bool] = MappingProxyType(
    {"brightness": 0, "contrast": 1.0, "saturation": 1.0, "awb": False}
)

_MIN_GAIN = 0.5
_MAX_GAIN = 2.0
_GAIN_MEMORY = 0.9
_MID_GREY = 128
_LUT_SIZE = 256


def _setting[T: (int, float)](settings: Mapping[str, Any], key: str, kind: type[T]) -> T:
    """Read one numeric setting, falling back to the default when it is unusable."""
    default = kind(COLOR_DEFAULTS[key])
    try:
        return kind(settings.get(key, default))
    except (TypeError, ValueError):
        return default


class ColorGrade:
    """Brightness, contrast, saturation and optional auto white balance for BGR frames.

    Attributes:
        brightness: Offset added to every channel, in 8-bit levels.
        contrast: Gain applied around mid-grey; 1.0 leaves contrast unchanged.
        saturation: Blend factor against the grayscale image; 1.0 is unchanged.
        awb: Whether grey-world white balance runs before the other controls.
    """

    def __init__(
        self,
        brightness: int = 0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        awb: bool = False,
    ) -> None:
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.awb = awb
        self._gains: NDArray[np.float64] | None = None

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> ColorGrade:
        """Build a grade from a settings mapping, using defaults for missing keys.

        Args:
            settings: Saved settings; keys other than the color controls are ignored.

        Returns:
            A grade with values converted to their expected types.
        """
        return cls(
            brightness=_setting(settings, "brightness", int),
            contrast=_setting(settings, "contrast", float),
            saturation=_setting(settings, "saturation", float),
            awb=bool(settings.get("awb", COLOR_DEFAULTS["awb"])),
        )

    def reset(self) -> None:
        """Restore every control to its default and forget the white balance history."""
        self.brightness = int(COLOR_DEFAULTS["brightness"])
        self.contrast = float(COLOR_DEFAULTS["contrast"])
        self.saturation = float(COLOR_DEFAULTS["saturation"])
        self.awb = bool(COLOR_DEFAULTS["awb"])
        self._gains = None

    def to_dict(self) -> dict[str, int | float | bool]:
        """Return the controls keyed as in :data:`COLOR_DEFAULTS`."""
        return {
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "awb": self.awb,
        }

    def is_default(self) -> bool:
        """True when every control holds its default value."""
        return self.to_dict() == COLOR_DEFAULTS

    def describe(self) -> str:
        """Short status text naming the controls that differ from their defaults."""
        parts: list[str] = []
        if self.awb:
            parts.append("AWB")
        if self.brightness:
            parts.append(f"bright {self.brightness:+d}")
        if self.contrast != 1.0:
            parts.append(f"contrast {self.contrast:.1f}")
        if self.saturation != 1.0:
            parts.append(f"sat {self.saturation:.1f}")
        return "  ".join(parts)

    def apply(self, image: BgrImage) -> BgrImage:
        """Grade one frame.

        Args:
            image: BGR frame. It is never modified.

        Returns:
            The graded frame, or ``image`` itself when every control is at its default.
        """
        graded = image
        if self.awb:
            graded = self._white_balance(graded)
        if self.contrast != 1.0 or self.brightness:
            # Contrast pivots on mid-grey so that it does not also shift brightness.
            beta = self.brightness + _MID_GREY * (1 - self.contrast)
            graded = cast(
                BgrImage, cv2.convertScaleAbs(graded, alpha=self.contrast, beta=beta)
            )
        if self.saturation != 1.0:
            gray = cv2.cvtColor(
                cv2.cvtColor(graded, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR
            )
            blended = cv2.addWeighted(
                graded, self.saturation, gray, 1 - self.saturation, 0
            )
            graded = cast(BgrImage, blended)
        return graded

    def _white_balance(self, image: BgrImage) -> BgrImage:
        """Scale channels so their means match, smoothed over frames to avoid flicker."""
        means = np.array(cv2.mean(image)[:3])
        gains = np.clip(means.mean() / np.maximum(means, 1), _MIN_GAIN, _MAX_GAIN)
        if self._gains is None:
            self._gains = gains
        else:
            self._gains = _GAIN_MEMORY * self._gains + (1 - _GAIN_MEMORY) * gains
        levels = np.arange(_LUT_SIZE)[:, None] * self._gains[None, :]
        lut = np.clip(levels, 0, 255).astype(np.uint8)
        return cast(BgrImage, cv2.LUT(image, lut.reshape(_LUT_SIZE, 1, 3)))
