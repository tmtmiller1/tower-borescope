"""One analyzed frame and the follow-up questions about it, on any backend."""

from __future__ import annotations

from tower_borescope.ai.base import Backend, ChatMessage, TextCallback
from tower_borescope.ai.prompts import SCALE_PROMPT, analyze_prompt
from tower_borescope.ai.schema import (
    Analysis,
    ScaleEstimate,
    normalize_analysis,
    normalize_scale,
)


class Conversation:
    """An analysis followed by streamed follow-up answers.

    The image travels in the first user turn only, so each follow-up adds text alone.

    Attributes:
        backend: Model that answers.
        jpeg: Frame under discussion.
        context: Homeowner notes sent with the analysis request.
        mm_per_px: Calibrated scale, or None.
        analysis: Normalized analysis once :meth:`analyze` has run.
        messages: Conversation turns so far.
    """

    def __init__(
        self,
        backend: Backend,
        jpeg: bytes,
        context: str = "",
        mm_per_px: float | None = None,
    ) -> None:
        self.backend = backend
        self.jpeg = jpeg
        self.context = context
        self.mm_per_px = mm_per_px
        self.analysis: Analysis | None = None
        self.messages: list[ChatMessage] = []

    def analyze(self) -> Analysis:
        """Analyze the frame and start the conversation from that answer.

        Returns:
            The normalized analysis.

        Raises:
            AiError: When the backend fails.
        """
        prompt = analyze_prompt(self.context, self.mm_per_px)
        self.analysis = normalize_analysis(self.backend.analyze(self.jpeg, prompt))
        self.messages = [
            {"role": "user", "text": prompt, "jpeg": self.jpeg},
            {"role": "assistant", "text": self.analysis.model_dump_json(), "jpeg": None},
        ]
        return self.analysis

    def ask(self, question: str, on_text: TextCallback) -> str:
        """Stream the answer to a follow-up question.

        Args:
            question: The homeowner's question.
            on_text: Called with each chunk of the answer as it arrives.

        Returns:
            The complete answer, which is also appended to :attr:`messages`.

        Raises:
            AiError: When the backend fails.
        """
        self.messages.append({"role": "user", "text": question, "jpeg": None})
        answer = self.backend.chat(self.messages, on_text)
        self.messages.append({"role": "assistant", "text": answer, "jpeg": None})
        return answer


def estimate_scale(backend: Backend, jpeg: bytes) -> ScaleEstimate:
    """Ask a backend for a scale reference in a frame.

    Args:
        backend: Model that answers.
        jpeg: Frame to measure.

    Returns:
        The normalized estimate; ``found`` is False without a usable span and size.
    """
    return normalize_scale(backend.scale(jpeg, SCALE_PROMPT))
