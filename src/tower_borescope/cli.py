"""Command line for the borescope: start the application, grab, stack or record.

Usage:
    tower-borescope                                   start the application
    tower-borescope grab out.jpg [--res 480p]         save one original frame
    tower-borescope stack out.png [--res 720p]        save one stacked 2x still
    tower-borescope record out.mp4 --duration 30      record without a window
        --raw       store the camera's JPEG stream in a .mov without re-encoding
        --enhance   apply enhance to the recorded or stacked picture

Color settings saved by the application also apply to ``stack`` and ``record``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import signal
import sys
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Final

import cv2

from tower_borescope.capture.recorder import Recorder, RecorderOptions
from tower_borescope.config import SettingsStore
from tower_borescope.device.camera import Camera, device_present
from tower_borescope.device.constants import DEFAULT_MODE, FPS, MODES
from tower_borescope.device.reader import FrameSource, Reader
from tower_borescope.errors import BorescopeError
from tower_borescope.image_types import BgrImage
from tower_borescope.imaging.color import ColorGrade
from tower_borescope.imaging.enhance import enhance, finish_still
from tower_borescope.imaging.stacking import STACK_FRAMES, stack_frames
from tower_borescope.jpeg import decode_bgr

PROGRAM: Final = "tower-borescope"
JPEG_EXTENSIONS: Final = (".jpg", ".jpeg")
RAW_EXTENSIONS: Final = (".mov", ".mkv", ".avi")
DEFAULT_DURATION: Final = 10.0
STALL_TIMEOUT_SECONDS: Final = 10.0
FRAME_WAIT_SECONDS: Final = 1.0
EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_INTERRUPTED: Final = 130
NOT_FOUND_MESSAGE: Final = "No supercamera found on USB."
TERMINATING_SIGNALS: Final = (signal.SIGTERM, signal.SIGHUP)


def _saved_grade() -> ColorGrade:
    """The color grade saved by the application."""
    return ColorGrade.from_settings(SettingsStore().load())


def _require_camera() -> None:
    """Fail early with a clear message when no borescope is attached.

    Raises:
        BorescopeError: When libusb cannot load or no camera is on the bus.
    """
    if not device_present():
        raise BorescopeError(NOT_FOUND_MESSAGE)


def grab(path: Path, mode: str) -> None:
    """Save one frame: the camera's JPEG as is, or decoded for other formats.

    Args:
        path: Destination; ``.jpg`` and ``.jpeg`` keep the original bytes.
        mode: Resolution mode name.

    Raises:
        BorescopeError: When the camera cannot open or sends no frame.
    """
    with Camera(mode=mode) as camera:
        jpeg = camera.read_jpeg()
    if jpeg is None:
        raise BorescopeError("No frame received within timeout.")
    if path.suffix.lower() in JPEG_EXTENSIONS:
        path.write_bytes(jpeg)
    else:
        image = decode_bgr(jpeg)
        if image is None or not cv2.imwrite(str(path), image):
            raise BorescopeError(f"Could not save {path}")
    print(f"Saved {path}")


def frames_from(
    reader: FrameSource, stall_timeout: float = STALL_TIMEOUT_SECONDS
) -> Iterator[bytes]:
    """Yield JPEG frames from a reader, raising when the scope stays silent.

    Args:
        reader: A started frame source.
        stall_timeout: Seconds without a frame before giving up.

    Yields:
        JPEG frames in arrival order.

    Raises:
        BorescopeError: When no frame arrives for ``stall_timeout`` seconds.
    """
    silent_since: float | None = None
    while True:
        jpeg = reader.next_frame(FRAME_WAIT_SECONDS)
        if jpeg is not None:
            silent_since = None
            yield jpeg
            continue
        silent_since = silent_since or time.monotonic()
        if reader.status:
            print(reader.status, file=sys.stderr)
        if time.monotonic() - silent_since > stall_timeout:
            raise BorescopeError("No video from the scope.")


def _collect_frames(reader: FrameSource, count: int) -> list[BgrImage]:
    """Decode ``count`` frames from a started reader."""
    frames: list[BgrImage] = []
    for jpeg in frames_from(reader):
        image = decode_bgr(jpeg)
        if image is not None:
            frames.append(image)
        if len(frames) >= count:
            break
    return frames


def stack_still(path: Path, enhanced: bool, mode: str) -> None:
    """Save a still stacked from ``STACK_FRAMES`` aligned frames at twice the size.

    Args:
        path: Destination image file.
        enhanced: Whether to apply enhance to the still.
        mode: Resolution mode name.

    Raises:
        BorescopeError: When the scope sends no video or the frames do not align.
    """
    reader = Reader(mode)
    reader.start()
    try:
        frames = _collect_frames(reader, STACK_FRAMES)
    finally:
        reader.stop()
    still, used = stack_frames(frames)
    still = finish_still(_saved_grade().apply(still), enhanced)
    if not cv2.imwrite(str(path), still):
        raise BorescopeError(f"Could not save {path}")
    height, width = still.shape[:2]
    print(f"Saved {path} ({used} frames stacked, {width}x{height})")


@dataclass(slots=True)
class RecordJob:
    """One command-line recording.

    Attributes:
        path: Output video file.
        duration: Seconds to record.
        raw: Whether to store the camera's JPEG stream without re-encoding.
        enhanced: Whether to apply enhance to processed frames.
        grade: Color grade applied to processed frames.
    """

    path: Path
    duration: float
    raw: bool
    enhanced: bool
    grade: ColorGrade


class _RecordSession:
    """Opens the recorder on the first usable frame and pads dropped frames."""

    def __init__(self, job: RecordJob, reader: FrameSource) -> None:
        self.job = job
        self.reader = reader
        self.recorder: Recorder | None = None
        self.total = int(job.duration * FPS)
        self._dropped_at_write = 0

    def _image(self, jpeg: bytes) -> BgrImage | None:
        """The processed frame, or None when it does not decode."""
        image = decode_bgr(jpeg)
        if image is None:
            return None
        graded = self.job.grade.apply(image)
        return enhance(graded) if self.job.enhanced else graded

    def _open(self, size: tuple[int, int]) -> Recorder:
        """Start the recorder at ``size`` and announce the recording."""
        options = RecorderOptions(self.job.path, self.job.raw, size, fps=FPS)
        recorder = Recorder(options)
        self._dropped_at_write = self.reader.dropped
        width, height = self.reader.size
        print(
            f"Recording {self.job.duration:g}s at {width}x{height} to {self.job.path} "
            "(Ctrl-C to stop early)"
        )
        return recorder

    def feed(self, jpeg: bytes) -> bool:
        """Write one frame; True once the recording is complete or has failed."""
        image = None if self.job.raw else self._image(jpeg)
        if image is None and not self.job.raw:
            return False
        if self.recorder is None:
            size = self.reader.size if image is None else (image.shape[1], image.shape[0])
            self.recorder = self._open(size)
        dropped = self.reader.dropped
        self.recorder.write(jpeg, image, dropped - self._dropped_at_write)
        self._dropped_at_write = dropped
        return self.recorder.failed or self.recorder.frames >= self.total

    def close(self) -> bool:
        """Finish the file; True when a recording exists and closed cleanly."""
        if self.recorder is None:
            return False
        ok = self.recorder.close()
        if ok:
            print(f"Saved {self.recorder.frames / FPS:.1f}s to {self.job.path}")
        else:
            print("Recording failed (see ffmpeg error above)", file=sys.stderr)
        return ok


def record(job: RecordJob, mode: str) -> bool:
    """Record from the scope without a window.

    Args:
        job: Output file, duration, raw or processed, enhance and color grade.
        mode: Resolution mode name.

    Returns:
        True when the video was written.

    Raises:
        BorescopeError: When a raw recording has an unsupported container, ffmpeg is
            missing, or the scope sends no video.
    """
    if job.raw and job.path.suffix.lower() not in RAW_EXTENSIONS:
        raise BorescopeError("--raw recordings must be .mov, .mkv or .avi")
    reader = Reader(mode)
    reader.start()
    session = _RecordSession(job, reader)
    try:
        for jpeg in frames_from(reader):
            if session.feed(jpeg):
                break
    finally:
        reader.stop()
        saved = session.close()
    return saved


def build_parser() -> argparse.ArgumentParser:
    """The argument parser with the ``grab``, ``stack`` and ``record`` subcommands."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    helps = (
        ("grab", "save a single original frame to PATH"),
        ("stack", "save a stacked 2x still to PATH"),
        ("record", "record to PATH without opening a window"),
    )
    for name, text in helps:
        command = commands.add_parser(name, help=text)
        command.add_argument("path", metavar="PATH", type=Path)
        command.add_argument(
            "--res",
            choices=list(MODES),
            default=DEFAULT_MODE,
            help=f"camera resolution (default {DEFAULT_MODE}; 480p shows a wider view)",
        )
    record_parser = commands.choices["record"]
    record_parser.add_argument(
        "--duration", type=float, default=DEFAULT_DURATION, help="seconds (default 10)"
    )
    record_parser.add_argument(
        "--raw", action="store_true", help="record the original JPEG stream (.mov)"
    )
    for name in ("stack", "record"):
        commands.choices[name].add_argument(
            "--enhance", action="store_true", help="apply enhance"
        )
    return parser


