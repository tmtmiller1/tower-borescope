"""Video recording by piping frames into an ffmpeg process.

Raw recordings stream-copy the camera's MJPEG frames into a QuickTime ``.mov`` file,
bit for bit. Processed recordings pipe BGR pixels to the VideoToolbox H.264 encoder. An
optional AVFoundation microphone adds an AAC audio track from the macOS AudioToolbox
encoder (``aac_at``).
"""

from __future__ import annotations

import contextlib
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import numpy as np

from tower_borescope.capture.ffmpeg import find_ffmpeg
from tower_borescope.errors import BorescopeError
from tower_borescope.image_types import BgrImage

# Camera frame rate; equal to FPS in tower_borescope.device.constants.
DEFAULT_FPS = 20
CLOSE_TIMEOUT_SECONDS = 15.0
AUDIO_SETTLE_SECONDS = 0.3
THREAD_QUEUE_SIZE = "1024"
VIDEO_BITRATE = "6M"
AUDIO_BITRATE = "96k"
# Apple's AudioToolbox AAC encoder, present in the bundled ffmpeg and in Homebrew ffmpeg.
AUDIO_ENCODER = "aac_at"
INSTALL_HINT = "Recording needs ffmpeg; install it with: brew install ffmpeg"


@dataclass(frozen=True, slots=True)
class RecorderOptions:
    """Settings for one recording.

    Attributes:
        path: Output file; ``.mov`` for raw recordings, ``.mp4`` otherwise.
        raw: True stream-copies camera JPEGs; False encodes processed frames to H.264.
        size: ``(width, height)`` of the processed frames; unused for raw recordings.
        fps: Input frame rate.
        audio_device: AVFoundation audio device index, or None for no audio track.
    """

    path: Path
    raw: bool
    size: tuple[int, int]
    fps: int = DEFAULT_FPS
    audio_device: int | None = None


def _video_input(options: RecorderOptions) -> list[str]:
    """ffmpeg arguments describing the piped video input."""
    rate = str(options.fps)
    if options.raw:
        return ["-f", "mjpeg", "-framerate", rate, "-i", "-"]
    width, height = options.size
    geometry = ["-s", f"{width}x{height}"]
    return [
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        *geometry,
        "-framerate",
        rate,
        "-i",
        "-",
    ]


def _audio_input(device: int) -> list[str]:
    """ffmpeg arguments adding an AVFoundation microphone as an AudioToolbox AAC track."""
    source = ["-thread_queue_size", THREAD_QUEUE_SIZE, "-f", "avfoundation"]
    mapping = ["-i", f":{device}", "-map", "0:v", "-map", "1:a"]
    return [*source, *mapping, "-c:a", AUDIO_ENCODER, "-b:a", AUDIO_BITRATE]


def _video_output(raw: bool) -> list[str]:
    """ffmpeg arguments selecting the video codec and container flags."""
    if raw:
        return ["-c:v", "copy"]
    encoder = ["-c:v", "h264_videotoolbox", "-b:v", VIDEO_BITRATE]
    return [*encoder, "-pix_fmt", "yuv420p", "-tag:v", "avc1", "-movflags", "+faststart"]


def _command(ffmpeg: str, options: RecorderOptions) -> list[str]:
    """Complete ffmpeg command line for a recording."""
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    command += ["-thread_queue_size", THREAD_QUEUE_SIZE]
    if options.audio_device is not None:
        # Wall-clock timestamps keep the piped video in step with the live audio.
        command += ["-use_wallclock_as_timestamps", "1"]
    command += _video_input(options)
    if options.audio_device is not None:
        command += _audio_input(options.audio_device)
    command += _video_output(options.raw)
    command.append(str(options.path))
    return command


class Recorder:
    """Appends frames to a video file through an ffmpeg subprocess.

    Attributes:
        path: Output file.
        raw: True when camera JPEGs are stream-copied.
        size: ``(width, height)`` of processed frames.
        audio: True when a microphone track is recorded.
        frames: Frames written so far, including padding copies.
        failed: True once a write to ffmpeg has failed; later writes are ignored.
    """

    def __init__(self, options: RecorderOptions) -> None:
        """Start ffmpeg for ``options``.

        Args:
            options: Output path, mode, frame size, frame rate and audio device.

        Raises:
            BorescopeError: When ffmpeg is not installed.
        """
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            raise BorescopeError(INSTALL_HINT)
        self.path = Path(options.path)
        self.raw = options.raw
        self.size = options.size
        self.audio = options.audio_device is not None
        self.frames = 0
        self.failed = False
        self._fps = options.fps
        self._last: bytes | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(_command(ffmpeg, options), stdin=subprocess.PIPE)

    def _stdin(self) -> IO[bytes]:
        """The ffmpeg input pipe."""
        stdin = self._process.stdin
        if stdin is None:
            raise BrokenPipeError("ffmpeg input pipe is not open")
        return stdin

    def write(
        self, jpeg: bytes, image: BgrImage | None, repeat_previous: int = 0
    ) -> None:
        """Append one frame.

        Args:
            jpeg: Camera JPEG, written in raw mode.
            image: Processed BGR frame, written otherwise. A processed recording skips
                the frame when this is None.
            repeat_previous: Copies of the previous frame to write first, at most one
                second of frames, so dropped camera frames do not shorten the video.
        """
        if self.failed:
            return
        payload = jpeg if self.raw else _pixels(image)
        if payload is None:
            return
        try:
            stdin = self._stdin()
            if self._last is not None:
                for _ in range(min(repeat_previous, DEFAULT_FPS)):
                    stdin.write(self._last)
                    self.frames += 1
            stdin.write(payload)
            self.frames += 1
            self._last = payload
        except OSError:
            self.failed = True

    def close(self) -> bool:
        """Finish the file and wait for ffmpeg to exit.

        Returns:
            True when ffmpeg exited cleanly and every write succeeded.
        """
        with contextlib.suppress(OSError):
            self._stdin().close()
        if self.audio:
            # The microphone input never ends by itself; SIGINT makes ffmpeg finalize.
            time.sleep(AUDIO_SETTLE_SECONDS)
            self._process.send_signal(signal.SIGINT)
        try:
            code = self._process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
            return False
        return code == 0 and not self.failed


def _pixels(image: BgrImage | None) -> bytes | None:
    """Contiguous BGR bytes of ``image``, or None when there is no image."""
    if image is None:
        return None
    return np.ascontiguousarray(image).tobytes()
