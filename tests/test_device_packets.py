"""Tests for tower_borescope.device.packets: frame assembly, drops and gestures."""

from __future__ import annotations

from synthetic import camera_packets, jpeg_frames
from tower_borescope.device.packets import ButtonGestures, FrameAssembler

SMALL_WIDTH = 160
SMALL_HEIGHT = 120


class ManualClock:
    """A clock the test advances explicitly."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _frames(count):
    return jpeg_frames(count, SMALL_WIDTH, SMALL_HEIGHT)


def _feed_all(assembler, packets):
    return [frame for frame in map(assembler.feed, packets) if frame is not None]


def _stream(frames, fids):
    packets = []
    for jpeg, fid in zip(frames, fids, strict=True):
        packets.extend(camera_packets(jpeg, fid))
    return packets


def test_frames_complete_when_the_frame_id_changes():
    frames = _frames(4)
    assembler = FrameAssembler()
    completed = _feed_all(assembler, _stream(frames, [0, 1, 2, 3]))
    assert completed == frames[:3]
    assert assembler.dropped == 0


def test_gaps_in_frame_ids_count_as_dropped_frames():
    frames = _frames(5)
    assembler = FrameAssembler()
    completed = _feed_all(assembler, _stream(frames, [0, 1, 4, 5, 6]))
    assert completed == frames[:4]
    assert assembler.dropped == 2


def test_frame_id_wraparound_is_not_a_drop_and_wrapped_gaps_are_counted():
    frames = _frames(4)
    assembler = FrameAssembler()
    _feed_all(assembler, _stream(frames, [254, 255, 0, 1]))
    assert assembler.dropped == 0
    wrapped = FrameAssembler()
    _feed_all(wrapped, _stream(frames, [255, 1, 2, 3]))
    assert wrapped.dropped == 1


def test_large_frame_id_jumps_are_not_counted():
    frames = _frames(4)
    assembler = FrameAssembler()
    completed = _feed_all(assembler, _stream(frames, [0, 1, 200, 201]))
    assert len(completed) == 3
    assert assembler.dropped == 0


def test_incomplete_jpeg_is_discarded():
    frames = _frames(3)
    packets = camera_packets(frames[0], 0)[1:] + _stream(frames[1:], [1, 2])
    assembler = FrameAssembler()
    assert _feed_all(assembler, packets) == [frames[1]]


def test_invalid_and_truncated_packets_are_ignored():
    jpeg = _frames(1)[0]
    good = camera_packets(jpeg, 7)
    assembler = FrameAssembler()
    assert assembler.feed(b"\x00\x11" + good[0][2:]) is None
    assert assembler.feed(good[0][:2] + b"\x09" + good[0][3:]) is None
    assert assembler.feed(good[0][:-1]) is None
    assert assembler.feed(b"\xaa\xbb\x07") is None
    for packet in good:
        assembler.feed(packet)
    assert assembler.feed(camera_packets(jpeg, 8)[0]) == jpeg


def test_several_packets_in_one_transfer_are_walked():
    frames = _frames(2)
    joined = b"".join(camera_packets(frames[0], 3)) + camera_packets(frames[1], 4)[0]
    assert FrameAssembler().feed(joined) == frames[0]


def test_discard_partial_keeps_the_dropped_count():
    frames = _frames(4)
    assembler = FrameAssembler()
    _feed_all(assembler, _stream(frames[:3], [0, 2, 3]))
    assert assembler.dropped == 1
    assembler.discard_partial()
    assert _feed_all(assembler, _stream(frames, [9, 10, 11, 12])) == frames[:3]
    assert assembler.dropped == 1


def test_short_press_is_reported_after_release():
    gestures = ButtonGestures()
    for now in (0.0, 0.05, 0.1, 0.2):
        gestures.observe(True, now)
    gestures.settle(0.45)
    assert gestures.pop_events() == []
    gestures.settle(0.55)
    assert gestures.pop_events() == ["short"]
    assert gestures.pop_events() == []


def test_long_press_fires_once_while_held_and_no_short_on_release():
    gestures = ButtonGestures()
    for step in range(20):
        gestures.observe(True, step * 0.05)
    assert gestures.pop_events() == ["long"]
    gestures.settle(2.0)
    assert gestures.pop_events() == []


def test_a_gap_over_the_release_time_starts_a_new_hold():
    gestures = ButtonGestures()
    gestures.observe(True, 0.0)
    gestures.observe(True, 0.1)
    gestures.observe(True, 0.5)
    assert gestures.pop_events() == ["short"]
    gestures.observe(False, 5.0)
    gestures.settle(0.9)
    assert gestures.pop_events() == ["short"]


def test_assembler_reports_button_gestures_from_packet_flags():
    frames = _frames(3)
    clock = ManualClock()
    assembler = FrameAssembler(clock=clock)
    for packet in camera_packets(frames[0], 0, button=True):
        assembler.feed(packet)
    clock.now = 0.5
    for fid, jpeg in ((1, frames[1]), (2, frames[2])):
        for packet in camera_packets(jpeg, fid):
            assembler.feed(packet)
    assert assembler.gestures.pop_events() == ["short"]
