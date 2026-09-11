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


SOI = b"\xff\xd8"
# SOF0 marker, segment length 17, 8-bit samples, height 240, width 320.
FRAME_HEADER = b"\xff\xc0\x00\x11\x08\x00\xf0\x01\x40"


def test_jpeg_size_reads_a_frame_header_ending_at_the_last_byte():
    assert jpeg_size(SOI + FRAME_HEADER) == (320, 240)
    assert jpeg_size(SOI + FRAME_HEADER[:-1]) is None


def test_jpeg_size_skips_a_segment_longer_than_255_bytes():
    # A comment segment of 300 bytes puts a nonzero value in the high length byte.
    comment = b"\xff\xfe" + (300).to_bytes(2, "big") + bytes(298)
    assert jpeg_size(SOI + comment + FRAME_HEADER + bytes(8)) == (320, 240)


def test_decode_of_non_jpeg_bytes_is_none():
    assert decode_bgr(b"not a jpeg at all") is None
