"""Packet parsing, frame assembly and scope button gestures.

Each bulk transfer from the video endpoint carries one packet: a 5-byte USB header
(magic ``AA BB``, a camera id of 7 or 11, and a little-endian length), a 7-byte camera
header (frame id, camera number, flags, g-sensor) and a chunk of JPEG data. A frame is
the concatenated chunks that share one frame id, and it completes when the id changes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final, NamedTuple

from tower_borescope.device.constants import (
    FID_OFFSET,
    FLAG_BUTTON,
    FLAGS_OFFSET,
    PACKET_MAGIC,
    PAYLOAD_OFFSET,
    USB_HEADER_SIZE,
    VALID_CIDS,
)

RELEASE_GAP_SECONDS: Final = 0.3
LONG_PRESS_SECONDS: Final = 0.7
SHORT_GESTURE: Final = "short"
LONG_GESTURE: Final = "long"
JPEG_SOI: Final = b"\xff\xd8"
JPEG_EOI: Final = b"\xff\xd9"
FID_MODULUS: Final = 256
MAX_COUNTED_GAP: Final = 128


class ButtonGestures:
    """Turns the repeating button flag into short and long press gestures.

    The flag repeats in every packet while the button is held. A gap longer than
    ``RELEASE_GAP_SECONDS`` ends a hold. A hold of ``LONG_PRESS_SECONDS`` or more emits
    ``"long"`` once while still held; a shorter hold emits ``"short"`` when it ends.
    """

    def __init__(self) -> None:
        self._down_since: float | None = None
        self._last_seen = 0.0
        self._long_fired = False
        self._events: list[str] = []

    def observe(self, pressed: bool, now: float) -> None:
        """Record the button flag from one packet.

        Args:
            pressed: True when the packet carries the button flag.
            now: Monotonic time of the packet in seconds.
        """
        if not pressed:
            return
        if self._down_since is None or now - self._last_seen > RELEASE_GAP_SECONDS:
            self.settle(now)
            self._down_since = now
            self._long_fired = False
        self._last_seen = now
        if not self._long_fired and now - self._down_since >= LONG_PRESS_SECONDS:
            self._long_fired = True
            self._events.append(LONG_GESTURE)

    def settle(self, now: float) -> None:
        """End the current hold when the flag has been absent long enough.

        Args:
            now: Current monotonic time in seconds.
        """
        if self._down_since is None or now - self._last_seen <= RELEASE_GAP_SECONDS:
            return
        if not self._long_fired:
            self._events.append(SHORT_GESTURE)
        self._down_since = None

    def pop_events(self) -> list[str]:
        """Return and clear the gestures recorded so far, oldest first."""
        events, self._events = self._events, []
        return events


class _Packet(NamedTuple):
    """Header fields and bounds of one parsed packet."""

    end: int
    fid: int
    flags: int


def _parse_packet(data: bytes, pos: int) -> _Packet | None:
    """Parse the packet starting at ``pos``, or None when it is invalid or truncated."""
    if pos + PAYLOAD_OFFSET > len(data):
        return None
    if (data[pos], data[pos + 1]) != PACKET_MAGIC or data[pos + 2] not in VALID_CIDS:
        return None
    length = data[pos + 3] | (data[pos + 4] << 8)
    end = pos + USB_HEADER_SIZE + length
    if end > len(data):
        return None
    return _Packet(end, data[pos + FID_OFFSET], data[pos + FLAGS_OFFSET])


class FrameAssembler:
    """Collects packet payloads into complete JPEG frames and counts dropped frames.

    Attributes:
        dropped: Frames the camera skipped, derived from gaps in frame ids.
        gestures: Button gesture tracker fed from the packet flags.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.dropped = 0
        self.gestures = ButtonGestures()
        self._clock = clock
        self._buffer = bytearray()
        self._fid: int | None = None
        self._last_fid: int | None = None

    def discard_partial(self) -> None:
        """Forget the frame in progress and the last frame id after a stream restart.

        The dropped count and the gesture state are kept.
        """
        self._buffer.clear()
        self._fid = None
        self._last_fid = None

    def feed(self, data: bytes) -> bytes | None:
        """Process the bytes of one bulk transfer.

        Args:
            data: Bytes received in one transfer; normally a single packet.

        Returns:
            The last JPEG frame completed by these packets, or None.
        """
        frame: bytes | None = None
        pos = 0
        packet = _parse_packet(data, pos)
        while packet is not None:
            self.gestures.observe(bool(packet.flags & FLAG_BUTTON), self._clock())
            completed = self._complete_frame(packet.fid)
            frame = completed if completed is not None else frame
            self._fid = packet.fid
            self._buffer.extend(data[pos + PAYLOAD_OFFSET : packet.end])
            pos = packet.end
            packet = _parse_packet(data, pos)
        if frame is not None:
            self.gestures.settle(self._clock())
        return frame

    def _complete_frame(self, fid: int) -> bytes | None:
        """Close the frame in progress when ``fid`` starts a new one.

        Returns:
            The finished frame when it is a whole JPEG, otherwise None.
        """
        if self._fid is None or fid == self._fid or not self._buffer:
            return None
        done = bytes(self._buffer)
        self._buffer.clear()
        if not (done.startswith(JPEG_SOI) and done.endswith(JPEG_EOI)):
            return None
        if self._last_fid is not None:
            gap = (self._fid - self._last_fid) % FID_MODULUS - 1
            if 0 < gap < MAX_COUNTED_GAP:
                self.dropped += gap
        self._last_fid = self._fid
        return done
