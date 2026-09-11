"""Tests for tower_borescope.capture.recorder: ffmpeg command lines and real encodes."""

from __future__ import annotations

import io
import json
import shutil
import signal
import subprocess

import pytest

from synthetic import jpeg_frames, textured_frame
from tower_borescope.capture import recorder
from tower_borescope.capture.recorder import DEFAULT_FPS, Recorder, RecorderOptions
from tower_borescope.config import data_paths
from tower_borescope.errors import BorescopeError

WIDTH = 320
HEIGHT = 240
AUDIO_ARGUMENT_RUNS = (
    ("-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "640x480"),
    ("-framerate", "15", "-i", "-"),
    ("-f", "avfoundation", "-i", ":2", "-map", "0:v"),
    ("-map", "1:a", "-c:a", "aac_at", "-b:a", "96k"),
    ("-c:v", "h264_videotoolbox", "-b:v", "6M"),
    ("-pix_fmt", "yuv420p", "-tag:v", "avc1"),
    ("-movflags", "+faststart"),
)

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are not installed",
)


class FakeProcess:
    """Stands in for the ffmpeg subprocess and records how it was driven."""

    def __init__(self, command, stdin=None):
        self.command = command
        self.stdin = io.BytesIO()
        self.signals = []
        self.killed = False
        self.hangs = False

    def send_signal(self, number):
        self.signals.append(number)

    def wait(self, timeout=None):
        if self.hangs and not self.killed:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return -9 if self.killed else 0

    def kill(self):
        self.killed = True


class BrokenPipe(io.BytesIO):
    """Input pipe of an ffmpeg process that has already exited."""

    def write(self, data):
        raise BrokenPipeError("ffmpeg exited")


@pytest.fixture
def fake_popen(monkeypatch):
    processes = []

    def make(command, stdin=None):
        process = FakeProcess(command, stdin)
        processes.append(process)
        return process

    monkeypatch.setattr(recorder, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(recorder.subprocess, "Popen", make)
    monkeypatch.setattr(recorder.time, "sleep", lambda seconds: None)
    return processes


def _probe(path):
    entries = "stream=codec_name,codec_tag_string,width,height,nb_read_frames"
    command = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0"]
    command += ["-show_entries", f"{entries}:format=duration", "-of", "json", str(path)]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    report = json.loads(output)
    return report["streams"][0], float(report["format"]["duration"])


def _follows(command, *arguments):
    width = len(arguments)
    runs = (tuple(command[start : start + width]) for start in range(len(command)))
    return arguments in runs


@needs_ffmpeg
def test_processed_recording_is_h264_mp4():
    path = data_paths().movies / "processed.mp4"
    frame = textured_frame(WIDTH, HEIGHT)
    video = Recorder(RecorderOptions(path, raw=False, size=(WIDTH, HEIGHT)))
    for _ in range(DEFAULT_FPS):
        video.write(b"", frame)
    assert video.close()
    assert video.frames == DEFAULT_FPS
    stream, duration = _probe(path)
    assert stream["codec_name"] == "h264"
    assert stream["codec_tag_string"] == "avc1"
    assert (stream["width"], stream["height"]) == (WIDTH, HEIGHT)
    assert int(stream["nb_read_frames"]) == DEFAULT_FPS
    assert duration == pytest.approx(1.0, abs=0.15)


@needs_ffmpeg
def test_raw_recording_copies_mjpeg_into_mov():
    path = data_paths().movies / "nested" / "raw.mov"
    frames = jpeg_frames(10, WIDTH, HEIGHT)
    video = Recorder(RecorderOptions(path, raw=True, size=(WIDTH, HEIGHT)))
    for jpeg in frames:
        video.write(jpeg, None)
    assert video.close()
    stream, duration = _probe(path)
    assert stream["codec_name"] == "mjpeg"
    assert (stream["width"], stream["height"]) == (WIDTH, HEIGHT)
    assert int(stream["nb_read_frames"]) == 10
    assert duration == pytest.approx(0.5, abs=0.1)


@needs_ffmpeg
def test_repeat_previous_pads_frames_up_to_one_second():
    path = data_paths().movies / "padded.mov"
    first, second, third = jpeg_frames(3, WIDTH, HEIGHT)
    video = Recorder(RecorderOptions(path, raw=True, size=(WIDTH, HEIGHT)))
    video.write(first, None, repeat_previous=5)
    video.write(second, None, repeat_previous=3)
    video.write(third, None, repeat_previous=500)
    assert video.close()
    expected = 1 + (3 + 1) + (DEFAULT_FPS + 1)
    assert video.frames == expected
    stream, _ = _probe(path)
    assert int(stream["nb_read_frames"]) == expected


def test_audio_command_line(fake_popen, tmp_path):
    path = tmp_path / "movies" / "voice.mp4"
    options = RecorderOptions(path, raw=False, size=(640, 480), fps=15, audio_device=2)
    video = Recorder(options)
    command = fake_popen[0].command
    assert command.index("-use_wallclock_as_timestamps") < command.index("-i")
    assert [run for run in AUDIO_ARGUMENT_RUNS if not _follows(command, *run)] == []
    assert command[-1] == str(path)
    assert path.parent.is_dir()
    assert video.close()
    assert fake_popen[0].signals == [signal.SIGINT]


def test_raw_command_line_without_audio(fake_popen, tmp_path):
    video = Recorder(RecorderOptions(tmp_path / "raw.mov", raw=True, size=(640, 480)))
    command = fake_popen[0].command
    assert "-use_wallclock_as_timestamps" not in command
    assert "avfoundation" not in command
    assert _follows(command, "-f", "mjpeg", "-framerate", str(DEFAULT_FPS), "-i", "-")
    assert _follows(command, "-c:v", "copy")
    assert video.close()
    assert fake_popen[0].signals == []


def test_close_kills_ffmpeg_that_does_not_exit(fake_popen, tmp_path):
    video = Recorder(RecorderOptions(tmp_path / "hang.mp4", raw=False, size=(64, 48)))
    fake_popen[0].hangs = True
    assert not video.close()
    assert fake_popen[0].killed


def test_pipe_error_marks_recording_failed(fake_popen, tmp_path):
    video = Recorder(RecorderOptions(tmp_path / "broken.mov", raw=True, size=(64, 48)))
    fake_popen[0].stdin = BrokenPipe()
    video.write(b"jpeg", None)
    video.write(b"jpeg", None)
    assert video.failed
    assert video.frames == 0
    assert not video.close()


def test_processed_frame_without_image_is_skipped(fake_popen, tmp_path):
    video = Recorder(RecorderOptions(tmp_path / "skip.mp4", raw=False, size=(64, 48)))
    video.write(b"jpeg", None)
    assert video.frames == 0
    assert fake_popen[0].stdin.getvalue() == b""


def test_missing_ffmpeg_raises_with_install_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "find_ffmpeg", lambda: None)
    options = RecorderOptions(tmp_path / "none.mp4", raw=False, size=(64, 48))
    with pytest.raises(BorescopeError, match="brew install ffmpeg"):
        Recorder(options)
