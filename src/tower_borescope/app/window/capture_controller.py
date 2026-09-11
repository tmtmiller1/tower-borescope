"""Snapshots, stacked stills, bursts, recording, time-lapse, the scope button and the
recent captures strip."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox

from tower_borescope.app.window.capture_panel import (
    RECORD_LABEL,
    STACK_LABEL,
    TIMELAPSE_START_LABEL,
    CaptureActions,
    CaptureOptions,
    CapturePanel,
)
from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.recent_panel import RecentPanel
from tower_borescope.capture.ffmpeg import list_audio_devices

SHORT_PRESS: Final = "short"
LONG_PRESS: Final = "long"
STARTING_LABEL: Final = "Starting..."
START_RECORDING: Final = "Start Recording"
STOP_RECORDING: Final = "Stop Recording"
CLOCK_INTERVAL_MS: Final = 500
SECONDS_PER_MINUTE: Final = 60


@dataclass(frozen=True, slots=True)
class CaptureLinks:
    """What the capture controls need from the rest of the window.

    Attributes:
        show_gallery: Open the gallery.
        refresh_gallery: Reload the gallery when it is open.
        burn_in: True when snapshots also save an annotated copy.
        camera_combo: Resolution combo box, disabled while recording.
    """

    show_gallery: Callable[[], None]
    refresh_gallery: Callable[[], None]
    burn_in: Callable[[], bool]
    camera_combo: QComboBox


class CaptureController(QObject):
    """Handlers for the Capture tab and the scope's button.

    Attributes:
        ctx: Shared window state.
        panel: The Capture tab widgets.
        feedback: Progress, recording state and recent captures.
    """

    def __init__(self, ctx: WindowContext, links: CaptureLinks) -> None:
        super().__init__(ctx.window)
        self.ctx = ctx
        self._burn_in = links.burn_in
        pipeline = ctx.pipeline
        state = pipeline.state
        actions = CaptureActions(
            snapshot=self.snapshot,
            stack=pipeline.stack,
            burst=pipeline.burst,
            toggle_recording=self.toggle_recording,
            toggle_timelapse=self.toggle_timelapse,
            set_preroll=self.set_preroll,
            set_raw=self.set_raw,
            set_audio_index=self.set_audio_index,
            set_auto_stack=self.set_auto_stack,
            set_motion_trigger=self.set_motion_trigger,
            open_pictures=self.open_pictures,
            open_movies=self.open_movies,
            show_gallery=links.show_gallery,
        )
        options = CaptureOptions(
            preroll=state.preroll_enabled,
            raw=state.raw_recording,
            audio_device=state.audio_device,
            audio_devices=list_audio_devices(),
        )
        self.panel = CapturePanel(actions, options)
        self.feedback = CaptureFeedback(ctx, self.panel, links)

    def snapshot(self) -> None:
        """Save the next frame, with an annotated copy when burn-in is on."""
        overlay = self.ctx.view.overlay() if self._burn_in() else None
        self.ctx.pipeline.snapshot(overlay)

    def toggle_recording(self) -> None:
        """Start or stop recording; the button shows "Starting..." until it begins."""
        pipeline = self.ctx.pipeline
        pipeline.set_recording(not pipeline.recording)
        if not pipeline.recording:
            self.panel.record_btn.setChecked(True)
            self.panel.record_btn.setText(STARTING_LABEL)

    def toggle_timelapse(self) -> None:
        """Start a time-lapse at the chosen interval, or stop the running one."""
        state = self.ctx.pipeline.state
        if state.timelapse_interval > 0:
            state.timelapse_interval = 0.0
        else:
            state.timelapse_interval = float(self.panel.timelapse_spin.value())
            self.panel.timelapse_btn.setChecked(True)

    def set_preroll(self, on: bool) -> None:
        """Include the pre-roll in new recordings."""
        self.ctx.pipeline.state.preroll_enabled = on
        self.ctx.prefs.remember(preroll=on)

    def set_raw(self, on: bool) -> None:
        """Record the camera's original stream instead of the processed view."""
        self.ctx.pipeline.state.raw_recording = on
        self.ctx.prefs.remember(raw=on)

    def set_audio_index(self, index: int) -> None:
        """Record from the microphone at combo ``index``; pre-roll needs no microphone."""
        data = self.panel.audio_combo.itemData(index)
        device = data if isinstance(data, int) else None
        self.ctx.pipeline.state.audio_device = device
        self.panel.preroll_check.setEnabled(device is None)
        self.ctx.prefs.remember(audio_device=device)

    def set_auto_stack(self, on: bool) -> None:
        """Take a stacked still whenever the view holds still."""
        self.ctx.pipeline.state.auto_stack = on

    def set_motion_trigger(self, on: bool) -> None:
        """Take a snapshot whenever something moves in view."""
        self.ctx.pipeline.state.motion_trigger = on

    def open_pictures(self) -> None:
        """Open the pictures folder."""
        self.ctx.open_path(self.ctx.paths.pictures)

    def open_movies(self) -> None:
        """Open the movies folder."""
        self.ctx.open_path(self.ctx.paths.movies)

    def on_scope_button(self, gesture: str) -> None:
        """A short press takes a snapshot; a long press starts or stops recording."""
        if gesture == SHORT_PRESS:
            self.snapshot()
        elif gesture == LONG_PRESS:
            self.toggle_recording()


