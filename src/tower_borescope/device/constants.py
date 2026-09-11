"""Protocol constants and the resolution mode table for the supercamera.

Values come from the verified protocol notes: USB identifiers, endpoints, the
initialisation and start commands, packet layout offsets, and the frame indexes the
resolution probe accepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DEVICE_IDS: Final[tuple[tuple[int, int], ...]] = ((0x2CE3, 0x3828), (0x0329, 0x2022))

CONFIGURATION: Final = 1
IAP_INTERFACE: Final = 0
VIDEO_INTERFACE: Final = 1
VIDEO_ALT_IDLE: Final = 0
VIDEO_ALT_STREAMING: Final = 1

EP_OUT: Final = 0x01
EP_IN: Final = 0x81
EP_IAP_OUT: Final = 0x02
EP_IAP_IN: Final = 0x82

MAGIC_INIT: Final = bytes([0xFF, 0x55, 0xFF, 0x55, 0xEE, 0x10])
START_STREAM: Final = bytes([0xBB, 0xAA, 0x05, 0x00, 0x00])

READ_SIZE: Final = 0x400
ASYNC_TRANSFERS: Final = 128
IAP_DRAIN_READS: Final = 30
IAP_DRAIN_SIZE: Final = 512
IAP_DRAIN_TIMEOUT_MS: Final = 100
WRITE_TIMEOUT_MS: Final = 1000

USB_HEADER_SIZE: Final = 5
PAYLOAD_OFFSET: Final = 12
FID_OFFSET: Final = 5
FLAGS_OFFSET: Final = 7
VALID_CIDS: Final = (7, 11)
PACKET_MAGIC: Final = (0xAA, 0xBB)
FLAG_BUTTON: Final = 0x02

FPS: Final = 20
FRAME_INTERVAL_100NS: Final = 333333

PROBE_REQUEST_TYPE: Final = 0x21
PROBE_REQUEST: Final = 0x01
PROBE_VALUE: Final = 0x0100
COMMIT_VALUE: Final = 0x0200
PROBE_INDEX: Final = 1
PROBE_LENGTH: Final = 26
PROBE_FORMAT_INDEX: Final = 0x02


@dataclass(frozen=True, slots=True)
class Mode:
    """One resolution the camera streams.

    Attributes:
        name: Short identifier used in settings and on the command line.
        index: Frame index sent in the resolution probe.
        width: Frame width in pixels.
        height: Frame height in pixels.
        label: Human-readable description for menus.
    """

    name: str
    index: int
    width: int
    height: int
    label: str


MODES: Final[dict[str, Mode]] = {
    mode.name: mode
    for mode in (
        Mode("720p", 3, 1280, 720, "1280 x 720  (best detail)"),
        Mode("480p", 1, 640, 480, "640 x 480  (wider view)"),
        Mode("480w", 4, 720, 480, "720 x 480"),
        Mode("240p", 2, 320, 240, "320 x 240"),
        Mode("120p", 5, 160, 120, "160 x 120"),
    )
}

DEFAULT_MODE: Final = "720p"
