"""Tests for tower_borescope.cli: argument parsing, error paths and the application start
offline, and grabbing and recording with the borescope."""

from __future__ import annotations

import signal

import cv2
import pytest

from fakes import FakeReader
from synthetic import jpeg_frames
from tower_borescope import cli
from tower_borescope.capture.ffmpeg import find_ffmpeg
from tower_borescope.device.constants import DEFAULT_MODE, MODES
from tower_borescope.errors import BorescopeError

JPEG_MAGIC = b"\xff\xd8"


class FakeCamera:
    frame = jpeg_frames(1, 64, 48)[0]

    def __init__(self, mode):
        self.mode = mode

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def read_jpeg(self):
        return self.frame


class SilentReader:
    status = "Connecting to scope..."

    def next_frame(self, timeout):
        return None


@pytest.fixture
def camera_attached(monkeypatch):
    monkeypatch.setattr(cli, "device_present", lambda: True)


def test_parser_reads_every_subcommand():
    parser = cli.build_parser()
    grab = parser.parse_args(["grab", "out.jpg"])
    assert (grab.command, str(grab.path), grab.res) == ("grab", "out.jpg", DEFAULT_MODE)
    stack = parser.parse_args(["stack", "still.png", "--res", "480p", "--enhance"])
    assert (stack.command, stack.res, stack.enhance) == ("stack", "480p", True)
    record = parser.parse_args(["record", "a.mov", "--duration", "3", "--raw"])
    assert (record.duration, record.raw, record.enhance) == (3.0, True, False)
    assert parser.parse_args(["record", "a.mp4"]).duration == 10.0
    choices = parser._subparsers._group_actions[0].choices["grab"]._actions
    res = next(action for action in choices if action.dest == "res")
    assert list(res.choices) == list(MODES)


def test_invalid_arguments_return_usage_status(capsys):
    assert cli.main(["grab", "x.jpg", "--res", "4k"]) == 2
    assert "invalid choice" in capsys.readouterr().err
    assert cli.main(["record"]) == 2
    assert cli.main(["bogus"]) == 2
    assert cli.main(["--help"]) == 0
    assert "grab" in capsys.readouterr().out


def test_missing_camera_prints_an_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "device_present", lambda: False)
    assert cli.main(["grab", str(tmp_path / "frame.jpg")]) == 1
    assert "No supercamera found on USB." in capsys.readouterr().err


def test_libusb_failure_prints_an_error(monkeypatch, tmp_path, capsys):
    def broken():
        raise BorescopeError("libusb could not be loaded")

    monkeypatch.setattr(cli, "device_present", broken)
    assert cli.main(["stack", str(tmp_path / "still.png")]) == 1
    assert "libusb could not be loaded" in capsys.readouterr().err


def test_raw_recording_needs_a_raw_container(
    camera_attached, monkeypatch, tmp_path, capsys
):
    started = []
    monkeypatch.setattr(cli, "Reader", lambda mode: started.append(mode))
    assert cli.main(["record", str(tmp_path / "clip.mp4"), "--raw"]) == 1
    assert "--raw recordings must be .mov, .mkv or .avi" in capsys.readouterr().err
    assert started == []


def test_grab_writes_jpeg_bytes_or_decoded_images(camera_attached, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "Camera", FakeCamera)
    jpeg = tmp_path / "frame.jpg"
    assert cli.main(["grab", str(jpeg), "--res", "240p"]) == 0
    assert jpeg.read_bytes() == FakeCamera.frame
    png = tmp_path / "frame.png"
    assert cli.main(["grab", str(png)]) == 0
    assert cv2.imread(str(png)).shape == (48, 64, 3)


def test_grab_without_a_frame_fails(camera_attached, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(FakeCamera, "read_jpeg", lambda self: None)
    monkeypatch.setattr(cli, "Camera", FakeCamera)
    assert cli.main(["grab", str(tmp_path / "frame.jpg")]) == 1
    assert "No frame received" in capsys.readouterr().err


def test_stack_saves_a_double_size_still(camera_attached, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "Reader", FakeReader)
    still = tmp_path / "still.png"
    assert cli.main(["stack", str(still), "--res", "240p"]) == 0
    assert cv2.imread(str(still)).shape == (480, 640, 3)
    assert "frames stacked, 640x480" in capsys.readouterr().out


@pytest.mark.skipif(find_ffmpeg() is None, reason="needs ffmpeg")
@pytest.mark.parametrize(
    "name, extra", [("clip.mp4", ["--enhance"]), ("raw.mov", ["--raw"])]
)
def test_record_writes_a_video(camera_attached, monkeypatch, tmp_path, name, extra):
    monkeypatch.setattr(cli, "Reader", FakeReader)
    video = tmp_path / name
    args = ["record", str(video), "--res", "240p", "--duration", "0.5", *extra]
    assert cli.main(args) == 0
    assert video.stat().st_size > 0


def test_frames_from_gives_up_on_a_silent_scope(capsys):
    with pytest.raises(BorescopeError, match="No video from the scope"):
        next(cli.frames_from(SilentReader(), stall_timeout=-1.0))
    assert "Connecting to scope..." in capsys.readouterr().err


def test_interrupt_returns_130_and_restores_signal_handlers(camera_attached, monkeypatch):
    before = signal.getsignal(signal.SIGTERM)

    def interrupted(args):
        assert signal.getsignal(signal.SIGTERM) is cli._terminate
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_command", interrupted)
    assert cli.main(["grab", "frame.jpg"]) == 130
    assert signal.getsignal(signal.SIGTERM) is before


def test_no_arguments_start_the_application(monkeypatch):
    from tower_borescope.app import main as app_main

    calls = []
    monkeypatch.setattr(app_main, "run_app", lambda argv: calls.append(argv) or 0)
    assert cli.main([]) == 0
    assert calls == [["tower-borescope"]]


@pytest.mark.camera
def test_grab_from_the_borescope(borescope_available, tmp_path):
    frame = tmp_path / "grab.jpg"
    assert cli.main(["grab", str(frame)]) == 0
    assert frame.read_bytes().startswith(JPEG_MAGIC)


@pytest.mark.camera
def test_record_three_seconds_from_the_borescope(borescope_available, tmp_path):
    video = tmp_path / "record.mp4"
    assert cli.main(["record", str(video), "--duration", "3"]) == 0
    assert video.stat().st_size > 0
