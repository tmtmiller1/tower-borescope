"""Asynchronous libusb bulk reads through ctypes.

pyusb offers only synchronous reads, which leave gaps with nothing queued for the USB
controller. The camera has almost no buffer and drops a frame when the host is not
reading within a few milliseconds, so this module keeps a pool of libusb transfers
queued on the video endpoint. Completed transfers are banked by a callback and
resubmitted at once; ``pump`` runs the libusb event loop that invokes the callback.
"""

from __future__ import annotations

import ctypes
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Final

import usb.core

TRANSFER_TYPE_BULK: Final = 2
STATUS_COMPLETED: Final = 0
STATUS_ERROR: Final = 1
STATUS_TIMED_OUT: Final = 2
STATUS_CANCELLED: Final = 3
STATUS_STALL: Final = 4
STATUS_NO_DEVICE: Final = 5
STATUS_OVERFLOW: Final = 6
STOP_TIMEOUT_SECONDS: Final = 2.0
STOP_PUMP_MS: Final = 100
_MS_PER_SECOND: Final = 1000
_US_PER_MS: Final = 1000


class LibusbTransfer(ctypes.Structure):
    """``struct libusb_transfer`` without the trailing isochronous packet array."""

    _fields_ = [
        ("dev_handle", ctypes.c_void_p),
        ("flags", ctypes.c_uint8),
        ("endpoint", ctypes.c_ubyte),
        ("type", ctypes.c_ubyte),
        ("timeout", ctypes.c_uint),
        ("status", ctypes.c_int),
        ("length", ctypes.c_int),
        ("actual_length", ctypes.c_int),
        ("callback", ctypes.c_void_p),
        ("user_data", ctypes.c_void_p),
        ("buffer", ctypes.POINTER(ctypes.c_ubyte)),
        ("num_iso_packets", ctypes.c_int),
    ]


class LibusbTimeval(ctypes.Structure):
    """``struct timeval`` for ``libusb_handle_events_timeout_completed``."""

    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


TRANSFER_CALLBACK: Final = ctypes.CFUNCTYPE(None, ctypes.POINTER(LibusbTransfer))

# Readers whose transfers were still in flight at stop. They stay referenced so libusb
# never calls a freed callback or writes into a freed buffer.
_ABANDONED: list[AsyncBulkReader] = []


@dataclass(frozen=True, slots=True)
class LibusbHandle:
    """The libusb objects behind one open pyusb device.

    Attributes:
        library: The loaded libusb ``ctypes`` library.
        context: The libusb context pointer the backend was initialised with.
        device: The ``libusb_device_handle`` address.
    """

    library: Any
    context: Any
    device: int | None

    @classmethod
    def from_device(cls, device: Any) -> LibusbHandle:
        """Read the libusb handle from a pyusb device that has been opened.

        pyusb exposes no public accessor, so this reads its resource manager. The
        device must already be open, which claiming an interface guarantees.

        Args:
            device: A ``usb.core.Device`` from the libusb 1.0 backend.

        Returns:
            The library, context and device handle.
        """
        manager = device._ctx
        backend = manager.backend
        return cls(backend.lib, backend.ctx, manager.handle.handle.value)


def _bind_prototypes(library: Any) -> None:
    """Declare argument and result types for the libusb calls used here."""
    transfer_pointer = ctypes.POINTER(LibusbTransfer)
    library.libusb_alloc_transfer.restype = transfer_pointer
    library.libusb_alloc_transfer.argtypes = [ctypes.c_int]
    library.libusb_submit_transfer.argtypes = [transfer_pointer]
    library.libusb_cancel_transfer.argtypes = [transfer_pointer]
    library.libusb_free_transfer.argtypes = [transfer_pointer]
    library.libusb_free_transfer.restype = None
    library.libusb_handle_events_timeout_completed.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(LibusbTimeval),
        ctypes.c_void_p,
    ]


