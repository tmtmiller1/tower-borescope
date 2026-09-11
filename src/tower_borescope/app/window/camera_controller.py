"""Resolution changes and the stream statistics in the sidebar and status bar."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QLabel

from tower_borescope.app.window.camera_panel import CameraPanel
from tower_borescope.app.window.context import WindowContext
from tower_borescope.device.constants import MODES

CONNECTING_STATUS: Final = "Connecting to scope..."
STREAMING_STATUS: Final = "Streaming"
SEPARATOR: Final = "   "


class CameraController(QObject):
    """Switches resolution and shows frame rate, drops and the reader status.

    Attributes:
        ctx: Shared window state.
        panel: The CAMERA group.
        status_left: Status bar text: streaming or the reader status.
        status_right: Status bar statistics and phone viewers.
        frame_size: Width and height of the camera frames.
    """

    def __init__(
        self, ctx: WindowContext, on_mode_changed: Callable[[str], None]
    ) -> None:
        super().__init__(ctx.window)
        self.ctx = ctx
        self._on_mode_changed = on_mode_changed
        mode = MODES[ctx.pipeline.state.mode]
        self.frame_size = (mode.width, mode.height)
        self.panel = CameraPanel(self.set_resolution, ctx.pipeline.state.mode)
        self.status_left = QLabel(CONNECTING_STATUS)
        self.status_right = QLabel("")
        self.status_right.setObjectName("muted")

    def set_resolution(self, key: str) -> None:
        """Switch the camera to the mode ``key`` and remember it.

        Args:
            key: A key of ``device.constants.MODES``.
        """
        pipeline = self.ctx.pipeline
        if key == pipeline.state.mode:
            return
        if pipeline.recording:
            self.ctx.toast("Recording stopped: resolution change")
        pipeline.set_mode(key)
        self.ctx.prefs.remember(mode=key)
        mode = MODES[key]
        self.ctx.toast(f"Switching to {mode.width}x{mode.height}...")
        self.panel.show_mode(key)
        self._on_mode_changed(key)

    def on_stats(self, fps: float, dropped: int, status: str) -> None:
        """Show the reader status, or the frame rate while streaming.

        Args:
            fps: Frames per second.
            dropped: Frames dropped since the start.
            status: Reader status; empty while streaming.
        """
        view = self.ctx.view
        view.status = status
        if status:
            self.status_left.setText(status)
            self.panel.stats_label.setText(status)
        else:
            self.status_left.setText(STREAMING_STATUS)
            width, height = self.frame_size
            text = f"{width}x{height}   {fps:.1f} fps"
            if dropped:
                text += f"   dropped {dropped}"
            self.panel.stats_label.setText(text)
            remote = self.ctx.pipeline.remote
            extras = [f"{remote.viewers} phone viewer(s)"] if remote is not None else []
            self.status_right.setText(SEPARATOR.join([text, *extras]))
        view.update()

    def on_size_changed(self, width: int, height: int) -> None:
        """Remember the camera frame size for the statistics line."""
        self.frame_size = (width, height)
