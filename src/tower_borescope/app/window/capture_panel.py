"""Capture tab: stills, recording options, automation and folder shortcuts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QSpinBox, QWidget

from tower_borescope.app.pipeline.state import BURST_FRAMES, PREROLL_SECONDS
from tower_borescope.app.widgets.layout import (
    button,
    checkbox,
    column,
    group,
    row,
    small_label,
)
from tower_borescope.capture.ffmpeg import AudioDevice

STACK_LABEL: Final = "Stacked still"
RECORD_LABEL: Final = "Record"
TIMELAPSE_START_LABEL: Final = "Start time-lapse"
NO_MICROPHONE: Final = "No microphone"
TIMELAPSE_RANGE: Final = (1, 3600)
TIMELAPSE_DEFAULT: Final = 5

type Action = Callable[[], None]
type Toggle = Callable[[bool], None]


@dataclass(frozen=True, slots=True)
class CaptureActions:
    """Handlers for the Capture tab controls.

    Attributes:
        snapshot: Take a snapshot.
        stack: Take a stacked still.
        burst: Save a burst of frames.
        toggle_recording: Start or stop recording.
        toggle_timelapse: Start or stop the time-lapse.
        set_preroll: Pre-roll switch.
        set_raw: Original camera stream switch.
        set_audio_index: Called with the microphone combo index.
        set_auto_stack: Automatic stacked still switch.
        set_motion_trigger: Motion snapshot switch.
        open_pictures: Open the pictures folder.
        open_movies: Open the movies folder.
        show_gallery: Open the gallery.
    """

    snapshot: Action
    stack: Action
    burst: Action
    toggle_recording: Action
    toggle_timelapse: Action
    set_preroll: Toggle
    set_raw: Toggle
    set_audio_index: Callable[[int], None]
    set_auto_stack: Toggle
    set_motion_trigger: Toggle
    open_pictures: Action
    open_movies: Action
    show_gallery: Action


@dataclass(frozen=True, slots=True)
class CaptureOptions:
    """Initial values of the Capture tab switches.

    Attributes:
        preroll: Pre-roll switch state.
        raw: Original camera stream switch state.
        audio_device: Selected microphone index, or None.
        audio_devices: Microphones to list.
    """

    preroll: bool
    raw: bool
    audio_device: int | None
    audio_devices: Sequence[AudioDevice]


class CapturePanel:
    """Widgets of the Capture tab.

    Attributes:
        snap_btn: Snapshot button.
        stack_btn: Stacked still button, which shows stacking progress.
        burst_btn: Burst button.
        record_btn: Checkable record button, which shows the elapsed time.
        preroll_check: Pre-roll switch.
        raw_check: Original camera stream switch.
        audio_combo: Microphone choice; item data holds the device index or None.
        timelapse_spin: Seconds between time-lapse frames.
        timelapse_btn: Checkable time-lapse button.
        auto_stack_check: Automatic stacked still switch.
        motion_check: Motion snapshot switch.
        widget: The tab contents.
    """

    def __init__(self, actions: CaptureActions, options: CaptureOptions) -> None:
        self.snap_btn = button("Snapshot", actions.snapshot, name="primary")
        self.stack_btn = button(
            STACK_LABEL,
            actions.stack,
            "Averages 16 frames at 2x for a low-noise still. Hold steady for a second.",
        )
        self.burst_btn = button(
            "Burst", actions.burst, f"Saves the next {BURST_FRAMES} frames."
        )
        self.record_btn = button(
            RECORD_LABEL, actions.toggle_recording, checkable=True, name="record"
        )
        self.preroll_check = checkbox(
            f"Pre-roll: include the {PREROLL_SECONDS} s before Record",
            options.preroll,
            actions.set_preroll,
            "Not available together with microphone audio.",
        )
        self.raw_check = checkbox(
            "Record original camera stream (.mov)",
            options.raw,
            actions.set_raw,
            "Stores the camera's JPEG frames bit-exact instead of the processed view "
            "as MP4.",
        )
        self.audio_combo = self._audio_combo(options)
        self.audio_combo.currentIndexChanged.connect(actions.set_audio_index)
        self.preroll_check.setEnabled(options.audio_device is None)
        self.widget = column(
            self._capture_group(),
            self._automation_group(actions),
            group(
                "FOLDERS",
                row(
                    button("Pictures", actions.open_pictures),
                    button("Movies", actions.open_movies),
                    button("Gallery...", actions.show_gallery),
                ),
            ),
        )

    @staticmethod
    def _audio_combo(options: CaptureOptions) -> QComboBox:
        """Microphone choice with the saved device selected."""
        combo = QComboBox()
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        combo.addItem(NO_MICROPHONE, None)
        for device in options.audio_devices:
            combo.addItem(device.name, device.index)
            if device.index == options.audio_device:
                combo.setCurrentIndex(combo.count() - 1)
        combo.setToolTip(
            "Adds commentary from a microphone to recordings "
            "(macOS will ask for microphone access once)."
        )
        return combo

    def _capture_group(self) -> QWidget:
        """The CAPTURE group."""
        return group(
            "CAPTURE",
            row(self.snap_btn, self.stack_btn, self.burst_btn),
            self.record_btn,
            self.preroll_check,
            self.raw_check,
            row(QLabel("Microphone"), self.audio_combo),
        )

    def _automation_group(self, actions: CaptureActions) -> QWidget:
        """The AUTOMATION group."""
        self.timelapse_spin = QSpinBox()
        self.timelapse_spin.setRange(*TIMELAPSE_RANGE)
        self.timelapse_spin.setValue(TIMELAPSE_DEFAULT)
        self.timelapse_spin.setSuffix(" s")
        self.timelapse_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.timelapse_btn = button(
            TIMELAPSE_START_LABEL, actions.toggle_timelapse, checkable=True
        )
        self.auto_stack_check = checkbox(
            "Auto-stack when held still",
            False,
            actions.set_auto_stack,
            "Takes a stacked still automatically whenever the picture is steady "
            "for a second.",
        )
        self.motion_check = checkbox(
            "Snapshot on motion",
            False,
            actions.set_motion_trigger,
            "Saves a snapshot whenever something moves in view (3 s cooldown).",
        )
        return group(
            "AUTOMATION",
            row(QLabel("Every"), self.timelapse_spin, self.timelapse_btn),
            self.auto_stack_check,
            self.motion_check,
            small_label("Scope button: press = snapshot, hold = record on/off."),
        )
