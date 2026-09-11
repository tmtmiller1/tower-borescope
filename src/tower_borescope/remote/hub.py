"""Latest encoded frame shared between the frame publisher and the stream handlers.

The pipeline publishes processed frames at the camera rate. The hub keeps only the newest
JPEG, limits publishing to the stream rate while phones watch and to one frame a second
otherwise, and wakes every waiting stream when a frame arrives or the server stops.
"""

from __future__ import annotations

import threading

STREAM_FPS = 12
IDLE_PUBLISH_SECONDS = 1.0
VIEWER_WAIT_SECONDS = 2.0


class FrameHub:
    """Latest encoded frame, shared by the publisher and the streaming handlers.

    Attributes:
        latest: Newest JPEG, or None before the first frame.
        latest_at: Time passed to :meth:`put` with the newest frame.
        viewers: Open stream connections.
        closed: True once the server stops; stream loops end.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self.latest: bytes | None = None
        self.latest_at = 0.0
        self.viewers = 0
        self.closed = False

    def should_publish(self, now: float) -> bool:
        """Rate limit: the stream rate with viewers, one frame a second without."""
        elapsed = now - self.latest_at
        if elapsed < 1.0 / STREAM_FPS:
            return False
        return self.viewers > 0 or elapsed >= IDLE_PUBLISH_SECONDS

    def put(self, data: bytes, now: float) -> None:
        """Store a frame and wake every waiting stream."""
        with self._condition:
            self.latest = data
            self.latest_at = now
            self._condition.notify_all()

    def wait_newer(self, last: float) -> tuple[bytes | None, float]:
        """Latest frame once one newer than ``last`` arrives or the wait times out."""
        with self._condition:
            self._condition.wait_for(
                lambda: self.closed or self.latest_at > last, timeout=VIEWER_WAIT_SECONDS
            )
            return self.latest, self.latest_at

    def add_viewers(self, delta: int) -> None:
        """Adjust the open stream count."""
        with self._condition:
            self.viewers += delta

    def close(self) -> None:
        """End every stream loop."""
        with self._condition:
            self.closed = True
            self._condition.notify_all()
