"""Locating the ffmpeg executable and listing the microphones it can record from."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tower_borescope.config import bundled_file, env_value

FFMPEG_PATH_VARIABLE = "FFMPEG_PATH"
BUNDLED_FFMPEG = ("bin", "ffmpeg")
LIST_TIMEOUT_SECONDS = 10.0
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
