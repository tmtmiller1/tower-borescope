"""The ``Pipeline`` QThread: everything per frame, off the GUI thread.

The thread owns the frame source and runs decode, filters, color, enhance,
orientation, meters, recording with pre-roll, snapshots, stacking, automation and
output publishing. The window changes ``Pipeline.state`` fields and calls the request
methods; the loop picks both up on the next frame.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import QThread, Signal

from tower_borescope.app.pipeline.automation import Automation
from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.outputs import FrameOutputs
from tower_borescope.app.pipeline.processor import FrameProcessor
from tower_borescope.app.pipeline.recording import RecordingControl
from tower_borescope.app.pipeline.state import PipelineState
from tower_borescope.app.pipeline.stills import StillCapture
from tower_borescope.config import DataPaths, data_paths
from tower_borescope.device.reader import FrameSource, Reader
from tower_borescope.image_types import BgrImage
from tower_borescope.jpeg import decode_bgr
from tower_borescope.measure.shapes import OverlaySnapshot
from tower_borescope.remote.server import RemoteServer

STATS_INTERVAL_SECONDS = 0.25
FRAME_WAIT_SECONDS = 0.05


class Pipeline(QThread):
    """Frame processing thread between the camera and the window.

    Attributes:
        state: Settings read on every frame.
        last_frame: Most recent processed frame, for AI analysis, or None.
        frame_ready: Emits a ``FrameInfo`` for every processed frame.
        stats: Emits frame rate, dropped frames and status, empty while streaming.
        size_changed: Emits the camera frame width and height when they change.
        stack_progress: Emits frames collected and needed for a stacked still.
        captured: Emits the capture kind and path of every saved file.
        recording_changed: Emits the recording state and file path.
        timelapse_changed: Emits the time-lapse state and frames so far.
        notice: Emits a short message for a toast.
        button: Emits "short" or "long" for presses of the scope's button.
        vcam_changed: Emits the virtual camera state.
    """

    frame_ready = Signal(object)
    stats = Signal(float, int, str)
    size_changed = Signal(int, int)
    stack_progress = Signal(int, int)
    captured = Signal(str, str)
    recording_changed = Signal(bool, str)
    timelapse_changed = Signal(bool, int)
    notice = Signal(str)
    button = Signal(str)
    vcam_changed = Signal(bool)

    def __init__(
        self,
        settings: Mapping[str, Any],
        source_factory: Callable[[str], FrameSource] = Reader,
        paths: DataPaths | None = None,
    ) -> None:
        """Prepare the pipeline without opening the source.

        Args:
            settings: Saved settings for the initial state.
            source_factory: Builds the frame source for a mode name.
            paths: Capture folders; resolved from the environment when None.
        """
        super().__init__()
        self.state = PipelineState.from_settings(settings)
        self.last_frame: BgrImage | None = None
        resolved = paths if paths is not None else data_paths()
        self._source_factory = source_factory
        self._want_mode: str | None = None
        self._stop_requested = False
        self._last_size: tuple[int, int] | None = None
        self._last_stats = float("-inf")
        events = PipelineEvents(
            notice=self.notice.emit,
            captured=self.captured.emit,
            recording_changed=self.recording_changed.emit,
            timelapse_changed=self.timelapse_changed.emit,
            stack_progress=self.stack_progress.emit,
            vcam_changed=self.vcam_changed.emit,
        )
        self._processor = FrameProcessor(self.state)
        self._stills = StillCapture(
            self.state, self._processor, resolved.pictures, events
        )
        self._recorder = RecordingControl(
            self.state, self._processor, resolved.movies, events
        )
        self._automation = Automation(self.state, self._stills, resolved, events)
        self._outputs = FrameOutputs(self.state, events)

    @property
    def recording(self) -> bool:
        """True while a recording is open."""
        return self._recorder.active

    @property
    def remote(self) -> RemoteServer | None:
        """Phone monitor server receiving frames, or None."""
        return self._outputs.remote

    def set_mode(self, mode: str) -> None:
        """Switch the camera resolution; an open recording stops first.

        Args:
            mode: A key of ``device.constants.MODES``.
        """
        self._want_mode = mode

    def snapshot(self, overlay: OverlaySnapshot | None = None) -> None:
        """Save the next frame, with an annotated copy when ``overlay`` has items.

        Args:
            overlay: Measurements and annotations to burn into a copy, or None.
        """
        self._stills.request_snapshot(overlay)

    def stack(self) -> None:
        """Take a stacked still from the next frames."""
        self._stills.request_stack()

    def burst(self) -> None:
        """Save the next frames as a burst."""
        self._stills.request_burst()

    def set_recording(self, on: bool) -> None:
        """Start or stop recording.

        Args:
            on: True starts recording with the next frame; False stops it.
        """
        self._recorder.request(on)

    def set_remote(self, server: RemoteServer | None) -> None:
        """Publish frames to a phone monitor server, or stop publishing with None.

        Args:
            server: A started ``RemoteServer``, or None.
        """
        self._outputs.remote = server

    def reset_stabilizer(self) -> None:
        """Forget the stabilizer's camera path."""
        self._processor.reset_stabilizer()

    def reset_denoiser(self) -> None:
        """Drop the running denoise average."""
        self._processor.reset_denoiser()

    def stop(self) -> None:
        """Ask the loop to end; ``wait()`` joins the thread."""
        self._stop_requested = True

    def run(self) -> None:
        """Stream and process frames until :meth:`stop` is called."""
        source = self._source_factory(self.state.mode)
        source.start()
        try:
            while not self._stop_requested:
                self._step(source)
        finally:
            self._recorder.finish()
            self._automation.timelapse.finish()
            self._outputs.close()
            source.stop()

    def _step(self, source: FrameSource) -> None:
        """Apply requests, report statistics and process one frame if one arrives."""
        self._apply_requests(source)
        now = time.monotonic()
        if now - self._last_stats > STATS_INTERVAL_SECONDS:
            self.stats.emit(source.fps, source.dropped, source.status)
            self._last_stats = now
        jpeg = source.next_frame(FRAME_WAIT_SECONDS)
        if jpeg is None:
            return
        for event in source.pop_button_events():
            self.button.emit(event)
        self._check_size(source)
        raw = decode_bgr(jpeg)
        if raw is not None:
            self._process(jpeg, raw, source.dropped, now)

    def _apply_requests(self, source: FrameSource) -> None:
        """Mode change, recording stop, time-lapse and virtual camera requests."""
        want, self._want_mode = self._want_mode, None
        if want and want != source.mode:
            self._recorder.finish()
            source.request_mode(want)
            self.state.mode = want
            self._recorder.clear_preroll()
            self._processor.reset_filters()
        self._recorder.apply_stop_request()
        self._automation.timelapse.sync()
        self._outputs.sync_vcam(self._last_size)

    def _check_size(self, source: FrameSource) -> None:
        """Report a new frame size and reopen the virtual camera to match."""
        size = source.size
        if size != self._last_size:
            self._last_size = size
            self.size_changed.emit(*size)
            self._outputs.resize_vcam(size)

    def _process(self, jpeg: bytes, raw: BgrImage, dropped: int, now: float) -> None:
        """Run one decoded frame through capture, filters, automation and outputs."""
        self._recorder.remember(jpeg, dropped)
        self._stills.collect_stack(raw)
        motion = self._automation.measure(raw, now)
        image = self._processor.process_live(raw)
        self._recorder.write_frame(jpeg, image, dropped)
        self._stills.capture_processed(image)
        self._automation.after_frame(image, motion, now)
        self._outputs.send(image)
        info = self._processor.frame_info(raw, image, motion)
        self.last_frame = image
        self.frame_ready.emit(info)
