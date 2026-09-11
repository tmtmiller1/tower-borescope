"""Tests for tower_borescope.ai.base: errors, usage counting and the Backend contract."""

from __future__ import annotations

import pytest

from tower_borescope.ai.base import HOSTED_IMAGE_WIDTH, AiError, Backend, Usage
from tower_borescope.ai.schema import fallback_analysis
from tower_borescope.errors import BorescopeError


class EchoBackend(Backend):
    name = "Echo"

    def __init__(self):
        super().__init__()
        self.received = []

    def analyze(self, jpeg, prompt):
        return fallback_analysis(prompt)

    def chat(self, messages, on_text):
        self.received = list(messages)
        on_text("chunk")
        return f"echo: {messages[-1]['text']}"

    def scale(self, jpeg, prompt):
        raise AiError("no scale")

    def check(self):
        return "ok"


def test_ai_error_is_a_borescope_error():
    assert issubclass(AiError, BorescopeError)


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        Backend()


def test_usage_adds_counts_and_ignores_missing_values():
    usage = Usage()
    usage.add(10, None)
    usage.add(None, 5)
    usage.add(2, 3)
    assert usage == Usage(input_tokens=12, output_tokens=8)


def test_summarize_sends_one_text_turn():
    backend = EchoBackend()
    assert backend.summarize("Summarize the views") == "echo: Summarize the views"
    assert backend.received == [
        {"role": "user", "text": "Summarize the views", "jpeg": None}
    ]


def test_defaults_describe_free_hosted_width():
    backend = EchoBackend()
    assert backend.describe() == "Echo"
    assert backend.cost_per_token == (0.0, 0.0)
    assert backend.max_image_width == HOSTED_IMAGE_WIDTH
    assert backend.usage == Usage()
