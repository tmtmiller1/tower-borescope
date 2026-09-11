"""Local vision models through the Ollama chat API.

Structured answers use Ollama's ``format`` option with the pydantic JSON schema.
Requests set ``think`` to false and carry no ``num_predict`` cap, because a cap cuts a
reasoning model off with empty content. Thinking variants such as ``qwen3-vl:4b``
ignore ``think`` and reason for minutes before answering, so automatic selection
prefers ``RECOMMENDED_MODEL`` and then vision models without the thinking capability.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from tower_borescope.ai.base import (
    LOCAL_IMAGE_WIDTH,
    AiError,
    Backend,
    ChatMessage,
    TextCallback,
)
from tower_borescope.ai.http import base_url, http_json, http_stream_lines
from tower_borescope.ai.images import to_base64
from tower_borescope.ai.parsing import parse_reply
from tower_borescope.ai.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT
from tower_borescope.ai.schema import Analysis, ScaleEstimate

VISION_HINTS: tuple[str, ...] = (
    "vl",
    "vision",
    "llava",
    "minicpm-v",
    "gemma3",
    "moondream",
    "bakllava",
)
OLLAMA_URL_VARIABLE = "TOWER_BORESCOPE_OLLAMA_URL"
RECOMMENDED_MODEL = "qwen3-vl:4b-instruct"
PULL_HINT = f"ollama pull {RECOMMENDED_MODEL}"
THINKING_CAPABILITY = "thinking"
THINKING_NOTE = "thinks before answering"
NOT_VISION_NOTE = "not a vision model"
LIST_TIMEOUT = 5.0
CHECK_TIMEOUT = 10.0
ANALYSIS_TEMPERATURE = 0.2
CHAT_TEMPERATURE = 0.3


def looks_like_vision_model(name: str) -> bool:
    """True when a model name suggests image input support."""
    lowered = name.lower()
    return any(hint in lowered for hint in VISION_HINTS)


def _family(name: str) -> str:
    """Model name without its tag, such as ``qwen3-vl`` for ``qwen3-vl:4b``."""
    return name.split(":")[0]


def _model_names(data: dict[str, Any]) -> list[str]:
    """Installed model names from an ``/api/tags`` reply."""
    models = data.get("models")
    if not isinstance(models, list):
        return []
    return [
        str(item["name"]) for item in models if isinstance(item, dict) and "name" in item
    ]


def _is_installed(name: str, names: Sequence[str]) -> bool:
    """True when ``name`` matches an installed model with or without its tag."""
    return name in names or name in map(_family, names)


def model_capabilities(url: str, name: str) -> frozenset[str]:
    """Capabilities Ollama reports for an installed model.

    Args:
        url: Ollama base address.
        name: Installed model name.

    Returns:
        Capability names such as ``vision`` and ``thinking``; empty when Ollama does
        not answer or does not know the model.
    """
    endpoint = f"{url.strip().rstrip('/')}/api/show"
    try:
        data = http_json(endpoint, {"model": name}, timeout=LIST_TIMEOUT)
    except AiError:
        return frozenset()
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        return frozenset()
    return frozenset(str(item) for item in capabilities)


def _automatic_model(url: str, names: Sequence[str]) -> str:
    """The recommended model, else a vision model that answers without thinking.

    A thinking vision model is chosen only when no other vision model is installed.
    """
    if RECOMMENDED_MODEL in names:
        return RECOMMENDED_MODEL
    vision = [name for name in names if looks_like_vision_model(name)]
    direct = (
        name
        for name in vision
        if THINKING_CAPABILITY not in model_capabilities(url, name)
    )
    return next(direct, next(iter(vision), ""))


def resolve_model(url: str, preferred: str = "") -> str:
    """Choose the model to use.

    Args:
        url: Ollama base address.
        preferred: Configured model name, with or without a tag; empty for automatic.

    Returns:
        ``preferred`` when installed; else ``RECOMMENDED_MODEL`` when installed; else
        the first installed vision model without the thinking capability; else the
        first installed vision model; else ``preferred`` or the first installed model;
        else an empty string.
    """
    names = OllamaBackend.list_models(url)
    if preferred and _is_installed(preferred, names):
        return preferred
    return _automatic_model(url, names) or preferred or next(iter(names), "")


def _model_notes(url: str, model: str) -> list[str]:
    """Warnings shown after the model name in the backend name."""
    notes = [] if looks_like_vision_model(model) else [NOT_VISION_NOTE]
    if THINKING_CAPABILITY in model_capabilities(url, model):
        notes.append(THINKING_NOTE)
    return notes


def _ollama_messages(
    messages: Sequence[ChatMessage], system: str
) -> list[dict[str, Any]]:
    """Chat messages in Ollama's shape, with images as base64 text."""
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        entry: dict[str, Any] = {"role": message["role"], "content": message["text"]}
        jpeg = message.get("jpeg")
        if jpeg:
            entry["images"] = [to_base64(jpeg)]
        converted.append(entry)
    return converted


