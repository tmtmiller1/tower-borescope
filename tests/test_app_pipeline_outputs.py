"""Tests for tower_borescope.app.pipeline.outputs: phone monitor and virtual camera."""

from __future__ import annotations

import pyvirtualcam

from synthetic import textured_frame
from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.outputs import OBS_HINT, FrameOutputs
from tower_borescope.app.pipeline.state import PipelineState

EVENT_NAMES = (
    "notice",
    "captured",
    "recording_changed",
    "timelapse_changed",
    "stack_progress",
    "vcam_changed",
)


def _events():
    calls = []

    def report(name):
        return lambda *args: calls.append((name, *args))

    return PipelineEvents(**{name: report(name) for name in EVENT_NAMES}), calls


class FakeCamera:
    """Stands in for pyvirtualcam.Camera."""

    opened = []

    def __init__(self, width, height, fps, fmt):
        self.size = (width, height)
        self.fps = fps
        self.fmt = fmt
        self.device = "fake cam"
        self.frames = 0
        self.closed = False
        self.fail = False
        FakeCamera.opened.append(self)

    def send(self, frame):
        if self.fail:
            raise RuntimeError("device gone")
        self.frames += 1

    def close(self):
        self.closed = True


class FakeRemote:
    """Counts published frames."""

    def __init__(self):
        self.published = 0

    def publish(self, image):
        self.published += 1


def _outputs(monkeypatch, **changes):
    FakeCamera.opened = []
    monkeypatch.setattr(pyvirtualcam, "Camera", FakeCamera)
    state = PipelineState()
    for name, value in changes.items():
        setattr(state, name, value)
    events, calls = _events()
    return FrameOutputs(state, events), state, calls


def test_frames_reach_the_remote_server(monkeypatch):
    outputs, _, calls = _outputs(monkeypatch)
    remote = FakeRemote()
    frame = textured_frame(64, 48)
    outputs.send(frame)
    outputs.remote = remote
    outputs.send(frame)
    outputs.send(frame)
    assert remote.published == 2 and calls == []


def test_virtual_camera_waits_for_a_frame_size(monkeypatch):
    outputs, _, calls = _outputs(monkeypatch, want_vcam=True)
    outputs.sync_vcam(None)
    assert (outputs.vcam_active, calls, FakeCamera.opened) == (False, [], [])


def test_virtual_camera_opens_and_sends(monkeypatch):
    outputs, _, calls = _outputs(monkeypatch, want_vcam=True)
    outputs.sync_vcam((320, 240))
    camera = FakeCamera.opened[-1]
    expected = ((320, 240), 20, pyvirtualcam.PixelFormat.BGR)
    assert (camera.size, camera.fps, camera.fmt) == expected
    assert calls == [("vcam_changed", True), ("notice", "Virtual camera on (fake cam)")]
    outputs.send(textured_frame(320, 240))
    assert (outputs.vcam_active, camera.frames) == (True, 1)


def test_clearing_the_request_closes_the_virtual_camera(monkeypatch):
    outputs, state, calls = _outputs(monkeypatch, want_vcam=True)
    outputs.sync_vcam((320, 240))
    state.want_vcam = False
    outputs.sync_vcam((320, 240))
    assert (FakeCamera.opened[-1].closed, outputs.vcam_active) == (True, False)
    assert calls[-1] == ("vcam_changed", False)


def test_rotation_swaps_the_camera_size_and_resize_reopens(monkeypatch):
    outputs, state, calls = _outputs(monkeypatch, want_vcam=True, rotation=1)
    outputs.sync_vcam((320, 240))
    assert FakeCamera.opened[-1].size == (240, 320)
    outputs.resize_vcam((160, 120))
    assert FakeCamera.opened[0].closed
    assert FakeCamera.opened[-1].size == (120, 160)
    outputs.close()
    assert FakeCamera.opened[-1].closed
    outputs.resize_vcam((320, 240))
    assert len(FakeCamera.opened) == 2


def test_send_failure_stops_the_virtual_camera(monkeypatch):
    outputs, state, calls = _outputs(monkeypatch, want_vcam=True)
    outputs.sync_vcam((320, 240))
    FakeCamera.opened[-1].fail = True
    outputs.send(textured_frame(320, 240))
    assert not outputs.vcam_active and not state.want_vcam
    assert ("notice", "Virtual camera stopped: device gone") in calls
    assert calls[-1] == ("vcam_changed", False)


def test_missing_backend_is_refused_gracefully(monkeypatch):
    def unavailable(**options):
        raise RuntimeError("no virtual camera backend found")

    monkeypatch.setattr(pyvirtualcam, "Camera", unavailable)
    events, calls = _events()
    state = PipelineState(want_vcam=True)
    outputs = FrameOutputs(state, events)
    outputs.sync_vcam((320, 240))
    assert not outputs.vcam_active and not state.want_vcam
    assert calls[0] == ("vcam_changed", False)
    assert calls[1] == ("notice", OBS_HINT + "no virtual camera backend found")


def test_real_virtual_camera_starts_or_refuses_without_raising():
    events, calls = _events()
    state = PipelineState(want_vcam=True)
    outputs = FrameOutputs(state, events)
    outputs.sync_vcam((320, 240))
    if outputs.vcam_active:
        outputs.send(textured_frame(320, 240))
        outputs.close()
        assert calls[0] == ("vcam_changed", True)
    else:
        assert not state.want_vcam
        assert calls[1][1].startswith(OBS_HINT)
