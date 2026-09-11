"""Tunable pipeline settings shared between the window and the frame thread.

The window assigns fields of :class:`PipelineState` from the GUI thread and the frame
loop reads them on every frame, so a change takes effect on the next frame.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from tower_borescope.device.constants import DEFAULT_MODE, MODES
from tower_borescope.imaging.color import ColorGrade
from tower_borescope.imaging.geometry import ROTATIONS
from tower_borescope.measure.calibration import Calibration

PREROLL_SECONDS = 10
BURST_FRAMES = 10
AUTO_STACK_STILL_SECONDS = 1.2
MOTION_COOLDOWN_SECONDS = 3.0
NORMAL_VIEW = "Normal"


def _flag(settings: Mapping[str, Any], key: str, default: bool) -> bool:
    """A boolean setting, or ``default`` when it is missing."""
    return bool(settings.get(key, default))


def _number(settings: Mapping[str, Any], key: str, default: float) -> float:
    """A numeric setting, or ``default`` when it is missing or not a number."""
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def _optional_index(value: object) -> int | None:
    """An integer device index, or None for anything else."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _calibration(value: object) -> Calibration:
    """Calibration from saved data, or an empty one when the data is not a mapping."""
    return Calibration(value if isinstance(value, Mapping) else None)


def _mode(value: object) -> str:
    """A known mode name, falling back to the default mode."""
    return value if isinstance(value, str) and value in MODES else DEFAULT_MODE


@dataclass
class PipelineState:
    """Every setting the frame loop reads.

    Attributes:
        mode: Camera resolution mode name; changed through ``Pipeline.set_mode``.
        grade: Color controls applied to every frame.
        enhanced: Whether the enhance filter runs.
        rotation: Clockwise quarter turns, from 0 to 3.
        mirror: Whether frames are flipped left to right.
        raw_recording: True records camera JPEGs unchanged into a ``.mov`` file.
        preroll_enabled: Whether a recording starts with the buffered pre-roll.
        audio_device: AVFoundation microphone index, or None for silent recordings.
        stabilize: Whether shake removal runs.
        denoise: Temporal denoise strength from 0 (off) to 1.
        glare: Highlight compression from 0 (off) to 1.
        view_mode: Display look from ``imaging.view_modes.VIEW_MODES``.
        zebra: Whether clipped highlights are striped in the display image.
        meters: Whether focus, histogram and clipping meters are computed.
        auto_stack: Whether holding the scope still takes a stacked still.
        motion_trigger: Whether strong motion takes a snapshot.
        timelapse_interval: Seconds between time-lapse frames; 0 stops the time-lapse.
        want_vcam: Whether the virtual camera is wanted; cleared when it cannot start.
        calibration: Millimetres per pixel for each mode.
    """

    mode: str = DEFAULT_MODE
    grade: ColorGrade = field(default_factory=ColorGrade)
    enhanced: bool = False
    rotation: int = 0
    mirror: bool = False
    raw_recording: bool = False
    preroll_enabled: bool = True
    audio_device: int | None = None
    stabilize: bool = False
    denoise: float = 0.0
    glare: float = 0.0
    view_mode: str = NORMAL_VIEW
    zebra: bool = False
    meters: bool = True
    auto_stack: bool = False
    motion_trigger: bool = False
    timelapse_interval: float = 0.0
    want_vcam: bool = False
    calibration: Calibration = field(default_factory=Calibration)

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> PipelineState:
        """Build the state from saved settings.

        Automation switches, the time-lapse and the virtual camera always start off,
        as they did in the original application.

        Args:
            settings: Saved settings; missing or unusable values take their defaults.

        Returns:
            The initial pipeline state.
        """
        return cls(
            mode=_mode(settings.get("mode")),
            grade=ColorGrade.from_settings(settings),
            enhanced=_flag(settings, "enhance", False),
            rotation=int(_number(settings, "rotation", 0)) % len(ROTATIONS),
            mirror=_flag(settings, "mirror", False),
            raw_recording=_flag(settings, "raw", False),
            preroll_enabled=_flag(settings, "preroll", True),
            audio_device=_optional_index(settings.get("audio_device")),
            stabilize=_flag(settings, "stabilize", False),
            denoise=_number(settings, "denoise", 0.0),
            glare=_number(settings, "glare", 0.0),
            view_mode=str(settings.get("view_mode", NORMAL_VIEW)),
            zebra=_flag(settings, "zebra", False),
            meters=_flag(settings, "meters", True),
            calibration=_calibration(settings.get("calibration")),
        )

    def capture_metadata(self) -> dict[str, Any]:
        """Settings recorded in a capture's JSON sidecar.

        Returns:
            Camera size, mode, color controls, filters, orientation and image scale.
        """
        size = MODES[self.mode]
        return {
            "camera": f"{size.width}x{size.height}",
            "mode": self.mode,
            **self.grade.to_dict(),
            "enhance": self.enhanced,
            "stabilize": self.stabilize,
            "denoise": self.denoise,
            "glare": self.glare,
            "view_mode": self.view_mode,
            "rotation": self.rotation,
            "mirror": self.mirror,
            "mm_per_px": self.calibration.mm_per_px(self.mode),
        }
