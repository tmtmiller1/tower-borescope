"""Tests for tower_borescope.app.pipeline.thread: the frame loop against FakeReader."""

from __future__ import annotations

import json
import shutil
import time
import urllib.request

import pytest
from PySide6.QtWidgets import QApplication

from fakes import FakeReader
from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.config import data_paths
from tower_borescope.device.reader import Reader
from tower_borescope.measure.shapes import Annotation, Measurement, OverlaySnapshot
from tower_borescope.remote.server import RemoteServer

TIMEOUT = 15.0


class Harness:
    """A running pipeline, its fake readers and every signal it emitted."""

    def __init__(self, settings, factory=None):
        self.readers = []
        self.pipeline = Pipeline(settings, factory or self._make_reader)
        self.frames, self.stats, self.sizes, self.buttons = [], [], [], []
        self.captured, self.notices, self.recording = [], [], []
        pipeline = self.pipeline
        pipeline.frame_ready.connect(lambda info: self.frames.append(info))
        pipeline.stats.connect(lambda *values: self.stats.append(values))
        pipeline.size_changed.connect(lambda *size: self.sizes.append(size))
        pipeline.button.connect(lambda gesture: self.buttons.append(gesture))
        pipeline.captured.connect(lambda *capture: self.captured.append(capture))
        pipeline.notice.connect(lambda text: self.notices.append(text))
        pipeline.recording_changed.connect(lambda *change: self.recording.append(change))

    def _make_reader(self, mode):
        reader = FakeReader(mode)
        self.readers.append(reader)
        return reader

    def kinds(self, kind):
        return [path for captured_kind, path in self.captured if captured_kind == kind]


def _spin(seconds):
    # QTest.qWait keeps the GIL and starves the pipeline thread; sleeping releases it.
    deadline = time.monotonic() + seconds
    while True:
        QApplication.processEvents()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.01))


