"""Backend interface shared by every AI provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, TypedDict

from tower_borescope.ai.schema import Analysis, ScaleEstimate
from tower_borescope.errors import BorescopeError

LOCAL_IMAGE_WIDTH = 768
HOSTED_IMAGE_WIDTH = 1280

type TextCallback = Callable[[str], None]


class AiError(BorescopeError):
    """A backend problem reported to the user as a plain message."""


class ChatMessage(TypedDict):
    """One conversation turn.

    Attributes:
        role: ``"user"`` or ``"assistant"``.
        text: Message text.
        jpeg: Image attached to the turn, or None.
    """

    role: Literal["user", "assistant"]
    text: str
    jpeg: bytes | None


@dataclass(slots=True)
class Usage:
    """Token counts accumulated by a backend.

    Attributes:
        input_tokens: Prompt tokens sent.
        output_tokens: Completion tokens received.
    """

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int | None, output_tokens: int | None) -> None:
        """Add one call's counts; a missing count adds nothing."""
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)


class Backend(ABC):
    """A vision model that analyzes frames, estimates scale and answers questions.

    Attributes:
        name: Display name including the model.
        cost_per_token: Dollars per input token and per output token.
        max_image_width: Widest image worth sending, in pixels.
        usage: Tokens used so far.
    """

    name: str = "AI"
    cost_per_token: tuple[float, float] = (0.0, 0.0)
    max_image_width: int = HOSTED_IMAGE_WIDTH

    def __init__(self) -> None:
        self.usage = Usage()

    def describe(self) -> str:
        """Name shown in reports and the status line."""
        return self.name

    @abstractmethod
    def analyze(self, jpeg: bytes, prompt: str) -> Analysis:
        """Return a structured analysis of one JPEG frame.

        Raises:
            AiError: When the backend cannot be reached or answers unusably.
        """

    @abstractmethod
    def chat(self, messages: Sequence[ChatMessage], on_text: TextCallback) -> str:
        """Stream an answer to the last user turn.

        Args:
            messages: Conversation so far, ending with a user turn.
            on_text: Called with each chunk of text as it arrives.

        Returns:
            The complete answer.

        Raises:
            AiError: When the backend cannot be reached.
        """

    @abstractmethod
    def scale(self, jpeg: bytes, prompt: str) -> ScaleEstimate:
        """Return a scale estimate for one JPEG frame.

        Raises:
            AiError: When the backend cannot be reached or answers unusably.
        """

    def summarize(self, prompt: str) -> str:
        """Answer a text-only prompt without streaming to a caller."""
        message: ChatMessage = {"role": "user", "text": prompt, "jpeg": None}
        return self.chat([message], _discard)

    @abstractmethod
    def check(self) -> str:
        """Verify connectivity and the model, returning a one-line status.

        Raises:
            AiError: When the backend or model is unavailable.
        """


def _discard(_text: str) -> None:
    """Ignore streamed text."""