class AsyncBulkReader:
    """Keeps ``count`` bulk transfers of ``size`` bytes queued on one IN endpoint.

    Args:
        handle: libusb objects of the open device.
        endpoint: IN endpoint address.
        count: Number of transfers kept queued.
        size: Buffer size of each transfer in bytes.
    """

    def __init__(
        self, handle: LibusbHandle, endpoint: int, count: int, size: int
    ) -> None:
        self._handle = handle
        self._endpoint = endpoint
        self._count = count
        self._size = size
        self._packets: deque[bytes] = deque()
        self._pending = 0
        self._stopping = False
        self._disconnected = False
        self._errors = 0
        # The ctypes callback object must outlive every transfer that points at it.
        self._callback = TRANSFER_CALLBACK(self._on_transfer)
        self._buffers: list[ctypes.Array[ctypes.c_ubyte]] = []
        self._transfers: list[Any] = []

    @property
    def disconnected(self) -> bool:
        """True once a transfer reported that the device is gone."""
        return self._disconnected

    @property
    def error_count(self) -> int:
        """Transfer errors since the last successful transfer."""
        return self._errors

    @property
    def pending(self) -> int:
        """Transfers currently submitted to libusb."""
        return self._pending

    def start(self) -> None:
        """Allocate and submit the transfers.

        Raises:
            usb.core.USBError: When libusb accepts none of the transfers.
        """
        library = self._handle.library
        _bind_prototypes(library)
        self._stopping = False
        callback_address = ctypes.cast(self._callback, ctypes.c_void_p).value
        for _ in range(self._count):
            buffer = (ctypes.c_ubyte * self._size)()
            pointer = library.libusb_alloc_transfer(0)
            transfer = pointer.contents
            transfer.dev_handle = self._handle.device
            transfer.flags = 0
            transfer.endpoint = self._endpoint
            transfer.type = TRANSFER_TYPE_BULK
            transfer.timeout = 0
            transfer.length = self._size
            transfer.buffer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
            transfer.callback = callback_address
            transfer.user_data = None
            self._buffers.append(buffer)
            self._transfers.append(pointer)
            if library.libusb_submit_transfer(pointer) == 0:
                self._pending += 1
        if self._pending == 0:
            raise usb.core.USBError("could not queue USB reads")

    def _on_transfer(self, pointer: ctypes._Pointer[LibusbTransfer]) -> None:
        """libusb callback: bank the packet and put the transfer straight back."""
        transfer = pointer.contents
        status = transfer.status
        if status in (STATUS_CANCELLED, STATUS_NO_DEVICE):
            self._disconnected = self._disconnected or status == STATUS_NO_DEVICE
            self._pending -= 1
            return
        if status == STATUS_COMPLETED:
            self._packets.append(
                ctypes.string_at(transfer.buffer, transfer.actual_length)
            )
            self._errors = 0
        else:
            self._errors += 1
        if self._stopping or not self._resubmit(pointer):
            self._pending -= 1

    def _resubmit(self, pointer: ctypes._Pointer[LibusbTransfer]) -> bool:
        """Submit a completed transfer again; True when libusb accepted it."""
        try:
            return bool(self._handle.library.libusb_submit_transfer(pointer) == 0)
        except ctypes.ArgumentError:
            return False

    def pump(self, timeout_ms: int) -> None:
        """Run libusb event handling, which invokes the callback for finished transfers.

        Args:
            timeout_ms: Longest time to wait for an event, in milliseconds.
        """
        timeval = LibusbTimeval(
            timeout_ms // _MS_PER_SECOND, (timeout_ms % _MS_PER_SECOND) * _US_PER_MS
        )
        self._handle.library.libusb_handle_events_timeout_completed(
            self._handle.context, ctypes.byref(timeval), None
        )

    def pop_packet(self) -> bytes | None:
        """Return the oldest banked packet, or None when none is waiting."""
        return self._packets.popleft() if self._packets else None

    def stop(self) -> None:
        """Cancel every transfer, wait for the cancellations, and free the transfers.

        Transfers are freed only when all of them completed within
        ``STOP_TIMEOUT_SECONDS``; otherwise they are left allocated rather than freed
        while libusb may still use them.
        """
        if not self._transfers:
            return
        library = self._handle.library
        self._stopping = True
        for pointer in self._transfers:
            library.libusb_cancel_transfer(pointer)
        deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
        while self._pending > 0 and time.monotonic() < deadline:
            self.pump(STOP_PUMP_MS)
        if self._pending == 0:
            for pointer in self._transfers:
                library.libusb_free_transfer(pointer)
            self._buffers = []
        else:
            _ABANDONED.append(self)
        self._transfers = []
        self._packets.clear()
