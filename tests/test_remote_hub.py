"""Tests for tower_borescope.remote.hub: publishing rate, waiting streams and closing."""

from __future__ import annotations

import threading
import time

from tower_borescope.remote.hub import (
    IDLE_PUBLISH_SECONDS,
    STREAM_FPS,
    VIEWER_WAIT_SECONDS,
    FrameHub,
)


def test_publishing_follows_the_viewer_count():
    hub = FrameHub()
    hub.put(b"first", 100.0)
    assert not hub.should_publish(100.0 + 0.5 / STREAM_FPS)
    assert not hub.should_publish(100.0 + 2.0 / STREAM_FPS)
    assert hub.should_publish(100.0 + IDLE_PUBLISH_SECONDS)
    hub.add_viewers(1)
    assert hub.should_publish(100.0 + 2.0 / STREAM_FPS)
    hub.add_viewers(-1)
    assert hub.viewers == 0


def test_a_new_frame_wakes_a_waiting_stream():
    hub = FrameHub()
    result = {}
    waiter = threading.Thread(target=lambda: result.update(frame=hub.wait_newer(0.0)))
    waiter.start()
    time.sleep(0.05)
    hub.put(b"jpeg", 5.0)
    waiter.join(VIEWER_WAIT_SECONDS / 2)
    assert not waiter.is_alive()
    assert result["frame"] == (b"jpeg", 5.0)


def test_close_wakes_waiting_streams_before_the_wait_ends():
    hub = FrameHub()
    hub.put(b"old", 1.0)
    waiter = threading.Thread(target=hub.wait_newer, args=(1.0,))
    waiter.start()
    time.sleep(0.05)
    hub.close()
    waiter.join(VIEWER_WAIT_SECONDS / 2)
    assert not waiter.is_alive()
    assert hub.closed
