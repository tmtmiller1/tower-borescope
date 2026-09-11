"""Tests for tower_borescope.device.reader: process loop, parent side and hardware."""

from __future__ import annotations

import itertools
import os
import queue
import time

import pytest

from fakes import FakeReader
from synthetic import jpeg_frames
from tower_borescope.device import reader as reader_module
from tower_borescope.device.camera import device_present
from tower_borescope.device.reader import FrameSource, Reader, reader_process_main
from tower_borescope.errors import BorescopeError, CameraDisconnectedError

FRAMES = jpeg_frames(3, 160, 120)


class ScriptQueue(queue.Queue):
    """A thread queue with the multiprocessing method the process loop calls."""

    def cancel_join_thread(self):
        self.cancelled = True


class StopAfterStatus(ScriptQueue):
    """Sends the stop command as soon as a status message is written."""

    def __init__(self, commands):
        super().__init__()
        self.commands = commands

    def put(self, item, block=True, timeout=None):
        super().put(item, block, timeout)
        if item[0] == "status":
            self.commands.put(None)


class RefusesSecondFrame(ScriptQueue):
    """Reports itself full for the second frame only."""

    def __init__(self):
        super().__init__()
        self.offered = 0

    def put_nowait(self, item):
        self.offered += 1
        if self.offered == 2:
            raise queue.Full
        super().put_nowait(item)


class ScriptedCamera:
    """Stands in for Camera inside the process loop, driven by class-level scripts."""

    opened_modes = []
    open_failures = 0
    frames_per_session = 2
    after_frames = None
    commands = None
    read_error = None

    def __init__(self, mode, timeout):
        self.mode = mode
        self.size = (160, 120)
        self.dropped = 1
        self.closed = False
        self.served = 0

    def open(self):
        if ScriptedCamera.open_failures:
            ScriptedCamera.open_failures -= 1
            raise BorescopeError("Borescope not found on USB.")
        ScriptedCamera.opened_modes.append(self.mode)

    def read_jpeg(self):
        if ScriptedCamera.read_error is not None:
            raise ScriptedCamera.read_error
        if self.served == self.frames_per_session:
            ScriptedCamera.commands.put(ScriptedCamera.after_frames.pop(0))
        self.served += 1
        return FRAMES[self.served % len(FRAMES)]

    def pop_button_events(self):
        return ["short"] if self.served == 1 else []

    def close(self):
        self.closed = True


@pytest.fixture
def scripted(monkeypatch):
    """Install ScriptedCamera and return fresh command and output queues."""
    commands, output = ScriptQueue(), ScriptQueue()
    ScriptedCamera.opened_modes = []
    ScriptedCamera.open_failures = 0
    ScriptedCamera.frames_per_session = 2
    ScriptedCamera.after_frames = [None]
    ScriptedCamera.commands = commands
    ScriptedCamera.read_error = None
    monkeypatch.setattr(reader_module, "Camera", ScriptedCamera)
    monkeypatch.setattr(reader_module, "RETRY_STEP_SECONDS", 0.001)
    return commands, output


def _drain(output):
    messages = []
    while not output.empty():
        messages.append(output.get_nowait())
    return messages


def test_process_forwards_frames_and_stops_on_none(scripted):
    commands, output = scripted
    reader_process_main(commands, output, "480p")
    messages = _drain(output)
    assert output.cancelled
    assert messages[0] == ("open", (160, 120), "480p")
    kinds = [message[0] for message in messages]
    assert kinds == ["open", "frame", "frame", "frame"]
    assert messages[1][3] == ["short"]
    assert messages[2][2] == 1


def test_mode_command_restarts_the_stream(scripted):
    commands, output = scripted
    ScriptedCamera.after_frames = ["240p", None]
    reader_process_main(commands, output, "720p")
    assert ScriptedCamera.opened_modes == ["720p", "240p"]
    opens = [message for message in _drain(output) if message[0] == "open"]
    assert opens[1] == ("open", (160, 120), "240p")


def test_open_failure_reports_status_and_retries(scripted):
    commands, output = scripted
    ScriptedCamera.open_failures = 1
    reader_process_main(commands, output, "720p")
    messages = _drain(output)
    assert messages[0] == ("status", "Borescope not found on USB. Retrying...")
    assert messages[1][0] == "open"


