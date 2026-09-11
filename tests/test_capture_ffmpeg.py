"""Tests for tower_borescope.capture.ffmpeg: executable discovery and device listing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tower_borescope.capture import ffmpeg
from tower_borescope.capture.ffmpeg import AudioDevice, find_ffmpeg, list_audio_devices

# Captured stderr of: ffmpeg -hide_banner -f avfoundation -list_devices true -i ""
DEVICE_LISTING = """\
[AVFoundation indev @ 0x14b604a40] AVFoundation video devices:
[AVFoundation indev @ 0x14b604a40] [0] FaceTime HD Camera
[AVFoundation indev @ 0x14b604a40] [1] Capture screen 0
[AVFoundation indev @ 0x14b604a40] AVFoundation audio devices:
[AVFoundation indev @ 0x14b604a40] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x14b604a40] [1] Microsoft Teams Audio
[AVFoundation indev @ 0x14b604a40] [2] USB Audio [Line In]
[in#0 @ 0x14b604700] Error opening input: Input/output error
Error opening input file .
Error opening input files: Input/output error
"""


def _fake_executable(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("")
    return path


def test_configured_path_wins_over_search_path(tmp_path, monkeypatch):
    configured = _fake_executable(tmp_path / "configured", "ffmpeg")
    searched = _fake_executable(tmp_path / "searched", "ffmpeg")
    monkeypatch.setenv("TOWER_BORESCOPE_FFMPEG_PATH", str(configured))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: str(searched))
    assert find_ffmpeg() == str(configured)


def test_missing_configured_file_falls_back_to_search_path(tmp_path, monkeypatch):
    searched = _fake_executable(tmp_path / "searched", "ffmpeg")
    monkeypatch.setenv("TOWER_BORESCOPE_FFMPEG_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: str(searched))
    assert find_ffmpeg() == str(searched)


def test_bundled_copy_beats_search_path_but_not_configuration(tmp_path, monkeypatch):
    bundled = _fake_executable(tmp_path / "bundle" / "bin", "ffmpeg")
    searched = _fake_executable(tmp_path / "searched", "ffmpeg")
    monkeypatch.delenv("TOWER_BORESCOPE_FFMPEG_PATH", raising=False)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: str(searched))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    assert find_ffmpeg() == str(bundled)
    configured = _fake_executable(tmp_path / "configured", "ffmpeg")
    monkeypatch.setenv("TOWER_BORESCOPE_FFMPEG_PATH", str(configured))
    assert find_ffmpeg() == str(configured)
    bundled.unlink()
    monkeypatch.delenv("TOWER_BORESCOPE_FFMPEG_PATH")
    assert find_ffmpeg() == str(searched)


def test_configured_directory_is_not_an_executable(tmp_path, monkeypatch):
    monkeypatch.setenv("TOWER_BORESCOPE_FFMPEG_PATH", str(tmp_path))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: None)
    assert find_ffmpeg() is None


def test_nothing_found_returns_none(monkeypatch):
    monkeypatch.delenv("TOWER_BORESCOPE_FFMPEG_PATH", raising=False)
    requested = []
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: requested.append(name))
    assert find_ffmpeg() is None
    assert requested == ["ffmpeg"]


def test_audio_devices_parsed_from_listing(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=DEVICE_LISTING)

    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)
    assert list_audio_devices() == [
        AudioDevice(0, "MacBook Pro Microphone"),
        AudioDevice(1, "Microsoft Teams Audio"),
        AudioDevice(2, "USB Audio [Line In]"),
    ]
    assert commands[0][:4] == ["ffmpeg", "-hide_banner", "-f", "avfoundation"]
    assert commands[0][4:] == ["-list_devices", "true", "-i", ""]


def test_listing_without_audio_section_is_empty(monkeypatch):
    video_only = "\n".join(DEVICE_LISTING.splitlines()[:3])
    completed = subprocess.CompletedProcess([], 1, stdout="", stderr=video_only)
    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "run", lambda command, **kwargs: completed)
    assert list_audio_devices() == []


def test_no_devices_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: None)
    assert list_audio_devices() == []


@pytest.mark.parametrize(
    "error", [OSError("exec failed"), subprocess.TimeoutExpired("ffmpeg", 10.0)]
)
def test_failed_listing_is_empty(monkeypatch, error):
    def failing_run(command, **kwargs):
        raise error

    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "run", failing_run)
    assert list_audio_devices() == []
