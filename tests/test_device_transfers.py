"""Tests for tower_borescope.device.transfers against an in-process fake libusb."""

from __future__ import annotations

import ctypes
from collections import deque
from types import SimpleNamespace

import pytest
import usb.core

from tower_borescope.device import transfers
from tower_borescope.device.transfers import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_NO_DEVICE,
    TRANSFER_CALLBACK,
    TRANSFER_TYPE_BULK,
    AsyncBulkReader,
    LibusbHandle,
    LibusbTransfer,
)

ENDPOINT = 0x81
COUNT = 4
SIZE = 64


class CFunction:
    """A callable that accepts the ctypes prototype attributes libusb functions get."""

    def __init__(self, implementation):
        self.implementation = implementation
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.implementation(*args)


class FakeLibusb:
    """Completes queued transfers from scripted outcomes when events are handled."""

    def __init__(self, accept=True, honour_cancel=True):
        self.accept = accept
        self.honour_cancel = honour_cancel
        self.queued = deque()
        self.outcomes = deque()
        self.freed = 0
        self.submissions = 0
        self.cancelled = []
        for name in (
            "alloc_transfer",
            "submit_transfer",
            "cancel_transfer",
            "free_transfer",
            "handle_events_timeout_completed",
        ):
            setattr(self, f"libusb_{name}", CFunction(getattr(self, f"_{name}")))

    def _alloc_transfer(self, iso_packets):
        return ctypes.pointer(LibusbTransfer())

    def _submit_transfer(self, pointer):
        if not self.accept:
            return -1
        self.submissions += 1
        self.queued.append(pointer)
        return 0

    def _cancel_transfer(self, pointer):
        self.cancelled.append(pointer)
        return 0

    def _free_transfer(self, pointer):
        self.freed += 1

    def _handle_events_timeout_completed(self, context, timeval, completed):
        if self.cancelled and self.honour_cancel:
            self._finish_cancelled()
            return 0
        while self.outcomes and self.queued:
            status, data = self.outcomes.popleft()
            self._complete(self.queued.popleft(), status, data)
        return 0

    def _finish_cancelled(self):
        while self.queued:
            self._complete(self.queued.popleft(), STATUS_CANCELLED, b"")

    def _complete(self, pointer, status, data):
        transfer = pointer.contents
        ctypes.memmove(transfer.buffer, data, len(data))
        transfer.actual_length = len(data)
        transfer.status = status
        TRANSFER_CALLBACK(transfer.callback)(pointer)


def _reader(library):
    handle = LibusbHandle(library=library, context=None, device=1234)
    return AsyncBulkReader(handle, ENDPOINT, COUNT, SIZE)


def test_start_queues_bulk_transfers_on_the_endpoint():
    library = FakeLibusb()
    reader = _reader(library)
    reader.start()
    assert reader.pending == COUNT
    transfer = library.queued[0].contents
    assert (transfer.endpoint, transfer.type, transfer.length) == (
        ENDPOINT,
        TRANSFER_TYPE_BULK,
        SIZE,
    )
    assert transfer.dev_handle == 1234
    assert library.libusb_alloc_transfer.restype is not None


def test_completed_transfers_are_banked_in_order_and_resubmitted():
    library = FakeLibusb()
    reader = _reader(library)
    reader.start()
    library.outcomes.extend([(STATUS_COMPLETED, b"first"), (STATUS_COMPLETED, b"second")])
    reader.pump(5)
    assert reader.pop_packet() == b"first"
    assert reader.pop_packet() == b"second"
    assert reader.pop_packet() is None
    assert reader.pending == COUNT
    assert library.submissions == COUNT + 2


def test_errors_are_counted_until_a_transfer_succeeds():
    library = FakeLibusb()
    reader = _reader(library)
    reader.start()
    library.outcomes.extend([(STATUS_ERROR, b""), (STATUS_ERROR, b"")])
    reader.pump(5)
    assert reader.error_count == 2
    library.outcomes.append((STATUS_COMPLETED, b"ok"))
    reader.pump(5)
    assert reader.error_count == 0
    assert reader.pending == COUNT


def test_no_device_status_marks_the_reader_disconnected():
    library = FakeLibusb()
    reader = _reader(library)
    reader.start()
    library.outcomes.append((STATUS_NO_DEVICE, b""))
    reader.pump(5)
    assert reader.disconnected
    assert reader.pending == COUNT - 1


def test_stop_cancels_waits_and_frees_every_transfer():
    library = FakeLibusb()
    reader = _reader(library)
    reader.start()
    library.outcomes.append((STATUS_COMPLETED, b"left over"))
    reader.pump(5)
    reader.stop()
    assert len(library.cancelled) == COUNT
    assert reader.pending == 0
    assert library.freed == COUNT
    assert reader.pop_packet() is None
    reader.stop()
    assert library.freed == COUNT


def test_stop_keeps_transfers_allocated_when_cancellation_stalls(monkeypatch):
    monkeypatch.setattr(transfers, "STOP_TIMEOUT_SECONDS", 0.05)
    library = FakeLibusb(honour_cancel=False)
    reader = _reader(library)
    reader.start()
    reader.stop()
    assert library.freed == 0
    assert reader.pending == COUNT
    assert reader in transfers._ABANDONED


def test_start_raises_when_libusb_refuses_every_transfer():
    reader = _reader(FakeLibusb(accept=False))
    with pytest.raises(usb.core.USBError, match="could not queue"):
        reader.start()


def test_handle_is_read_from_the_pyusb_resource_manager():
    context = ctypes.c_void_p(99)
    backend = SimpleNamespace(lib="library", ctx=context)
    manager = SimpleNamespace(
        backend=backend, handle=SimpleNamespace(handle=ctypes.c_void_p(4321))
    )
    handle = LibusbHandle.from_device(SimpleNamespace(_ctx=manager))
    assert handle == LibusbHandle("library", context, 4321)