def test_stop_during_retry_wait_exits(scripted):
    commands, _ = scripted
    ScriptedCamera.open_failures = 5
    output = StopAfterStatus(commands)
    reader_process_main(commands, output, "720p")
    assert _drain(output) == [("status", "Borescope not found on USB. Retrying...")]
    assert ScriptedCamera.opened_modes == []


def test_disconnect_reports_status(scripted):
    commands, _ = scripted
    ScriptedCamera.read_error = CameraDisconnectedError("gone")
    output = StopAfterStatus(commands)
    reader_process_main(commands, output, "720p")
    assert _drain(output)[1] == ("status", "Scope disconnected. Plug it back in...")


def test_full_output_queue_counts_skipped_frames(scripted):
    commands, _ = scripted
    output = RefusesSecondFrame()
    reader_process_main(commands, output, "720p")
    frames = _drain(output)[1:]
    assert [message[2] for message in frames] == [1, 2]


def test_parent_exit_stops_the_process(scripted, monkeypatch):
    commands, output = scripted
    parents = itertools.chain([100, 100, 100], itertools.repeat(1))
    monkeypatch.setattr(os, "getppid", lambda: next(parents))
    ScriptedCamera.frames_per_session = 50
    reader_process_main(commands, output, "720p")
    assert [message[0] for message in _drain(output)] == ["open", "frame"]


def _deliver(reader, *messages):
    for message in messages:
        reader._output.put(message)
        time.sleep(0.05)


def test_status_messages_update_the_reader():
    reader = Reader("720p")
    assert (reader.size, reader.status) == ((1280, 720), "Connecting to scope...")
    _deliver(reader, ("status", "Borescope is busy"))
    assert reader.next_frame(0.05) is None
    assert reader.status == "Borescope is busy"
    reader.stop()


def test_frames_update_drops_status_and_button_events():
    reader = Reader("720p")
    _deliver(reader, ("status", "waiting"), ("frame", FRAMES[0], 3, ["long"]))
    assert reader.next_frame(0.5) == FRAMES[0]
    assert (reader.status, reader.dropped) == ("", 3)
    assert reader.pop_button_events() == ["long"]
    assert reader.pop_button_events() == []


def test_frames_after_a_mode_request_are_skipped_until_open():
    reader = Reader("720p")
    reader.request_mode("480p")
    _deliver(reader, ("frame", FRAMES[1], 3, []))
    assert reader.next_frame(0.1) is None
    _deliver(reader, ("open", (640, 480), "480p"), ("frame", FRAMES[2], 4, []))
    assert reader.next_frame(0.5) == FRAMES[2]
    _deliver(reader, ("frame", FRAMES[0], 4, []))
    assert reader.next_frame(0.5) == FRAMES[0]
    assert (reader.mode, reader.size, reader.dropped) == ("480p", (640, 480), 4)
    assert reader.fps > 0


def test_sources_satisfy_the_frame_source_protocol():
    sources: list[FrameSource] = [Reader("240p"), FakeReader("240p")]
    assert [source.size for source in sources] == [(320, 240), (320, 240)]


def test_spawned_reader_reports_status_without_a_camera_and_stops():
    try:
        present = device_present()
    except BorescopeError:
        present = False
    if present:
        pytest.skip("a borescope is attached; covered by the camera test")
    reader = Reader("720p")
    reader.start()
    deadline = time.monotonic() + 30
    while "Retrying" not in reader.status and time.monotonic() < deadline:
        assert reader.next_frame(0.2) is None
    assert "Retrying" in reader.status
    reader.stop()
    assert not reader._process.is_alive()


@pytest.mark.camera
def test_hardware_reader_delivers_steady_frames(borescope_available):
    reader = Reader("720p")
    reader.start()
    try:
        first = None
        deadline = time.monotonic() + 15
        while first is None and time.monotonic() < deadline:
            first = reader.next_frame(0.5)
        assert first is not None, reader.status
        dropped_at_start = reader.dropped
        count = 0
        started = time.monotonic()
        while time.monotonic() - started < 3.0:
            count += reader.next_frame(0.5) is not None
        rate = count / (time.monotonic() - started)
    finally:
        reader.stop()
    assert rate >= 15
    assert reader.dropped == dropped_at_start
    assert not reader._process.is_alive()
