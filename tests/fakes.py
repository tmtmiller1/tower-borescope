"""Test doubles for the camera reader and the AI backend.

``FakeReader`` satisfies ``tower_borescope.device.reader.FrameSource`` in process, so the
pipeline and the application window run end to end without the borescope attached.
``FakeBackend`` answers AI requests instantly with ``SAMPLE_ANALYSIS`` and
``SAMPLE_SCALE``, without a model or network.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from synthetic import jpeg_frames
from tower_borescope.ai.base import Backend, ChatMessage, TextCallback
from tower_borescope.ai.schema import Analysis, Issue, ScaleEstimate
from tower_borescope.device.constants import FPS, MODES

FRAMES_PER_MODE = 24


class FakeReader:
    """Replays synthetic JPEG frames at the camera frame rate.

    Attributes:
        mode: Current resolution mode name.
        size: Frame size for the current mode.
        status: Empty while streaming; mirrors the real reader's status line.
        fps: Frames per second delivered.
        dropped: Frames the source skipped; always zero here.
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.size = (MODES[mode].width, MODES[mode].height)
        self.status = "Connecting to scope..."
        self.fps = 0.0
        self.dropped = 0
        self.started = False
        self.stopped = False
        self._frames: list[bytes] = []
        self._index = 0
        self._last = 0.0
        self._button_events: list[str] = []

    def _load(self) -> None:
        """Generate the frames for the current mode."""
        width, height = self.size
        self._frames = jpeg_frames(FRAMES_PER_MODE, width, height)
        self._index = 0

    def start(self) -> None:
        """Begin streaming."""
        self._load()
        self.started = True
        self.status = ""

    def stop(self) -> None:
        """Stop streaming."""
        self.stopped = True

    def request_mode(self, mode: str) -> None:
        """Switch resolution immediately."""
        self.mode = mode
        self.size = (MODES[mode].width, MODES[mode].height)
        self._load()

    def next_frame(self, timeout: float) -> bytes | None:
        """Return the next frame, paced at the camera rate, or None within ``timeout``."""
        if not self.started or self.stopped:
            time.sleep(timeout)
            return None
        wait = self._last + 1.0 / FPS - time.monotonic()
        if wait > timeout:
            time.sleep(timeout)
            return None
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        frame = self._frames[self._index % len(self._frames)]
        self._index += 1
        self.fps = float(FPS)
        return frame

    def press_button(self, gesture: str) -> None:
        """Queue a scope button gesture, ``"short"`` or ``"long"``."""
        self._button_events.append(gesture)

    def pop_button_events(self) -> list[str]:
        """Return and clear queued button gestures."""
        events, self._button_events = self._button_events, []
        return events


JPEG_MAGIC = b"\xff\xd8"
ANALYZE_MARKER = "Analyze this scope view"
FAKE_ANSWER = "Probably old residue; wipe it and re-check in a day."

SAMPLE_ANALYSIS = Analysis(
    subject="Copper supply line with compression fitting",
    description=(
        "A 1/2 in copper pipe entering a brass compression fitting; "
        "green-white deposits at the nut."
    ),
    condition="fair",
    issues=[
        Issue(
            label="Mineral deposits at fitting",
            severity="medium",
            note="White/green crust suggests a slow weep.",
            box=[0.42, 0.30, 0.68, 0.55],
        ),
        Issue(label="Surface tarnish", severity="info", note="Cosmetic.", box=None),
    ],
    actions=[
        "Dry the joint and check again in 24 h",
        "Snug the compression nut a quarter turn if it weeps",
    ],
    parts_and_tools=["Adjustable wrench", "Compression nut and ferrule 1/2 in"],
    safety=["Shut the supply valve before loosening anything"],
    confidence="medium",
    questions=["Is this a slow leak or old residue?", "What size wrench do I need?"],
)

SAMPLE_SCALE = ScaleEstimate(
    found=True,
    reference_object="1/2 in copper pipe (5/8 in OD)",
    standard_size_mm=15.875,
    span=[0.30, 0.50, 0.70, 0.50],
    confidence="medium",
    reasoning="Pipe OD spans the frame's middle.",
)


class FakeBackend(Backend):
    """Deterministic stand-in for a vision model: no network, instant answers.

    Attributes:
        name: Display name the application shows in its status line.
    """

    name = "Fake (test)"

    def analyze(self, jpeg: bytes, prompt: str) -> Analysis:
        """Return a copy of ``SAMPLE_ANALYSIS`` after checking the request shape."""
        assert jpeg.startswith(JPEG_MAGIC) and ANALYZE_MARKER in prompt
        self.usage.add(1500, 600)
        return SAMPLE_ANALYSIS.model_copy(deep=True)

    def chat(self, messages: Sequence[ChatMessage], on_text: TextCallback) -> str:
        """Stream ``FAKE_ANSWER`` one word at a time."""
        assert messages[-1]["role"] == "user"
        for word in FAKE_ANSWER.split(" "):
            on_text(word + " ")
        self.usage.add(800, 40)
        return FAKE_ANSWER + " "

    def scale(self, jpeg: bytes, prompt: str) -> ScaleEstimate:
        """Return a copy of ``SAMPLE_SCALE``."""
        return SAMPLE_SCALE.model_copy(deep=True)

    def check(self) -> str:
        """Report a healthy backend."""
        return "fake ok"