def _wait_until(predicate, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        _spin(0.02)
    return predicate()


@pytest.fixture
def start(qapp):
    harnesses = []

    def launch(settings=None, factory=None):
        chosen = {"mode": "240p"} if settings is None else settings
        harness = Harness(chosen, factory)
        harnesses.append(harness)
        harness.pipeline.start()
        return harness

    yield launch
    for harness in harnesses:
        harness.pipeline.stop()
        assert harness.pipeline.wait(20000)


def test_streams_frames_with_meters_and_size(start):
    harness = start()
    assert _wait_until(lambda: len(harness.frames) >= 5)
    info = harness.frames[-1]
    assert isinstance(info, FrameInfo)
    assert (info.image.width(), info.image.height()) == (320, 240)
    assert (info.focus is None, info.hist is None) == (False, False)
    assert harness.sizes == [(320, 240)]
    assert harness.pipeline.last_frame.shape == (240, 320, 3)


def test_reports_stats_and_releases_the_source(start):
    harness = start()
    pipeline = harness.pipeline
    assert _wait_until(lambda: any(status == "" for _, _, status in harness.stats))
    assert (pipeline.recording, pipeline.remote) == (False, None)
    pipeline.reset_stabilizer()
    pipeline.reset_denoiser()
    pipeline.stop()
    assert pipeline.wait(10000)
    reader = harness.readers[0]
    assert (reader.started, reader.stopped) == (True, True)


def test_mode_switch_changes_frame_size(start):
    harness = start()
    assert _wait_until(lambda: harness.frames)
    harness.pipeline.set_mode("120p")
    assert _wait_until(lambda: (160, 120) in harness.sizes)
    assert _wait_until(lambda: harness.frames[-1].image.width() == 160)
    assert harness.pipeline.state.mode == "120p"
    assert harness.readers[0].mode == "120p"


def test_scope_button_gestures_are_emitted(start):
    harness = start()
    assert _wait_until(lambda: harness.frames)
    harness.readers[0].press_button("short")
    harness.readers[0].press_button("long")
    assert _wait_until(lambda: len(harness.buttons) == 2)
    assert harness.buttons == ["short", "long"]


def test_remote_publishing_reaches_a_running_server(start):
    harness = start()
    server = RemoteServer(lambda: None, lambda: False, port=0)
    server.start()
    try:
        harness.pipeline.set_remote(server)
        assert harness.pipeline.remote is server
        url = f"http://127.0.0.1:{server.port}/stream"
        with urllib.request.urlopen(url, timeout=10) as stream:
            head = stream.read(4000)
        assert b"image/jpeg" in head and b"\xff\xd8" in head
    finally:
        harness.pipeline.set_remote(None)
        server.stop()


@pytest.mark.timing
def test_every_filter_on_holds_the_frame_rate(start):
    settings = {"mode": "720p", "enhance": True, "awb": True, "stabilize": True}
    settings.update({"denoise": 0.6, "glare": 0.5, "view_mode": "Outline", "zebra": True})
    harness = start(settings)
    assert _wait_until(lambda: len(harness.frames) >= 10)
    first, began = len(harness.frames), time.monotonic()
    _spin(3.0)
    fps = (len(harness.frames) - first) / (time.monotonic() - began)
    assert fps >= 17.0, fps
    assert harness.frames[-1].image.width() == 1280


def test_snapshot_with_overlay_writes_png_sidecar_and_annotated_copy(start):
    harness = start()
    assert _wait_until(lambda: harness.frames)
    distance = Measurement("distance", [(100.0, 100.0), (300.0, 100.0)])
    note = Annotation("text", [(40.0, 40.0)], "crack here")
    harness.pipeline.snapshot(OverlaySnapshot([distance], [note], 0.05, "mm"))
    assert _wait_until(lambda: len(harness.kinds("snapshot")) == 2)
    annotated, plain = harness.kinds("snapshot")
    assert annotated.endswith("_annotated.png") and plain.endswith(".png")
    meta = json.loads(open(plain.replace(".png", ".json")).read())
    assert meta["kind"] == "snapshot" and meta["camera"] == "320x240"
    assert meta["measurements"][0]["label"] == "10.00 mm"
    assert _wait_until(lambda: "Snapshot saved" in harness.notices)
    harness.pipeline.snapshot()
    assert _wait_until(lambda: len(harness.kinds("snapshot")) == 3)


def test_stack_and_burst_save_files(start):
    harness = start()
    assert _wait_until(lambda: harness.frames)
    harness.pipeline.stack()
    harness.pipeline.burst()
    assert _wait_until(lambda: harness.kinds("stack"))
    assert harness.kinds("stack")[0].endswith("_stack.png")
    assert _wait_until(
        lambda: any(n.startswith("Burst: 10 frames") for n in harness.notices)
    )
    bursts = list(data_paths().pictures.glob("burst_*/burst_*.png"))
    assert len(bursts) == 10


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_recording_stops_on_mode_change(start):
    harness = start()
    assert _wait_until(lambda: harness.frames)
    harness.pipeline.set_recording(True)
    assert _wait_until(lambda: harness.pipeline.recording)
    _spin(0.5)
    harness.pipeline.set_mode("120p")
    assert _wait_until(lambda: not harness.pipeline.recording)
    assert _wait_until(lambda: harness.kinds("video"))
    assert harness.recording[0][0] is True and harness.recording[-1][0] is False
    assert harness.kinds("video")[0].endswith(".mp4")


@pytest.mark.timing
@pytest.mark.camera
def test_real_reader_streams_720p_at_camera_rate(start, borescope_available):
    harness = start({"mode": "720p"}, Reader)
    assert _wait_until(lambda: len(harness.frames) >= 20, timeout=20.0)
    first, began = len(harness.frames), time.monotonic()
    _spin(4.0)
    fps = (len(harness.frames) - first) / (time.monotonic() - began)
    info = harness.frames[-1]
    assert (info.image.width(), info.image.height()) == (1280, 720)
    assert fps >= 17.0, fps
