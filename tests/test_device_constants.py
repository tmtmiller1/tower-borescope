"""Tests for tower_borescope.device.constants: protocol values and the mode table."""

from __future__ import annotations

import dataclasses

import pytest

from tower_borescope.device.constants import (
    DEFAULT_MODE,
    DEVICE_IDS,
    EP_IAP_IN,
    EP_IAP_OUT,
    EP_IN,
    EP_OUT,
    FPS,
    FRAME_INTERVAL_100NS,
    MAGIC_INIT,
    MODES,
    READ_SIZE,
    START_STREAM,
    Mode,
)


def test_device_ids_and_endpoints_match_the_protocol():
    assert DEVICE_IDS == ((0x2CE3, 0x3828), (0x0329, 0x2022))
    assert (EP_OUT, EP_IN) == (0x01, 0x81)
    assert (EP_IAP_OUT, EP_IAP_IN) == (0x02, 0x82)


def test_commands_and_stream_parameters():
    assert MAGIC_INIT == bytes.fromhex("ff55ff55ee10")
    assert START_STREAM == bytes.fromhex("bbaa050000")
    assert READ_SIZE == 1024
    assert FPS == 20
    assert FRAME_INTERVAL_100NS == 333333


def test_mode_table_indexes_and_sizes():
    table = {name: (mode.index, mode.width, mode.height) for name, mode in MODES.items()}
    assert table == {
        "720p": (3, 1280, 720),
        "480p": (1, 640, 480),
        "480w": (4, 720, 480),
        "240p": (2, 320, 240),
        "120p": (5, 160, 120),
    }
    assert all(mode.name == name for name, mode in MODES.items())
    assert all(f"{mode.width} x {mode.height}" in mode.label for mode in MODES.values())


def test_default_mode_is_720p_and_modes_are_frozen():
    assert DEFAULT_MODE == "720p"
    assert DEFAULT_MODE in MODES
    with pytest.raises(dataclasses.FrozenInstanceError):
        MODES["720p"].width = 1  # type: ignore[misc]  # asserting the dataclass is frozen
    assert Mode("720p", 3, 1280, 720, "x") == Mode("720p", 3, 1280, 720, "x")
