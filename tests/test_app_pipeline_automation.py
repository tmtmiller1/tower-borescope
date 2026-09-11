"""Tests for tower_borescope.app.pipeline.automation: time-lapse, auto stack, motion."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from fakes import FakeReader
from synthetic import textured_frame
from tower_borescope.app.pipeline import automation
from tower_borescope.app.pipeline.automation import (
    Automation,
    TimeLapse,
    timelapse_command,
)
from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.state import PipelineState
from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.config import data_paths

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
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed"
)


def _events():
    calls = []

    def report(name):
        return lambda *args: calls.append((name, *args))

    return PipelineEvents(**{name: report(name) for name in EVENT_NAMES}), calls


class FakeStills:
    """Records the requests automation makes."""

    def __init__(self):
        self.stacking = False
        self.stacks = 0
        self.saved = []

    def request_stack(self):
        self.stacks += 1

    def save_image(self, image, kind):
        self.saved.append(kind)


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


def test_timelapse_command_encodes_numbered_frames():
    command = timelapse_command("ffmpeg", Path("frames"), Path("out.mp4"))
    assert command[0] == "ffmpeg" and command[-1] == "out.mp4"
    assert command[command.index("-i") + 1] == str(Path("frames") / "frame_%05d.png")
    assert command[command.index("-framerate") + 1] == "10"
    assert "h264_videotoolbox" in command


def _run_timelapse(state, events):
    timelapse = TimeLapse(state, data_paths(), events)
    timelapse.sync()
    frame = textured_frame(WIDTH, HEIGHT)
    for now in (10.0, 10.5, 11.0, 12.5):
        timelapse.capture(frame, now)
    return timelapse


def test_timelapse_writes_frames_on_the_interval(qapp):
    state = PipelineState(timelapse_interval=1.0)
    events, calls = _events()
    timelapse = _run_timelapse(state, events)
    assert timelapse.running
    assert calls == [("timelapse_changed", True, count) for count in range(4)]
    frames = sorted(p.name for p in data_paths().pictures.glob("timelapse_*/*.png"))
    assert frames == ["frame_00001.png", "frame_00002.png", "frame_00003.png"]


@needs_ffmpeg
def test_timelapse_assembles_a_video_when_stopped(qapp):
    state = PipelineState(timelapse_interval=1.0)
    events, calls = _events()
    timelapse = _run_timelapse(state, events)
    state.timelapse_interval = 0.0
    timelapse.sync()
    assert (timelapse.running, calls[4]) == (False, ("timelapse_changed", False, 3))
    assert _wait_until(lambda: any(call[0] == "captured" for call in calls))
    video = Path(next(call[2] for call in calls if call[0] == "captured"))
    assert (video.parent, video.suffix) == (data_paths().movies, ".mp4")
    assert video.stat().st_size > 0
    assert ("notice", "Time-lapse saved (3 frames)") in calls


def test_short_timelapse_is_not_assembled(qapp):
    state = PipelineState(timelapse_interval=1.0)
    events, calls = _events()
    timelapse = TimeLapse(state, data_paths(), events)
    timelapse.sync()
    timelapse.capture(textured_frame(WIDTH, HEIGHT), 1.0)
    timelapse.finish()
    timelapse.finish()
    assert calls[-1] == ("timelapse_changed", False, 1)


def test_missing_ffmpeg_keeps_the_frames(monkeypatch):
    monkeypatch.setattr(automation, "find_ffmpeg", lambda: None)
    state = PipelineState(timelapse_interval=0.5)
    events, calls = _events()
    timelapse = TimeLapse(state, data_paths(), events)
    timelapse.sync()
    for now in (1.0, 2.0):
        timelapse.capture(textured_frame(WIDTH, HEIGHT), now)
    timelapse.finish()
    assert _wait_until(lambda: any(call[0] == "notice" for call in calls))
    notice = next(call[1] for call in calls if call[0] == "notice")
    assert notice.startswith("Time-lapse video failed; frames are in ")


def test_holding_still_requests_one_stack_per_steady_period():
    state = PipelineState(auto_stack=True)
    stills = FakeStills()
    events, calls = _events()
    auto = Automation(state, stills, data_paths(), events)
    still_frame = textured_frame(WIDTH, HEIGHT)
    moving_frame = textured_frame(WIDTH, HEIGHT, seed=9)
    for now in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5):
        auto.after_frame(still_frame, auto.measure(still_frame, now), now)
    assert stills.stacks == 1
    assert ("notice", "Holding still: taking a stacked still") in calls
    auto.after_frame(moving_frame, auto.measure(moving_frame, 3.0), 3.0)
    for now in (3.5, 4.0, 4.5, 5.0):
        auto.after_frame(moving_frame, auto.measure(moving_frame, now), now)
    assert stills.stacks == 2


def test_auto_stack_waits_while_a_stack_is_collecting():
    state = PipelineState(auto_stack=True)
    stills = FakeStills()
    stills.stacking = True
    auto = Automation(state, stills, data_paths(), _events()[0])
    frame = textured_frame(WIDTH, HEIGHT)
    for now in (0.0, 1.0, 2.0):
        auto.after_frame(frame, auto.measure(frame, now), now)
    assert stills.stacks == 0
    stills.stacking = False
    auto.after_frame(frame, auto.measure(frame, 3.0), 3.0)
    assert stills.stacks == 1


def test_auto_stack_off_requests_nothing():
    stills = FakeStills()
    auto = Automation(PipelineState(), stills, data_paths(), _events()[0])
    frame = textured_frame(WIDTH, HEIGHT)
    for now in (0.0, 2.0, 4.0):
        auto.after_frame(frame, auto.measure(frame, now), now)
    assert stills.stacks == 0 and stills.saved == []


def test_motion_snapshot_respects_the_cooldown():
    state = PipelineState(motion_trigger=True)
    stills = FakeStills()
    events, calls = _events()
    auto = Automation(state, stills, data_paths(), events)
    frame = textured_frame(WIDTH, HEIGHT)
    strong = auto.motion.threshold * 2 + 1
    for now, level in ((10.0, strong), (11.0, strong), (12.0, 1.0), (13.5, strong)):
        auto.after_frame(frame, level, now)
    assert stills.saved == ["motion", "motion"]
    assert calls.count(("notice", "Motion: snapshot saved")) == 2


@needs_ffmpeg
def test_pipeline_timelapse_assembles_an_mp4(qapp):
    pipeline = Pipeline({"mode": "240p"}, FakeReader)
    counts = []
    videos = []
    pipeline.timelapse_changed.connect(lambda running, count: counts.append(count))
    pipeline.captured.connect(lambda kind, path: videos.append(path))
    pipeline.start()
    try:
        pipeline.state.timelapse_interval = 0.2
        assert _wait_until(lambda: counts and counts[-1] >= 4)
        pipeline.state.timelapse_interval = 0.0
        assert _wait_until(lambda: any(path.endswith(".mp4") for path in videos))
    finally:
        pipeline.stop()
        pipeline.wait(15000)
    video = Path(next(path for path in videos if path.endswith(".mp4")))
    assert video.name.startswith("timelapse_") and video.stat().st_size > 0
    frames = list(data_paths().pictures.glob("timelapse_*/frame_*.png"))
    assert len(frames) >= 4
