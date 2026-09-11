"""Rich text for the AI answer panel: analysis, suggested questions and the follow-ups."""

from __future__ import annotations

from typing import Final

from tower_borescope.ai.base import Backend
from tower_borescope.ai.factory import estimated_cost
from tower_borescope.ai.panel_html import analysis_html
from tower_borescope.ai.schema import Analysis
from tower_borescope.ai.settings import AiConfig
from tower_borescope.app.style import ERROR_TEXT, LINK_TEXT, MUTED_TEXT
from tower_borescope.app.widgets.html_text import html_escape

ASK_PREFIX: Final = "ask:"
BACKEND_TITLES: Final = {
    "ollama": "Local model via Ollama",
    "anythingllm": "AnythingLLM workspace",
    "anthropic": "Claude via the Anthropic API",
}
STATUS_SEPARATOR: Final = "; "
PENDING_HTML: Final = f"<div style='color:{MUTED_TEXT}'>...</div>"


def _multiline(text: str) -> str:
    """Escaped text with line breaks kept."""
    return html_escape(text).replace("\n", "<br>")


def analyzing_html(backend_name: str) -> str:
    """Placeholder shown while an analysis runs."""
    return (
        f"<div style='color:{MUTED_TEXT}'>Analyzing the frozen frame with "
        f"{html_escape(backend_name)}...<br>A local model takes about 1 to 2 minutes per "
        "analysis; follow-up questions are much faster.</div>"
    )


def error_html(message: str) -> str:
    """A failure message in the error color."""
    return f"<div style='color:{ERROR_TEXT}'>{_multiline(message)}</div>"


def status_text(
    backend: Backend | None, settings: dict[str, object], extra: str = ""
) -> str:
    """The AI status line: backend, session cost, or the configured backend.

    Args:
        backend: The connected backend, or None before the first request.
        settings: Saved settings naming the configured backend.
        extra: Additional note appended at the end.

    Returns:
        Status text such as "Ollama qwen3-vl; local, no cost".
    """
    if backend is not None:
        text = backend.describe()
        cost = estimated_cost(backend)
        if cost:
            text += f"{STATUS_SEPARATOR}this session about ${cost:.2f}"
        elif backend.usage.input_tokens:
            text += f"{STATUS_SEPARATOR}local, no cost"
    else:
        name = AiConfig.from_settings(settings).backend
        text = f"{BACKEND_TITLES.get(name, name)} (not connected yet)"
    return text + (f"{STATUS_SEPARATOR}{extra}" if extra else "")


class AiTranscript:
    """Follow-up questions and answers shown below the analysis.

    Attributes:
        html: Finished questions and answers.
        streamed: Text of the answer arriving now.
    """

    def __init__(self) -> None:
        self.html = ""
        self.streamed = ""

    def clear(self) -> None:
        """Forget the questions and answers of an earlier analysis."""
        self.html = ""
        self.streamed = ""

    def add_question(self, question: str) -> None:
        """Record a question and start a new streamed answer."""
        self.html += (
            f"<div style='margin-top:12px;color:{MUTED_TEXT}'>"
            f"You: {html_escape(question)}</div>"
        )
        self.streamed = ""

    def stream(self, chunk: str) -> str:
        """Append a chunk of the arriving answer and return its rich text."""
        self.streamed += chunk
        return f"<div style='margin-top:4px'>{_multiline(self.streamed)}</div>"

    def add_answer(self, answer: str) -> None:
        """Record the complete answer."""
        self.html += f"<div style='margin-top:4px'>{_multiline(answer)}</div>"
        self.streamed = ""

    def render(self, analysis: Analysis, extra_html: str = "") -> str:
        """The panel contents: analysis, suggested questions, transcript and extra.

        Args:
            analysis: The analysis of the frozen frame.
            extra_html: Rich text for an answer still arriving.

        Returns:
            The complete rich text.
        """
        parts = [analysis_html(analysis)]
        if analysis.questions:
            parts.append("<div style='margin-top:10px;font-weight:600'>Ask next</div>")
            links = "".join(
                f"<li><a href='{ASK_PREFIX}{html_escape(question)}' "
                f"style='color:{LINK_TEXT};text-decoration:none'>"
                f"{html_escape(question)}</a></li>"
                for question in analysis.questions
            )
            parts.append(f"<ul style='margin:2px 0 0 -18px'>{links}</ul>")
        parts.append(self.html)
        return "".join(parts) + extra_html
