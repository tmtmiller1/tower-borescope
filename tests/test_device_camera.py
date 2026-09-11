"""Tests for tower_borescope.device.camera with a fake pyusb device and the hardware."""

from __future__ import annotations

import logging
import time
from collections import deque
from types import SimpleNamespace

import pytest
import usb.core
import usb.util

from synthetic import camera_packets, jpeg_frames
from tower_borescope.device import camera as camera_module
from tower_borescope.device.camera import Camera, device_present, probe_payload
from tower_borescope.device.constants import MAGIC_INIT, MODES, START_STREAM
from tower_borescope.errors import BorescopeError, CameraDisconnectedError
from tower_borescope.jpeg import jpeg_size

FRAME_WIDTH = 320
FRAME_HEIGHT = 240


class FakeDevice:
    """Records the calls the camera makes and fails on request."""

    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = set(fail_on)
        self.configuration = 1
        self._ctx = SimpleNamespace(
            backend=SimpleNamespace(lib=None, ctx=None),
            handle=SimpleNamespace(handle=SimpleNamespace(value=1)),
        )

    def _record(self, name, *args):
        self.calls.append((name, *args))
        if name in self.fail_on or (name, *args) in self.fail_on:
            raise usb.core.USBError(f"{name} failed")

    def get_active_configuration(self):
        self._record("get_active_configuration")
        return SimpleNamespace(bConfigurationValue=self.configuration)

    def set_configuration(self, value):
        self._record("set_configuration", value)

    def read(self, endpoint, size, timeout):
        self._record("read", endpoint)
        raise usb.core.USBError("timeout")

    def ctrl_transfer(self, *request, timeout):
        self._record("ctrl_transfer", *request)

    def set_interface_altsetting(self, interface, alternate_setting):
        self._record("set_interface_altsetting", interface, alternate_setting)

    def clear_halt(self, endpoint):
        self._record("clear_halt", endpoint)

    def write(self, endpoint, data, timeout):
        self._record("write", endpoint, bytes(data))

    def reset(self):
        self._record("reset")


class FakeBulkReader:
    """Serves synthetic camera packets in place of the libusb transfers."""

    packets: deque = deque()
    disconnect_after = None
    errors = 0
    instances = []

    def __init__(self, handle, endpoint, count, size):
        self.endpoint = endpoint
        self.started = False
        self.stopped = False
        self.served = 0
        self.disconnected = False
        self.error_count = 0
        FakeBulkReader.instances.append(self)

    def start(self):
        self.started = True

    def _cut_off(self):
        limit = FakeBulkReader.disconnect_after
        return limit is not None and self.served >= limit

    def pump(self, timeout_ms):
        self.error_count = FakeBulkReader.errors
        self.disconnected = self._cut_off()

    def pop_packet(self):
        if not FakeBulkReader.packets or self._cut_off():
            return None
        self.served += 1
        return FakeBulkReader.packets.popleft()

    def stop(self):
        self.stopped = True


def _load_packets(frame_count, button=False):
    frames = jpeg_frames(frame_count, FRAME_WIDTH, FRAME_HEIGHT)
    FakeBulkReader.packets = deque()
    for fid, jpeg in enumerate(frames):
        FakeBulkReader.packets.extend(camera_packets(jpeg, fid, button=button))
    return frames


