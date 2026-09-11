"""Locating the ffmpeg executable, listing the microphones it can record from and reading
the first frame of a video."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tower_borescope.config import bundled_file, env_value
from tower_borescope.image_types import BgrImage

FFMPEG_PATH_VARIABLE = "FFMPEG_PATH"
BUNDLED_FFMPEG = ("bin", "ffmpeg")
LIST_TIMEOUT_SECONDS = 10.0
FRAME_TIMEOUT_SECONDS = 5.0
BGR_CHANNELS = 3
_AUDIO_SECTION_MARKER = "audio devices"
_INDEX_OPENER = "] ["
_INDEX_CLOSER = "] "


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """One AVFoundation audio input that ffmpeg can capture.

    Attributes:
        index: AVFoundation device index, passed to ffmpeg as ``:<index>``.
        name: Device name as ffmpeg reports it.
    """

    index: int
    name: str


def find_ffmpeg() -> str | None:
    """Locate the ffmpeg executable.

    ``TOWER_BORESCOPE_FFMPEG_PATH`` wins when it names an existing file; then the copy
    packed into the application bundle; then the executable search path.

    Returns:
        The executable path, or None when ffmpeg is not installed.
    """
    configured = env_value(FFMPEG_PATH_VARIABLE)
    if configured is not None:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate)
    bundled = bundled_file(*BUNDLED_FFMPEG)
    if bundled is not None:
        return str(bundled)
    return shutil.which("ffmpeg")


def _parse_device_line(line: str) -> AudioDevice | None:
    """Read ``[AVFoundation indev @ 0x...] [3] Name`` into a device, if it is one."""
    if _INDEX_OPENER not in line:
        return None
    entry = line.split(_INDEX_OPENER, 1)[1]
    if _INDEX_CLOSER not in entry:
        return None
    index, name = entry.split(_INDEX_CLOSER, 1)
    if not index.isdigit():
        return None
    return AudioDevice(int(index), name.strip())


def _parse_audio_devices(listing: str) -> list[AudioDevice]:
    """Audio devices from the stderr of an AVFoundation device listing."""
    devices: list[AudioDevice] = []
    in_audio = False
    for line in listing.splitlines():
        if _AUDIO_SECTION_MARKER in line:
            in_audio = True
            continue
        device = _parse_device_line(line) if in_audio else None
        if device is not None:
            devices.append(device)
    return devices


def list_audio_devices() -> list[AudioDevice]:
    """List the microphones ffmpeg can capture through macOS AVFoundation.

    The listing only enumerates devices; no microphone is opened.

    Returns:
        Audio devices in the order ffmpeg reports them, or an empty list when ffmpeg is
        missing or the listing fails.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return []
    command = [ffmpeg, "-hide_banner", "-f", "avfoundation"]
    command += ["-list_devices", "true", "-i", ""]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=LIST_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return _parse_audio_devices(completed.stderr)


def first_frame_command(ffmpeg: str, path: Path, width: int, height: int) -> list[str]:
    """ffmpeg command that writes the first video frame as raw BGR bytes to stdout.

    Args:
        ffmpeg: ffmpeg executable.
        path: Video file.
        width: Output frame width in pixels.
        height: Output frame height in pixels.

    Returns:
        The command line.
    """
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    command += ["-i", str(path), "-an", "-frames:v", "1"]
    command += ["-vf", f"scale={width}:{height}"]
    return [*command, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]


def first_frame(path: Path, width: int, height: int) -> BgrImage | None:
    """Decode the first frame of a video, scaled to ``width`` by ``height`` pixels.

    ffmpeg decodes and scales the frame and writes it to its standard output, so the
    application needs no video decoder of its own.

    Args:
        path: Video file.
        width: Frame width in pixels.
        height: Frame height in pixels.

    Returns:
        A writable BGR frame, or None when ffmpeg is missing, cannot start, times out or
        delivers less than one frame.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return None
    try:
        completed = subprocess.run(
            first_frame_command(ffmpeg, path, width, height),
            capture_output=True,
            timeout=FRAME_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    size = width * height * BGR_CHANNELS
    if len(completed.stdout) < size:
        return None
    pixels = np.frombuffer(completed.stdout, dtype=np.uint8, count=size)
    return pixels.reshape(height, width, BGR_CHANNELS).copy()
