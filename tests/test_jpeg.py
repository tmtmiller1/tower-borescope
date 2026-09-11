"""Tests for tower_borescope.jpeg: header parsing, decoding and encoding."""

from __future__ import annotations

import numpy as np

from synthetic import textured_frame
from tower_borescope.jpeg import decode_bgr, encode_jpeg, jpeg_size


def test_round_trip_keeps_size_and_content():
    frame = textured_frame(320, 240)
    data = encode_jpeg(frame, 90)
    assert data.startswith(b"\xff\xd8")
    assert data.endswith(b"\xff\xd9")
    assert jpeg_size(data) == (320, 240)
    decoded = decode_bgr(data)
    assert decoded is not None
    assert decoded.shape == (240, 320, 3)
    assert np.abs(decoded.astype(np.int16) - frame.astype(np.int16)).mean() < 12


def test_jpeg_size_of_truncated_or_empty_data_is_none():
    assert jpeg_size(b"") is None
    assert jpeg_size(b"\xff\xd8\x00\x01") is None


def test_jpeg_size_stops_at_scan_data_without_frame_header():
    data = b"\xff\xd8" + b"\xff\xda\x00\x08" + bytes(16)
    assert jpeg_size(data) is None


def test_decode_of_non_jpeg_bytes_is_none():
    assert decode_bgr(b"not a jpeg at all") is None