def _terminate(_signum: int, _frame: FrameType | None) -> None:
    """Turn a termination signal into KeyboardInterrupt so readers stop cleanly."""
    raise KeyboardInterrupt


@contextlib.contextmanager
def _interrupt_on_termination() -> Iterator[None]:
    """Route SIGTERM and SIGHUP to KeyboardInterrupt, restoring handlers afterwards."""
    previous = {
        number: signal.signal(number, _terminate) for number in TERMINATING_SIGNALS
    }
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_command(args: argparse.Namespace) -> int:
    """Run a parsed subcommand.

    Args:
        args: Parsed arguments from :func:`build_parser`.

    Returns:
        The process exit status.

    Raises:
        BorescopeError: When the camera, capture or recording fails.
    """
    _require_camera()
    if args.command == "grab":
        grab(args.path, args.res)
        return EXIT_OK
    if args.command == "stack":
        stack_still(args.path, args.enhance, args.res)
        return EXIT_OK
    job = RecordJob(args.path, args.duration, args.raw, args.enhance, _saved_grade())
    return EXIT_OK if record(job, args.res) else EXIT_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``tower-borescope`` command.

    Args:
        argv: Arguments without the program name; None reads ``sys.argv``.

    Returns:
        The exit status: 0 on success, 1 on a camera or capture error, 2 for invalid
        arguments and 130 when interrupted.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        from tower_borescope.app.main import run_app

        return run_app([PROGRAM])
    try:
        args = build_parser().parse_args(arguments)
    except SystemExit as exit_request:
        return int(exit_request.code or EXIT_OK)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        with _interrupt_on_termination():
            return run_command(args)
    except BorescopeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
