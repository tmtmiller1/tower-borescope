"""Recording lifecycle with the buffered pre-roll written on a background thread.

The frame loop keeps the last ``PREROLL_SECONDS`` of camera JPEGs. When recording
starts, a worker thread decodes and processes those frames into the new file while the
loop keeps running; frames that arrive meanwhile wait in a pending list and are
written by the worker once the pre-roll is done, so the file stays in order.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.processor import FrameProcessor
from tower_borescope.app.pipeline.state import PREROLL_SECONDS, PipelineState
from tower_borescope.capture.recorder import Recorder, RecorderOptions
from tower_borescope.capture.storage import capture_path, write_sidecar
from tower_borescope.device.constants import FPS
from tower_borescope.errors import BorescopeError
from tower_borescope.image_types import BgrImage
from tower_borescope.jpeg import decode_bgr, encode_jpeg

PENDING_JPEG_QUALITY = 95
RAW_EXTENSION = ".mov"
PROCESSED_EXTENSION = ".mp4"

type PrerollFrame = tuple[bytes, int]
type PendingFrame = tuple[bytes, bytes | None, int]


def _pending_payload(recorder: Recorder, image: BgrImage) -> bytes | None:
    """Compressed copy of a processed frame held until the pre-roll is written."""
    return None if recorder.raw else encode_jpeg(image, PENDING_JPEG_QUALITY)


def _write_buffered(
    recorder: Recorder,
    frames: list[PrerollFrame],
    process: Callable[[BgrImage], BgrImage],
) -> None:
    """Write buffered camera frames, processing them for processed recordings."""
    last_dropped = frames[0][1]
    for jpeg, dropped in frames:
        image = None
        if not recorder.raw:
            raw = decode_bgr(jpeg)
            if raw is None:
                continue
            image = process(raw)
        recorder.write(jpeg, image, dropped - last_dropped)
        last_dropped = dropped


def _write_pending(recorder: Recorder, pending: list[PendingFrame]) -> None:
    """Write the frames that arrived while the pre-roll was being written."""
    for jpeg, encoded, repeats in pending:
        image = decode_bgr(encoded) if encoded is not None else None
        recorder.write(jpeg, image, repeats)


class RecordingControl:
    """Starts, feeds and finishes recordings for the frame loop.

    Attributes:
        folder: Folder that receives recordings and their sidecars.
    """

    def __init__(
        self,
        state: PipelineState,
        processor: FrameProcessor,
        folder: Path,
        events: PipelineEvents,
    ) -> None:
        self.folder = folder
        self._state = state
        self._processor = processor
        self._events = events
        self._preroll: deque[PrerollFrame] = deque(maxlen=PREROLL_SECONDS * FPS)
        self._recorder: Recorder | None = None
        self._request: bool | None = None
        self._lock = threading.Lock()
        self._preroll_thread: threading.Thread | None = None
        self._pending: list[PendingFrame] = []
        self._dropped_at_write = 0

    @property
    def active(self) -> bool:
        """True while a recording is open."""
        return self._recorder is not None

    def request(self, on: bool) -> None:
        """Ask the frame loop to start or stop recording.

        Args:
            on: True starts a recording with the next frame; False stops it.
        """
        self._request = on

    def remember(self, jpeg: bytes, dropped: int) -> None:
        """Add a camera frame to the pre-roll buffer.

        Args:
            jpeg: Camera JPEG.
            dropped: Source dropped-frame total when the frame arrived.
        """
        self._preroll.append((jpeg, dropped))

    def clear_preroll(self) -> None:
        """Empty the pre-roll buffer, for example after a resolution change."""
        self._preroll.clear()

    def apply_stop_request(self) -> None:
        """Finish the recording when a stop was requested."""
        if self._request is False:
            self._request = None
            self.finish()

    def write_frame(self, jpeg: bytes, image: BgrImage, dropped: int) -> None:
        """Start a requested recording, then append the frame to an open one.

        Dropped camera frames are padded with copies of the previous frame so the
        recording keeps real time.

        Args:
            jpeg: Camera JPEG, written by raw recordings.
            image: Processed frame, written by processed recordings.
            dropped: Source dropped-frame total.
        """
        if self._request is True and self._recorder is None:
            self._request = None
            self._start(image, dropped)
        recorder = self._recorder
        if recorder is None:
            return
        repeats = dropped - self._dropped_at_write
        self._dropped_at_write = dropped
        with self._lock:
            if self._preroll_thread is not None:
                encoded = _pending_payload(recorder, image)
                self._pending.append((jpeg, encoded, repeats))
            else:
                recorder.write(jpeg, image, repeats)
        if recorder.failed:
            self.finish()

    def finish(self) -> None:
        """Close an open recording, waiting for the pre-roll writer, and report it."""
        recorder = self._recorder
        if recorder is None:
            return
        writer = self._preroll_thread
        if writer is not None:
            writer.join()
        ok = recorder.close()
        seconds = recorder.frames / FPS
        self._recorder = None
        self._events.recording_changed(False, str(recorder.path))
        if not ok:
            self._events.notice("Recording failed (ffmpeg error)")
            return
        meta = {"kind": "video", "seconds": round(seconds, 1)}
        write_sidecar(recorder.path, {**meta, **self._state.capture_metadata()})
        self._events.captured("video", str(recorder.path))
        self._events.notice(f"Saved {seconds:.1f} s recording")

    def _start(self, image: BgrImage, dropped: int) -> None:
        """Open a recorder sized for ``image`` and launch the pre-roll writer."""
        state = self._state
        extension = RAW_EXTENSION if state.raw_recording else PROCESSED_EXTENSION
        height, width = image.shape[:2]
        path = capture_path(self.folder, "", extension)
        options = RecorderOptions(
            path, state.raw_recording, (width, height), FPS, state.audio_device
        )
        try:
            recorder = Recorder(options)
        except (BorescopeError, OSError) as error:
            self._events.notice(str(error))
            self._events.recording_changed(False, "")
            return
        self._recorder = recorder
        self._dropped_at_write = dropped
        self._events.recording_changed(True, str(path))
        # The newest buffered frame is the current one, which the loop writes itself.
        frames = list(self._preroll)[:-1]
        if state.preroll_enabled and state.audio_device is None and frames:
            self._dropped_at_write = frames[-1][1]
            self._pending = []
            self._preroll_thread = threading.Thread(
                target=self._write_preroll, args=(recorder, frames), daemon=True
            )
            self._preroll_thread.start()

    def _write_preroll(self, recorder: Recorder, frames: list[PrerollFrame]) -> None:
        """Write buffered frames, then the frames that arrived meanwhile."""
        _write_buffered(recorder, frames, self._processor.process_static)
        with self._lock:
            _write_pending(recorder, self._pending)
            self._pending = []
            self._preroll_thread = None