@pytest.fixture
def usb_world(monkeypatch):
    """Patch pyusb lookups and the transfer layer; return the fake-device holder."""
    world = SimpleNamespace(devices=deque(), claimed=[], released=[], disposed=[])
    world.claim_fails = False
    FakeBulkReader.instances = []
    FakeBulkReader.disconnect_after = None
    FakeBulkReader.errors = 0

    def find(**_criteria):
        return world.devices[0] if world.devices else None

    def claim(device, interface):
        world.claimed.append(interface)
        if world.claim_fails:
            raise usb.core.USBError("Access denied")

    def dispose(device):
        world.disposed.append(device)
        if world.devices and world.devices[0] is device and len(world.devices) > 1:
            world.devices.popleft()

    monkeypatch.setattr(camera_module, "load_backend", lambda: "backend")
    monkeypatch.setattr(camera_module, "AsyncBulkReader", FakeBulkReader)
    monkeypatch.setattr(camera_module, "RETRY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(camera_module, "FIND_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(usb.core, "find", find)
    monkeypatch.setattr(usb.util, "claim_interface", claim)
    monkeypatch.setattr(
        usb.util, "release_interface", lambda device, i: world.released.append(i)
    )
    monkeypatch.setattr(usb.util, "dispose_resources", dispose)
    return world


def _open_camera(usb_world, mode="720p"):
    device = FakeDevice()
    usb_world.devices.append(device)
    frames = _load_packets(8)
    camera = Camera(mode, timeout=1.0)
    camera.open()
    return device, camera, frames


def test_probe_payload_layout():
    payload = probe_payload(MODES["480w"])
    assert len(payload) == 26
    assert payload[:8] == bytes([0, 0, 0x02, 4]) + (333333).to_bytes(4, "little")
    assert payload[8:] == bytes(18)


def test_open_discards_startup_frames_and_reads_the_frame_size(usb_world):
    _, camera, frames = _open_camera(usb_world)
    assert camera.size == (FRAME_WIDTH, FRAME_HEIGHT)
    assert camera.read_jpeg() == frames[3]
    assert camera.dropped == 0


def test_open_sends_the_start_sequence(usb_world):
    device, _, _ = _open_camera(usb_world)
    payload = probe_payload(MODES["720p"])
    sequence = [call for call in device.calls if call[0] != "read"]
    assert usb_world.claimed == [0, 1]
    assert sequence[1:] == [
        ("ctrl_transfer", 0x21, 0x01, 0x0100, 1, payload),
        ("ctrl_transfer", 0x21, 0x01, 0x0200, 1, payload),
        ("set_interface_altsetting", 1, 1),
        ("clear_halt", 0x01),
        ("clear_halt", 0x02),
        ("write", 0x02, MAGIC_INIT),
        ("write", 0x01, START_STREAM),
    ]
    assert device.calls.count(("read", 0x82)) == 1
    assert FakeBulkReader.instances[0].endpoint == 0x81


def test_configuration_is_set_when_inactive_or_unreadable(usb_world):
    device = FakeDevice(fail_on={"get_active_configuration"})
    usb_world.devices.append(device)
    _load_packets(5)
    Camera("480p", timeout=1.0).open()
    assert ("set_configuration", 1) in device.calls
    other = FakeDevice()
    other.configuration = 2
    usb_world.devices[0] = other
    _load_packets(5)
    Camera("480p", timeout=1.0).open()
    assert ("set_configuration", 1) in other.calls


def test_probe_and_init_write_failures_are_not_fatal(usb_world, caplog):
    device = FakeDevice(fail_on={"ctrl_transfer", ("write", 0x02, MAGIC_INIT)})
    usb_world.devices.append(device)
    _load_packets(5)
    camera = Camera("240p", timeout=1.0)
    with caplog.at_level(logging.WARNING):
        camera.open()
    assert "Could not set 240p" in caplog.text
    assert ("write", 0x01, START_STREAM) in device.calls


def test_busy_device_raises_without_reset(usb_world):
    device = FakeDevice()
    usb_world.devices.append(device)
    usb_world.claim_fails = True
    with pytest.raises(BorescopeError, match="busy"):
        Camera(timeout=1.0).open()
    assert ("reset",) not in device.calls
    assert usb_world.disposed == [device]


def test_usb_error_during_start_resets_and_retries(usb_world):
    failing = FakeDevice(fail_on={("write", 0x01, START_STREAM)})
    working = FakeDevice()
    usb_world.devices.extend([failing, working])
    _load_packets(5)
    camera = Camera(timeout=1.0)
    camera.open()
    assert ("reset",) in failing.calls
    assert usb_world.disposed == [failing]
    assert ("write", 0x01, START_STREAM) in working.calls


def test_three_failed_starts_raise(usb_world):
    device = FakeDevice(fail_on={"clear_halt"})
    usb_world.devices.append(device)
    with pytest.raises(BorescopeError, match="Could not start the borescope"):
        Camera(timeout=1.0).open()
    assert device.calls.count(("reset",)) == 3


def test_no_video_after_start_counts_as_a_failed_attempt(usb_world):
    usb_world.devices.append(FakeDevice())
    FakeBulkReader.packets = deque()
    with pytest.raises(BorescopeError, match="no video after start"):
        Camera(timeout=0.05).open()
    assert len(FakeBulkReader.instances) == 3
    assert all(reader.stopped for reader in FakeBulkReader.instances)


def test_missing_device_raises_not_found(usb_world):
    with pytest.raises(BorescopeError, match="not found"):
        Camera().open()
    assert not device_present()
    usb_world.devices.append(FakeDevice())
    assert device_present()


def test_disconnect_and_repeated_errors_raise_camera_disconnected(usb_world):
    usb_world.devices.append(FakeDevice())
    _load_packets(6)
    camera = Camera(timeout=1.0)
    camera.open()
    FakeBulkReader.disconnect_after = 0
    with pytest.raises(CameraDisconnectedError):
        camera.read_jpeg()
    FakeBulkReader.disconnect_after = None
    FakeBulkReader.errors = 51
    FakeBulkReader.packets.clear()
    with pytest.raises(CameraDisconnectedError, match="repeated"):
        camera.read_jpeg()


def test_read_times_out_with_none_and_requires_open(usb_world):
    with pytest.raises(BorescopeError, match="not open"):
        Camera().read_jpeg()
    usb_world.devices.append(FakeDevice())
    _load_packets(4)
    camera = Camera(timeout=0.05)
    camera.open()
    FakeBulkReader.packets.clear()
    assert camera.read_jpeg() is None


def test_close_releases_without_reset_and_tolerates_errors(usb_world):
    device = FakeDevice()
    usb_world.devices.append(device)
    _load_packets(5)
    camera = Camera(timeout=1.0)
    with camera:
        device.fail_on = {"set_interface_altsetting"}
    assert device.calls[-1] == ("set_interface_altsetting", 1, 0)
    assert usb_world.released == [1, 0]
    assert usb_world.disposed == [device]
    assert ("reset",) not in device.calls
    assert FakeBulkReader.instances[-1].stopped
    camera.close()
    assert usb_world.disposed == [device]


def test_button_gestures_are_reported(usb_world):
    usb_world.devices.append(FakeDevice())
    _load_packets(5, button=True)
    camera = Camera(timeout=1.0)
    camera.open()
    assert camera.pop_button_events() == []
    time.sleep(0.35)
    assert camera.pop_button_events() == ["short"]


@pytest.mark.camera
def test_hardware_720p_frame(borescope_available):
    with Camera("720p") as camera:
        jpeg = camera.read_jpeg()
    assert jpeg is not None
    assert jpeg_size(jpeg) == (1280, 720)
    assert camera.size == (1280, 720)


@pytest.mark.camera
def test_hardware_switch_to_480p(borescope_available):
    with Camera("480p") as camera:
        jpeg = camera.read_jpeg()
    assert jpeg is not None
    assert jpeg_size(jpeg) == (640, 480)


@pytest.mark.camera
def test_hardware_reopen_after_close_needs_no_reset(borescope_available, monkeypatch):
    resets = []
    original = usb.core.Device.reset
    monkeypatch.setattr(
        usb.core.Device, "reset", lambda self: resets.append(self) or original(self)
    )
    with Camera("720p") as first:
        assert first.read_jpeg() is not None
    with Camera("720p") as second:
        assert second.read_jpeg() is not None
    assert resets == []