class CaptureFeedback(QObject):
    """Shows stacking progress, recording and time-lapse state, and new captures.

    Attributes:
        ctx: Shared window state.
        panel: The Capture tab widgets.
        recent: The recent captures strip.
        record_action: The File menu recording item, once the menus exist.
    """

    def __init__(
        self, ctx: WindowContext, panel: CapturePanel, links: CaptureLinks
    ) -> None:
        super().__init__(ctx.window)
        self.ctx = ctx
        self.panel = panel
        self._links = links
        self.recent = RecentPanel(ctx.open_path)
        self.record_action: QAction | None = None
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)

    def on_stack_progress(self, done: int, total: int) -> None:
        """Show stacking progress on the button, which is disabled until it finishes."""
        button = self.panel.stack_btn
        button.setText(f"Stacking {done}/{total}" if total else STACK_LABEL)
        button.setEnabled(not total)

    def on_captured(self, _kind: str, path: str) -> None:
        """Put a new capture at the front of the strip and refresh the gallery."""
        self.recent.add(Path(path), front=True)
        self._links.refresh_gallery()

    def on_recording_changed(self, on: bool, path: str) -> None:
        """Reflect the recording state on the button, menu, combo boxes and view.

        Args:
            on: True when recording started.
            path: The recording file.
        """
        self.panel.record_btn.setChecked(on)
        if self.record_action is not None:
            self.record_action.setText(STOP_RECORDING if on else START_RECORDING)
        self._links.camera_combo.setEnabled(not on)
        self.panel.audio_combo.setEnabled(not on)
        view = self.ctx.view
        if on:
            view.recording_since = time.monotonic()
            self._clock.start(CLOCK_INTERVAL_MS)
            self.ctx.toast(f"Recording to {Path(path).name}")
        else:
            view.recording_since = None
            self._clock.stop()
            self.panel.record_btn.setText(RECORD_LABEL)
        view.update()

    def on_timelapse_changed(self, running: bool, frames: int) -> None:
        """Show the time-lapse state and frame count."""
        self.panel.timelapse_btn.setChecked(running)
        text = f"Stop time-lapse ({frames})" if running else TIMELAPSE_START_LABEL
        self.panel.timelapse_btn.setText(text)
        self.panel.timelapse_spin.setEnabled(not running)

    def _tick(self) -> None:
        """Show the elapsed recording time on the record button."""
        since = self.ctx.view.recording_since
        if since is None:
            return
        minutes, seconds = divmod(int(time.monotonic() - since), SECONDS_PER_MINUTE)
        self.panel.record_btn.setText(f"Stop  {minutes:02d}:{seconds:02d}")
