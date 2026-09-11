"""Tests for tower_borescope.app.pipeline.stills: snapshots, stacks, bursts, sidecars."""

from __future__ import annotations

import json
import time

import cv2
import numpy as np

from synthetic import shifted, textured_frame
from tower_borescope.app.pipeline import stills as stills_module
from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.processor import FrameProcessor
from tower_borescope.app.pipeline.state import BURST_FRAMES, PipelineState
from tower_borescope.app.pipeline.stills import StillCapture
from tower_borescope.errors import BorescopeError
from tower_borescope.imaging.stacking import STACK_FRAMES
from tower_borescope.measure.shapes import Annotation, Measurement, OverlaySnapshot

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


def _events():
    calls = []

    def report(name):
        return lambda *args: calls.append((name, *args))

    return PipelineEvents(**{name: report(name) for name in EVENT_NAMES}), calls


def _capture(tmp_path):
    state = PipelineState(mode="240p")
    events, calls = _events()
    stills = StillCapture(state, FrameProcessor(state), tmp_path / "pictures", events)
    return stills, calls


def _overlay():
    distance = Measurement("distance", [(10.0, 10.0), (110.0, 10.0)])
    arrow = Annotation("arrow", [(20.0, 50.0), (80.0, 90.0)])
    return OverlaySnapshot([distance], [arrow], 0.05, "mm")


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_save_image_writes_png_and_sidecar(tmp_path):
    stills, calls = _capture(tmp_path)
    frame = textured_frame(WIDTH, HEIGHT)
    path = stills.save_image(frame, "snapshot")
    assert path.name.startswith("scope_") and path.suffix == ".png"
    assert cv2.imread(str(path)).shape == frame.shape
    meta = json.loads(path.with_suffix(".json").read_text())
    assert meta["kind"] == "snapshot" and meta["camera"] == "320x240"
    assert "time" in meta and "measurements" not in meta
    assert calls == [("captured", "snapshot", str(path))]


def test_overlay_items_add_an_annotated_copy(tmp_path):
    stills, calls = _capture(tmp_path)
    frame = textured_frame(WIDTH, HEIGHT)
    path = stills.save_image(frame, "snapshot", overlay=_overlay())
    annotated = path.with_name(path.stem + "_annotated.png")
    assert annotated.is_file()
    assert not np.array_equal(cv2.imread(str(annotated)), cv2.imread(str(path)))
    meta = json.loads(annotated.with_suffix(".json").read_text())
    assert meta["measurements"] == [
        {"kind": "distance", "points": [[10.0, 10.0], [110.0, 10.0]], "label": "5.00 mm"}
    ]
    assert json.loads(path.with_suffix(".json").read_text()) == meta
    assert calls == [
        ("captured", "snapshot", str(annotated)),
        ("captured", "snapshot", str(path)),
    ]


def test_empty_overlay_gives_no_annotated_copy(tmp_path):
    stills, calls = _capture(tmp_path)
    empty = OverlaySnapshot([], [], None, "mm")
    stills.save_image(textured_frame(WIDTH, HEIGHT), "snapshot", overlay=empty)
    assert not list((tmp_path / "pictures").glob("*_annotated.png"))
    assert len(calls) == 1


def test_snapshot_request_is_served_once(tmp_path):
    stills, calls = _capture(tmp_path)
    frame = textured_frame(WIDTH, HEIGHT)
    stills.request_snapshot(_overlay())
    stills.capture_processed(frame)
    stills.capture_processed(frame)
    assert ("notice", "Snapshot saved") in calls
    assert len(list((tmp_path / "pictures").glob("scope_*.png"))) == 2


def test_burst_saves_ten_frames_on_a_worker(tmp_path):
    stills, calls = _capture(tmp_path)
    stills.request_burst()
    for index in range(BURST_FRAMES + 3):
        stills.capture_processed(textured_frame(WIDTH, HEIGHT, seed=index))
    assert _wait_until(lambda: any(call[0] == "notice" for call in calls))
    folders = list((tmp_path / "pictures").glob("burst_*"))
    assert len(folders) == 1
    assert len(list(folders[0].glob("burst_*.png"))) == BURST_FRAMES
    assert ("captured", "snapshot", str(folders[0] / "burst_01.png")) in calls


def _collect_shifted_stack(stills):
    base = textured_frame(WIDTH, HEIGHT)
    states = []
    stills.request_stack()
    for index in range(STACK_FRAMES):
        stills.collect_stack(shifted(base, 0.5 * index, 0.0))
        states.append(stills.stacking)
    return states


def test_stack_needs_a_request(tmp_path):
    stills, calls = _capture(tmp_path)
    stills.collect_stack(textured_frame(WIDTH, HEIGHT))
    assert (stills.stacking, calls) == (False, [])


def test_stack_reports_progress_while_collecting(tmp_path):
    stills, calls = _capture(tmp_path)
    states = _collect_shifted_stack(stills)
    assert states == [True] * (STACK_FRAMES - 1) + [False]
    progress = [call[1:] for call in calls if call[0] == "stack_progress"]
    counts = [(count, STACK_FRAMES) for count in range(1, STACK_FRAMES + 1)]
    assert progress == [*counts, (0, 0)]


def test_stack_saves_a_larger_still(tmp_path):
    stills, calls = _capture(tmp_path)
    _collect_shifted_stack(stills)
    saved = list((tmp_path / "pictures").glob("scope_*_stack.png"))
    assert len(saved) == 1
    assert cv2.imread(str(saved[0])).shape == (HEIGHT * 2, WIDTH * 2, 3)
    notices = [call[1] for call in calls if call[0] == "notice"]
    assert notices[0].startswith("Stacked still saved (")


def test_stack_that_cannot_align_reports_the_reason(tmp_path, monkeypatch):
    def refuse(frames):
        raise BorescopeError("Could not align frames for stacking.")

    monkeypatch.setattr(stills_module, "stack_frames", refuse)
    stills, calls = _capture(tmp_path)
    stills.request_stack()
    for index in range(STACK_FRAMES):
        stills.collect_stack(textured_frame(WIDTH, HEIGHT, seed=index))
    notices = [call[1] for call in calls if call[0] == "notice"]
    assert notices == ["Could not align frames for stacking."]
    assert calls[-1] == ("stack_progress", 0, 0)
    assert not list((tmp_path / "pictures").glob("*_stack.png"))
