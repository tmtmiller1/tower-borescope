"""Tests for tower_borescope.app.pipeline.recording: pre-roll, padding and failures."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from fakes import FakeReader
from synthetic import jpeg_frames
from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.processor import FrameProcessor
from tower_borescope.app.pipeline.recording import RecordingControl
from tower_borescope.app.pipeline.state import PipelineState
from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.capture import recorder as recorder_module
from tower_borescope.capture.recorder import INSTALL_HINT
from tower_borescope.device.constants import FPS
from tower_borescope.jpeg import decode_bgr

EVENT_NAMES = (
    "notice",
    "captured",
    "recording_changed",
    "timelapse_changed",
    "stack_progress",
    "vcam_changed",
)
WIDTH = 320
HEIGHT = 240

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are not installed",
)


def _events():
    calls = []

    def report(name):
        return lambda *args: calls.append((name, *args))

    return PipelineEvents(**{name: report(name) for name in EVENT_NAMES}), calls


def _control(tmp_path, **changes):
    state = PipelineState(mode="240p")
    for name, value in changes.items():
        setattr(state, name, value)
    events, calls = _events()
    control = RecordingControl(state, FrameProcessor(state), tmp_path / "movies", events)
    return control, calls


def _probe(path, entry):
    command = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0"]
    command += ["-show_entries", entry, "-of", "csv=p=0", str(path)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return result.stdout.strip().rstrip(",")


def _feed(control, frames, dropped=0, start_at=None):
    for index, jpeg in enumerate(frames):
        control.remember(jpeg, dropped)
        if start_at is not None and index == start_at:
            control.request(True)
        if start_at is None or index >= start_at:
            control.write_frame(jpeg, decode_bgr(jpeg), dropped)


def _spin(seconds):
    # QTest.qWait keeps the GIL and starves the pipeline thread; sleeping releases it.
    deadline = time.monotonic() + seconds
    while True:
        QApplication.processEvents()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.01))


def _wait_until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        _spin(0.02)
    return predicate()


@needs_ffmpeg
def test_preroll_frames_come_first_and_count(tmp_path):
    control, calls = _control(tmp_path)
    _feed(control, jpeg_frames(30, WIDTH, HEIGHT), start_at=20)
    active_while_recording = control.active
    control.finish()
    assert (active_while_recording, control.active) == (True, False)
    path = next(call[2] for call in calls if call[0] == "captured")
    assert _probe(path, "stream=nb_read_frames") == "30"
    meta = json.loads(Path(path).with_suffix(".json").read_text())
    assert (meta["kind"], meta["seconds"]) == ("video", 1.5)
    assert calls[0][:2] == ("recording_changed", True)
    assert ("notice", "Saved 1.5 s recording") in calls


@needs_ffmpeg
def test_without_preroll_only_new_frames_are_recorded(tmp_path):
    control, calls = _control(tmp_path, preroll_enabled=False)
    _feed(control, jpeg_frames(30, WIDTH, HEIGHT), start_at=20)
    control.finish()
    path = next(call[2] for call in calls if call[0] == "captured")
    assert _probe(path, "stream=nb_read_frames") == "10"


@needs_ffmpeg
def test_dropped_frames_are_padded_in_raw_recordings(tmp_path):
    control, calls = _control(tmp_path, raw_recording=True, preroll_enabled=False)
    frames = jpeg_frames(6, WIDTH, HEIGHT)
    control.request(True)
    for index, jpeg in enumerate(frames):
        dropped = 0 if index < 3 else 2
        control.remember(jpeg, dropped)
        control.write_frame(jpeg, decode_bgr(jpeg), dropped)
    control.finish()
    path = next(call[2] for call in calls if call[0] == "captured")
    assert path.endswith(".mov")
    assert _probe(path, "stream=nb_read_frames") == "8"


def test_missing_ffmpeg_reports_and_stays_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module, "find_ffmpeg", lambda: None)
    control, calls = _control(tmp_path)
    _feed(control, jpeg_frames(3, WIDTH, HEIGHT), start_at=1)
    assert not control.active
    assert ("notice", INSTALL_HINT) in calls
    assert ("recording_changed", False, "") in calls
    control.finish()


def test_stop_request_without_recording_is_harmless(tmp_path):
    control, calls = _control(tmp_path)
    control.request(False)
    control.apply_stop_request()
    control.clear_preroll()
    assert calls == [] and not control.active


@needs_ffmpeg
def test_pipeline_preroll_makes_the_clip_longer_than_the_press(qapp):
    pipeline = Pipeline({"mode": "240p"}, FakeReader)
    captured = []
    frames = []
    pipeline.captured.connect(lambda kind, path: captured.append((kind, path)))
    pipeline.frame_ready.connect(frames.append)
    pipeline.start()
    try:
        _spin(3.0)
        before_press = len(frames)
        pipeline.set_recording(True)
        assert _wait_until(lambda: pipeline.recording)
        started = len(frames)
        _spin(2.0)
        pipeline.set_recording(False)
        pressed = len(frames) - started
        assert _wait_until(lambda: any(kind == "video" for kind, _ in captured))
    finally:
        pipeline.stop()
        pipeline.wait(15000)
    video = next(path for kind, path in captured if kind == "video")
    clip_frames = float(_probe(video, "format=duration")) * FPS
    # Counts come from the same run, so a slow machine lowers both sides alike.
    assert before_press >= 10 and pressed >= 10, (before_press, pressed)
    assert clip_frames >= pressed + before_press // 2, (
        clip_frames,
        pressed,
        before_press,
    )
