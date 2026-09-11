"""Opening, streaming from and closing the supercamera.

``Camera`` runs the verified start sequence: claim both interfaces, drain the iAP
heartbeat, select the resolution, switch the video interface to its streaming
alternate setting, send the initialisation and start commands, then discard the first
partial frames. A USB error during start resets the device, waits for it to enumerate
again and retries.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any, Final

import usb.core
import usb.util

from tower_borescope.device.constants import (
    ASYNC_TRANSFERS,
    COMMIT_VALUE,
    CONFIGURATION,
    DEFAULT_MODE,
    DEVICE_IDS,
    EP_IAP_IN,
    EP_IAP_OUT,
    EP_IN,
    EP_OUT,
    FRAME_INTERVAL_100NS,
    IAP_DRAIN_READS,
    IAP_DRAIN_SIZE,
    IAP_DRAIN_TIMEOUT_MS,
    IAP_INTERFACE,
    MAGIC_INIT,
    MODES,
    PROBE_FORMAT_INDEX,
    PROBE_INDEX,
    PROBE_LENGTH,
    PROBE_REQUEST,
    PROBE_REQUEST_TYPE,
    PROBE_VALUE,
    READ_SIZE,
    START_STREAM,
    VIDEO_ALT_IDLE,
    VIDEO_ALT_STREAMING,
    VIDEO_INTERFACE,
    WRITE_TIMEOUT_MS,
    Mode,
)
from tower_borescope.device.libusb import load_backend
from tower_borescope.device.packets import FrameAssembler
from tower_borescope.device.transfers import AsyncBulkReader, LibusbHandle
from tower_borescope.errors import BorescopeError, CameraDisconnectedError
from tower_borescope.jpeg import jpeg_size

OPEN_ATTEMPTS: Final = 3
FIND_WAIT_SECONDS: Final = 3.0
FIND_POLL_SECONDS: Final = 0.5
RETRY_DELAY_SECONDS: Final = 1.5
STARTUP_FRAMES: Final = 3
PUMP_MS: Final = 100
MAX_TRANSFER_ERRORS: Final = 50
LIBUSB_ERROR_NO_DEVICE: Final = -4
NOT_FOUND_MESSAGE: Final = "Borescope not found on USB."

_LOGGER = logging.getLogger(__name__)


def _find_device(backend: Any, wait: float = 0.0) -> Any | None:
    """Return the first attached supercamera, polling for up to ``wait`` seconds."""
    deadline = time.monotonic() + wait
    while True:
        for vendor, product in DEVICE_IDS:
            device = usb.core.find(idVendor=vendor, idProduct=product, backend=backend)
            if device is not None:
                return device
        if time.monotonic() >= deadline:
            return None
        time.sleep(FIND_POLL_SECONDS)


def device_present() -> bool:
    """Report whether a supercamera is attached.

    Returns:
        True when either known vendor and product id is on the bus.

    Raises:
        BorescopeError: When libusb cannot be loaded.
    """
    return _find_device(load_backend()) is not None


def _claim_interfaces(device: Any) -> None:
    """Select configuration 1 when needed and claim the iAP and video interfaces."""
    try:
        if device.get_active_configuration().bConfigurationValue != CONFIGURATION:
            device.set_configuration(CONFIGURATION)
    except usb.core.USBError:
        device.set_configuration(CONFIGURATION)
    for interface in (IAP_INTERFACE, VIDEO_INTERFACE):
        try:
            usb.util.claim_interface(device, interface)
        except usb.core.USBError as exc:
            raise BorescopeError(
                f"Borescope is busy ({exc}). Close other applications using it and retry."
            ) from exc


def _drain_heartbeat(device: Any) -> None:
    """Discard pending iAP heartbeat packets."""
    for _ in range(IAP_DRAIN_READS):
        try:
            device.read(EP_IAP_IN, IAP_DRAIN_SIZE, timeout=IAP_DRAIN_TIMEOUT_MS)
        except usb.core.USBError:
            return


def probe_payload(mode: Mode) -> bytes:
    """Build the 26-byte probe and commit payload selecting ``mode``.

    Args:
        mode: Resolution to select.

    Returns:
        Format index at byte 2, frame index at byte 3 and the frame interval in
        100 ns units, little-endian, at bytes 4 to 7.
    """
    payload = bytearray(PROBE_LENGTH)
    payload[2] = PROBE_FORMAT_INDEX
    payload[3] = mode.index
    payload[4:8] = FRAME_INTERVAL_100NS.to_bytes(4, "little")
    return bytes(payload)


def _select_mode(device: Any, mode: Mode) -> None:
    """Send the resolution probe and commit; a failure keeps the current mode."""
    payload = probe_payload(mode)
    try:
        for value in (PROBE_VALUE, COMMIT_VALUE):
            device.ctrl_transfer(
                PROBE_REQUEST_TYPE,
                PROBE_REQUEST,
                value,
                PROBE_INDEX,
                payload,
                timeout=WRITE_TIMEOUT_MS,
            )
    except usb.core.USBError as exc:
        _LOGGER.warning(
            "Could not set %s (%s); keeping the current mode.", mode.name, exc
        )


def _send_start(device: Any) -> None:
    """Switch the video interface to streaming and send the start commands."""
    device.set_interface_altsetting(
        interface=VIDEO_INTERFACE, alternate_setting=VIDEO_ALT_STREAMING
    )
    device.clear_halt(EP_OUT)
    # A previous session leaves the iAP OUT endpoint halted, so the write times out
    # unless the halt is cleared first. Video starts even when this write fails.
    with contextlib.suppress(usb.core.USBError):
        device.clear_halt(EP_IAP_OUT)
        device.write(EP_IAP_OUT, MAGIC_INIT, timeout=WRITE_TIMEOUT_MS)
    device.write(EP_OUT, START_STREAM, timeout=WRITE_TIMEOUT_MS)


def _release_device(device: Any) -> None:
    """Return the video interface to idle, release both interfaces, free resources."""
    with contextlib.suppress(usb.core.USBError):
        device.set_interface_altsetting(
            interface=VIDEO_INTERFACE, alternate_setting=VIDEO_ALT_IDLE
        )
    for interface in (VIDEO_INTERFACE, IAP_INTERFACE):
        with contextlib.suppress(usb.core.USBError):
            usb.util.release_interface(device, interface)
    with contextlib.suppress(usb.core.USBError):
        usb.util.dispose_resources(device)


class _FrameStream:
    """Queued asynchronous reads from one open device, assembled into frames."""

    def __init__(self, device: Any, assembler: FrameAssembler, timeout: float) -> None:
        self._device = device
        self._assembler = assembler
        self._timeout = timeout
        self._reader: AsyncBulkReader | None = None

    def start(self) -> None:
        """Queue the bulk transfers on the video endpoint."""
        handle = LibusbHandle.from_device(self._device)
        self._reader = AsyncBulkReader(handle, EP_IN, ASYNC_TRANSFERS, READ_SIZE)
        self._reader.start()

    def next_frame(self) -> bytes | None:
        """Return the next complete JPEG, or None when the timeout passes.

        Raises:
            usb.core.USBError: When the device is gone or reads keep failing.
        """
        reader = self._reader
        if reader is None:
            raise usb.core.USBError("stream not started")
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            packet = reader.pop_packet()
            if packet is None:
                _wait_for_packets(reader)
                continue
            frame = self._assembler.feed(packet)
            if frame is not None:
                return frame
        return None

    def stop(self) -> None:
        """Cancel and free the queued transfers."""
        if self._reader is not None:
            self._reader.stop()
            self._reader = None


def _wait_for_packets(reader: AsyncBulkReader) -> None:
    """Pump libusb once and raise when the device is gone or reads keep failing."""
    reader.pump(PUMP_MS)
    if reader.disconnected:
        raise usb.core.USBError("borescope disconnected", LIBUSB_ERROR_NO_DEVICE)
    if reader.error_count > MAX_TRANSFER_ERRORS:
        raise usb.core.USBError("repeated USB read errors")


class Camera:
    """One streaming session with the supercamera.

    Attributes:
        mode: Resolution mode name requested at open.
        timeout: Seconds ``read_jpeg`` waits for a frame.
        size: Frame size; replaced by the size in the first frame's JPEG header.

    Args:
        mode: Key into ``MODES``.
        timeout: Seconds ``read_jpeg`` waits for a frame before returning None.
    """

    def __init__(self, mode: str = DEFAULT_MODE, timeout: float = 5.0) -> None:
        selected = MODES[mode]
        self.mode = mode
        self.timeout = timeout
        self.size = (selected.width, selected.height)
        self._assembler = FrameAssembler()
        self._device: Any | None = None
        self._stream: _FrameStream | None = None

    @property
    def dropped(self) -> int:
        """Frames the camera skipped since this object was created."""
        return self._assembler.dropped

    def open(self) -> None:
        """Find the camera and start the stream, retrying after USB errors.

        Raises:
            BorescopeError: When the camera is missing, busy, or does not start after
                ``OPEN_ATTEMPTS`` attempts.
        """
        if self._device is not None:
            return
        backend = load_backend()
        failure: usb.core.USBError | None = None
        for attempt in range(OPEN_ATTEMPTS):
            device = _find_device(backend, FIND_WAIT_SECONDS if attempt else 0.0)
            if device is None:
                raise BorescopeError(NOT_FOUND_MESSAGE)
            try:
                self._start(device)
                return
            except BorescopeError:
                self._abandon(device, reset=False)
                raise
            except usb.core.USBError as exc:
                failure = exc
                _LOGGER.warning("USB start failed (%s); resetting and retrying.", exc)
                self._abandon(device, reset=True)
                time.sleep(RETRY_DELAY_SECONDS)
        raise BorescopeError(
            f"Could not start the borescope ({failure}). "
            "Unplug it, plug it back in and retry."
        )

    def _start(self, device: Any) -> None:
        """Run the start sequence on ``device`` and read the first frames."""
        self._device = device
        self._assembler.discard_partial()
        _claim_interfaces(device)
        _drain_heartbeat(device)
        _select_mode(device, MODES[self.mode])
        _send_start(device)
        self._stream = _FrameStream(device, self._assembler, self.timeout)
        self._stream.start()
        frames = [self._stream.next_frame() for _ in range(STARTUP_FRAMES)]
        last = frames[-1]
        if last is None:
            raise usb.core.USBError("no video after start command")
        actual = jpeg_size(last)
        if actual is not None:
            self.size = actual

    def _abandon(self, device: Any, *, reset: bool) -> None:
        """Stop reads and free ``device`` after a failed start; reset it on request."""
        self._stop_stream()
        if reset:
            with contextlib.suppress(usb.core.USBError):
                device.reset()
        with contextlib.suppress(usb.core.USBError):
            usb.util.dispose_resources(device)
        self._device = None

    def _stop_stream(self) -> None:
        """Stop the asynchronous reads when they are running."""
        if self._stream is not None:
            self._stream.stop()
            self._stream = None

    def read_jpeg(self) -> bytes | None:
        """Return the next complete JPEG frame.

        Returns:
            The frame bytes, or None when no frame arrives within ``timeout``.

        Raises:
            BorescopeError: When the camera is not open.
            CameraDisconnectedError: When the device goes away or reads keep failing.
        """
        if self._stream is None:
            raise BorescopeError("Borescope is not open.")
        try:
            return self._stream.next_frame()
        except usb.core.USBError as exc:
            raise CameraDisconnectedError(f"Borescope disconnected ({exc}).") from exc

    def pop_button_events(self) -> list[str]:
        """Return and clear button gestures, ``"short"`` or ``"long"``, oldest first."""
        self._assembler.gestures.settle(time.monotonic())
        return self._assembler.gestures.pop_events()

    def close(self) -> None:
        """Stop the stream and release the device without resetting it."""
        device = self._device
        if device is None:
            return
        self._stop_stream()
        _release_device(device)
        self._device = None

    def __enter__(self) -> Camera:
        self.open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
