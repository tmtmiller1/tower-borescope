"""Image scale in millimetres per pixel, kept per camera resolution.

The field of view differs between resolutions, so each mode has its own entry. The
borescope is fixed-focus: the picture is only at the calibrated working distance when
it is about as sharp as it was at calibration time, so each entry also remembers the
focus score measured then.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, TypedDict

FOCUS_TOLERANCE = 0.35
SOURCE_MEASURED = "measured"
SOURCE_AI = "ai"


class CalibrationEntry(TypedDict):
    """Stored scale for one camera mode.

    Attributes:
        mm_per_px: Millimetres per image pixel.
        focus: Focus score at calibration time, or None when unknown.
        source: "measured" for a clicked known length, "ai" for a model estimate.
    """

    mm_per_px: float
    focus: float | None
    source: str


def _optional_float(value: object) -> float | None:
    """A float from a number or numeric string, otherwise None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_entry(value: object) -> CalibrationEntry | None:
    """Read one saved entry: a mapping, or a bare number from older settings."""
    if not isinstance(value, Mapping):
        scale = _optional_float(value)
        if scale is None:
            return None
        return {"mm_per_px": scale, "focus": None, "source": SOURCE_MEASURED}
    scale = _optional_float(value.get("mm_per_px"))
    if scale is None:
        return None
    return {
        "mm_per_px": scale,
        "focus": _optional_float(value.get("focus")),
        "source": str(value.get("source", SOURCE_MEASURED)),
    }


class Calibration:
    """Scale per camera mode, loaded from and saved to the settings file.

    Attributes:
        entries: Calibration entries keyed by mode name.
        FOCUS_TOLERANCE: Fraction by which the focus score may differ from its
            calibration value before the scale is doubtful.
    """

    FOCUS_TOLERANCE: ClassVar[float] = FOCUS_TOLERANCE

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        """Load saved entries.

        Args:
            data: Saved calibration keyed by mode. Values are entry mappings or, in
                older settings, bare millimetre-per-pixel numbers. Unreadable values
                are skipped.
        """
        self.entries: dict[str, CalibrationEntry] = {}
        for mode, value in (data or {}).items():
            entry = _parse_entry(value)
            if entry is not None:
                self.entries[mode] = entry

    def set_from(
        self,
        mode: str,
        pixels: float,
        millimetres: float,
        focus: float | None = None,
        source: str = SOURCE_MEASURED,
    ) -> None:
        """Calibrate a mode from a known length.

        Non-positive lengths leave the calibration unchanged.

        Args:
            mode: Camera mode name.
            pixels: Length of the reference in image pixels.
            millimetres: True length of the reference.
            focus: Focus score at the time, for the focus lock.
            source: "measured" or "ai".
        """
        if pixels > 0 and millimetres > 0:
            self.entries[mode] = {
                "mm_per_px": millimetres / pixels,
                "focus": focus,
                "source": source,
            }

    def mm_per_px(self, mode: str) -> float | None:
        """Millimetres per pixel for ``mode``, or None when it is not calibrated."""
        entry = self.entries.get(mode)
        return entry["mm_per_px"] if entry else None

    def source(self, mode: str) -> str | None:
        """How ``mode`` was calibrated, or None when it is not calibrated."""
        entry = self.entries.get(mode)
        return entry["source"] if entry else None

    def focus_ok(self, mode: str, focus_now: float | None) -> bool | None:
        """Judge whether the scope is at the calibrated working distance.

        Args:
            mode: Camera mode name.
            focus_now: Current focus score.

        Returns:
            True or False when the focus scores can be compared, and None when the
            mode has no calibration focus or ``focus_now`` is None.
        """
        entry = self.entries.get(mode)
        if not entry or not entry["focus"] or focus_now is None:
            return None
        reference = entry["focus"]
        return abs(focus_now - reference) <= self.FOCUS_TOLERANCE * reference

    def to_dict(self) -> dict[str, CalibrationEntry]:
        """Copy of every entry, ready to save in the settings file."""
        return {mode: CalibrationEntry(**entry) for mode, entry in self.entries.items()}
