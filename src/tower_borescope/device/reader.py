"""Camera reading in a separate process.

The camera drops frames whenever the host pauses reading for more than a few
milliseconds, so decoding, filtering, drawing and encoding never share the loop that
reads USB. ``Reader`` starts ``reader_process_main`` in a spawned process and receives
frames and status messages over a bounded queue.

Messages from the process are ``("open", size, mode)`` when a stream starts,
``("status", text)`` while it is down, and ``("frame", jpeg, dropped_total,
button_events)`` for each frame. Commands to the process are a mode name, which
restarts the stream at that resolution, or None, which stops it.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import queue
import time
from collections import deque
from multiprocessing.queues import Queue
from typing import Final, Literal, Protocol

import usb.core

from tower_borescope.device.camera import Camera
from tower_borescope.device.constants import FPS, MODES
from tower_borescope.errors import BorescopeError

OUTPUT_QUEUE_SIZE: Final = 64
READ_TIMEOUT_SECONDS: Final = 2.0
RETRY_STEPS: Final = 20
RETRY_STEP_SECONDS: Final = 0.1
STOP_TIMEOUT_SECONDS: Final = 5.0
DRAIN_WAIT_SECONDS: Final = 0.05
TERMINATE_JOIN_SECONDS: Final = 1.0
MIN_WAIT_SECONDS: Final = 0.001
FPS_WINDOW: Final = FPS * 2
CONNECTING_STATUS: Final = "Connecting to scope..."
NO_VIDEO_STATUS: Final = "No video from scope; reconnecting..."
DISCONNECTED_STATUS: Final = "Scope disconnected. Plug it back in..."

type ReaderMessage = (
    tuple[Literal["open"], tuple[int, int], str]
    | tuple[Literal["status"], str]
    | tuple[Literal["frame"], bytes, int, list[str]]
)
type ReaderCommand = str | None


class FrameSource(Protocol):
    """A stream of camera JPEG frames with status, rate and button gestures."""

    @property
    def mode(self) -> str:
        """Current resolution mode name."""
        ...

    @property
    def size(self) -> tuple[int, int]:
        """Frame width and height."""
        ...

    @property
    def status(self) -> str:
        """Empty while streaming, otherwise a line describing the connection."""
        ...

    @property
    def fps(self) -> float:
        """Frames per second recently delivered."""
        ...

    @property
    def dropped(self) -> int:
        """Frames lost since the source started."""
        ...

    def start(self) -> None:
        """Begin streaming."""
        ...

    def stop(self) -> None:
        """Stop streaming and release the camera."""
        ...

    def request_mode(self, mode: str) -> None:
        """Switch resolution; the stream restarts."""
        ...

    def next_frame(self, timeout: float) -> bytes | None:
        """Return the next JPEG frame, or None when none arrives within ``timeout``."""
        ...

    def pop_button_events(self) -> list[str]:
        """Return and clear button gestures, ``"short"`` or ``"long"``."""
        ...


class _ProcessLoop:
    """State of the reader process: current mode, stop flag and dropped total."""

    def __init__(
        self, commands: Queue[ReaderCommand], output: Queue[ReaderMessage], mode: str
    ) -> None:
        self.mode = mode
        self._commands = commands
        self._output = output
        self._stopped = False
        self._dropped_earlier = 0
        self._parent = os.getppid()

    def poll(self) -> bool:
        """Apply waiting commands; True when the stream has to stop or restart."""
        if os.getppid() != self._parent:
            # The parent was killed: exit rather than keep holding the camera.
            self._stopped = True
            return True
        changed = False
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return changed
            if command is None:
                self._stopped = True
                return True
            if command != self.mode:
                self.mode = command
                changed = True

    def run(self) -> None:
        """Stream until stopped, reconnecting whenever the camera goes away."""
        while True:
            self.poll()
            if self._stopped:
                return
            camera = self._connect()
            if camera is not None:
                self._stream(camera)

    def _connect(self) -> Camera | None:
        """Open the camera, or report the failure and wait before the next attempt."""
        camera = Camera(mode=self.mode, timeout=READ_TIMEOUT_SECONDS)
        try:
            camera.open()
        except (BorescopeError, usb.core.USBError) as exc:
            self._output.put(("status", f"{exc} Retrying..."))
            self._wait_to_retry()
            return None
        self._output.put(("open", camera.size, self.mode))
        return camera

    def _wait_to_retry(self) -> None:
        """Sleep before reconnecting, returning early when a command arrives."""
        for _ in range(RETRY_STEPS):
            time.sleep(RETRY_STEP_SECONDS)
            if self.poll():
                return

    def _stream(self, camera: Camera) -> None:
        """Forward frames from an open camera, then close it."""
        try:
            self._forward_frames(camera)
        except (BorescopeError, usb.core.USBError):
            self._output.put(("status", DISCONNECTED_STATUS))
        finally:
            self._dropped_earlier += camera.dropped
            camera.close()

    def _forward_frames(self, camera: Camera) -> None:
        """Send frames until a command arrives or the video stops."""
        while not self.poll():
            jpeg = camera.read_jpeg()
            if jpeg is None:
                self._output.put(("status", NO_VIDEO_STATUS))
                return
            dropped = self._dropped_earlier + camera.dropped
            message: ReaderMessage = ("frame", jpeg, dropped, camera.pop_button_events())
            try:
                self._output.put_nowait(message)
            except queue.Full:
                # The consumer is behind; skip this frame and count it.
                self._dropped_earlier += 1


def reader_process_main(
    commands: Queue[ReaderCommand], output: Queue[ReaderMessage], mode: str
) -> None:
    """Entry point of the reader process.

    Args:
        commands: Mode names that restart the stream, or None to stop.
        output: Destination for open, status and frame messages.
        mode: Resolution mode name to start with.
    """
    # On exit, do not wait for the parent to drain buffered frames.
    output.cancel_join_thread()
    _ProcessLoop(commands, output, mode).run()


class Reader:
    """Runs the camera in a spawned process and implements ``FrameSource``.

    Attributes:
        mode: Current resolution mode name.
        size: Frame size of the current stream.
        status: Empty while streaming, otherwise the latest status line.
        fps: Frame rate over the last ``FPS_WINDOW`` arrivals.
        dropped: Frames lost by the camera or skipped because the consumer lagged.

    Args:
        mode: Resolution mode name to start with.
    """

    def __init__(self, mode: str) -> None:
        selected = MODES[mode]
        self.mode = mode
        self.size = (selected.width, selected.height)
        self.status = CONNECTING_STATUS
        self.fps = 0.0
        self.dropped = 0
        self._button_events: list[str] = []
        self._await_open = False
        self._arrivals: deque[float] = deque(maxlen=FPS_WINDOW)
        context = multiprocessing.get_context("spawn")
        self._commands: Queue[ReaderCommand] = context.Queue()
        self._output: Queue[ReaderMessage] = context.Queue(maxsize=OUTPUT_QUEUE_SIZE)
        self._process = context.Process(
            target=reader_process_main,
            args=(self._commands, self._output, mode),
            daemon=True,
        )

    def start(self) -> None:
        """Start the reader process."""
        self._process.start()

    def request_mode(self, mode: str) -> None:
        """Switch resolution; the stream restarts, which takes about half a second.

        Args:
            mode: Resolution mode name.
        """
        self.mode = mode
        self._await_open = True
        self._commands.put(mode)

    def next_frame(self, timeout: float) -> bytes | None:
        """Return the next JPEG frame, applying status messages on the way.

        Args:
            timeout: Seconds to wait.

        Returns:
            The frame, or None when none arrived within ``timeout``.
        """
        deadline = time.monotonic() + timeout
        while True:
            wait = max(deadline - time.monotonic(), MIN_WAIT_SECONDS)
            try:
                message = self._output.get(timeout=wait)
            except queue.Empty:
                return None
            frame = self._accept(message)
            if frame is not None:
                return frame

    def _accept(self, message: ReaderMessage) -> bytes | None:
        """Apply one message; return the frame it carries, if any."""
        match message:
            case ("frame", jpeg, dropped, events):
                return self._accept_frame(jpeg, dropped, events)
            case ("open", size, mode):
                self.size = size
                self.mode = mode
                self.status = ""
                self._await_open = False
                self._arrivals.clear()
            case ("status", text):
                self.status = text
        return None

    def _accept_frame(self, jpeg: bytes, dropped: int, events: list[str]) -> bytes | None:
        """Record a frame, or ignore it when it predates a requested mode change."""
        if self._await_open:
            return None
        self.dropped = dropped
        self._button_events.extend(events)
        self.status = ""
        now = time.monotonic()
        self._arrivals.append(now)
        span = now - self._arrivals[0]
        if len(self._arrivals) > 1 and span > 0:
            self.fps = (len(self._arrivals) - 1) / span
        return jpeg

    def pop_button_events(self) -> list[str]:
        """Return and clear button gestures received with frames."""
        events, self._button_events = self._button_events, []
        return events

    def stop(self) -> None:
        """Ask the process to stop, draining its output, and terminate it if needed."""
        self._commands.put(None)
        deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
        while self._process.is_alive() and time.monotonic() < deadline:
            with contextlib.suppress(queue.Empty):
                self._output.get(timeout=DRAIN_WAIT_SECONDS)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(TERMINATE_JOIN_SECONDS)