def _reply_text(data: dict[str, Any]) -> str:
    """The ``message.content`` text of a chat reply or stream event."""
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else ""


def _decode_event(line: str) -> dict[str, Any]:
    """One NDJSON stream event, or an empty dictionary for an unreadable line."""
    try:
        decoded = json.loads(line)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


class OllamaBackend(Backend):
    """A vision model served by a local Ollama.

    Attributes:
        url: Ollama base address.
        model: Resolved model name.
    """

    max_image_width = LOCAL_IMAGE_WIDTH

    def __init__(self, url: str, model: str = "") -> None:
        super().__init__()
        self.url = base_url(url, "Ollama", OLLAMA_URL_VARIABLE)
        self.model = resolve_model(self.url, model)
        if not self.model:
            raise AiError(
                f"Ollama at {self.url} has no models or is not running. "
                f"Install a vision model with: {PULL_HINT}"
            )
        details = [self.model, *_model_notes(self.url, self.model)]
        self.name = f"Ollama ({', '.join(details)})"

    def _structured[ModelT: BaseModel](
        self, jpeg: bytes, prompt: str, schema_model: type[ModelT]
    ) -> ModelT:
        """Request a JSON answer constrained by the schema of ``schema_model``."""
        message: ChatMessage = {"role": "user", "text": prompt, "jpeg": jpeg}
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": schema_model.model_json_schema(),
            "options": {"temperature": ANALYSIS_TEMPERATURE},
            "messages": _ollama_messages([message], SYSTEM_PROMPT),
        }
        data = http_json(f"{self.url}/api/chat", payload)
        self.usage.add(data.get("prompt_eval_count"), data.get("eval_count"))
        return parse_reply(_reply_text(data), schema_model, "The model")

    def analyze(self, jpeg: bytes, prompt: str) -> Analysis:
        """Return a structured analysis of one JPEG frame."""
        return self._structured(jpeg, prompt, Analysis)

    def scale(self, jpeg: bytes, prompt: str) -> ScaleEstimate:
        """Return a scale estimate for one JPEG frame."""
        return self._structured(jpeg, prompt, ScaleEstimate)

    def chat(self, messages: Sequence[ChatMessage], on_text: TextCallback) -> str:
        """Stream an answer from the NDJSON chat endpoint."""
        payload = {
            "model": self.model,
            "stream": True,
            "think": False,
            "options": {"temperature": CHAT_TEMPERATURE},
            "messages": _ollama_messages(messages, CHAT_SYSTEM_PROMPT),
        }
        parts: list[str] = []
        for line in http_stream_lines(f"{self.url}/api/chat", payload):
            event = _decode_event(line)
            chunk = _reply_text(event)
            if chunk:
                parts.append(chunk)
                on_text(chunk)
            if event.get("done"):
                self.usage.add(event.get("prompt_eval_count"), event.get("eval_count"))
        return "".join(parts)

    def check(self) -> str:
        """Confirm Ollama answers and has the model installed."""
        names = _model_names(http_json(f"{self.url}/api/tags", timeout=CHECK_TIMEOUT))
        if not names:
            raise AiError(
                f"Ollama is running but has no models. Pull a vision model: {PULL_HINT}"
            )
        if self.model not in names and _family(self.model) not in map(_family, names):
            available = ", ".join(names)
            raise AiError(
                f"Model '{self.model}' is not in Ollama. Available: {available}"
            )
        return (
            f"Ollama at {self.url}: {self.model} available "
            f"({len(names)} model(s) installed)"
        )

    @staticmethod
    def list_models(url: str) -> list[str]:
        """Installed model names, or an empty list when Ollama is unreachable."""
        if not url.strip():
            return []
        try:
            data = http_json(f"{url.strip().rstrip('/')}/api/tags", timeout=LIST_TIMEOUT)
        except AiError:
            return []
        return _model_names(data)
