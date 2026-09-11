"""Tests for tower_borescope.ai.anthropic_backend with an injected fake SDK client.

No test calls the Anthropic API or reads a stored key.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from synthetic import textured_frame
from tower_borescope.ai import keychain
from tower_borescope.ai.anthropic_backend import AnthropicBackend
from tower_borescope.ai.base import AiError, Usage
from tower_borescope.ai.factory import estimated_cost
from tower_borescope.ai.images import to_base64
from tower_borescope.ai.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT
from tower_borescope.ai.schema import Analysis, ScaleEstimate, fallback_analysis
from tower_borescope.jpeg import encode_jpeg

JPEG = encode_jpeg(textured_frame(160, 120))
REQUEST = httpx2.Request("POST", "/v1/messages")


def _status_error(error_class, status):
    response = httpx2.Response(status, request=REQUEST)
    return error_class("rejected", response=response, body=None)


class FakeMessages:
    def __init__(self, parsed, stop_reason, error):
        self.parsed = parsed
        self.stop_reason = stop_reason
        self.error = error
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200)
        return SimpleNamespace(
            usage=usage, stop_reason=self.stop_reason, parsed_output=self.parsed
        )

    @contextlib.contextmanager
    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        final = SimpleNamespace(usage=SimpleNamespace(input_tokens=300, output_tokens=12))
        chunks = iter(["Tighten ", "the nut."])
        yield SimpleNamespace(text_stream=chunks, get_final_message=lambda: final)


class FakeModels:
    def __init__(self, error):
        self.error = error
        self.calls = []

    def retrieve(self, model_id):
        self.calls.append(model_id)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(id=model_id)


def fake_client(parsed=None, stop_reason="end_turn", error=None):
    return SimpleNamespace(
        messages=FakeMessages(parsed, stop_reason, error), models=FakeModels(error)
    )


def test_analyze_sends_image_and_schema_and_counts_cost():
    sample = fallback_analysis("A pipe.")
    client = fake_client(parsed=sample)
    backend = AnthropicBackend(client=client)
    assert backend.analyze(JPEG, "Analyze this scope view.") == sample
    call = client.messages.calls[-1]
    assert call["output_format"] is Analysis and call["system"] == SYSTEM_PROMPT
    assert call["model"] == "claude-opus-5"
    image, text = call["messages"][0]["content"]
    assert image["source"] == {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": to_base64(JPEG),
    }
    assert text == {"type": "text", "text": "Analyze this scope view."}
    assert estimated_cost(backend) == pytest.approx(1000 * 5e-6 + 200 * 25e-6)


def test_scale_uses_the_scale_model():
    estimate = ScaleEstimate(
        found=False,
        reference_object="",
        standard_size_mm=0,
        confidence="low",
        reasoning="Nothing standard.",
    )
    client = fake_client(parsed=estimate)
    assert AnthropicBackend(client=client).scale(JPEG, "scale") == estimate
    assert client.messages.calls[-1]["output_format"] is ScaleEstimate


def test_refusal_and_missing_output_raise():
    refused = AnthropicBackend(client=fake_client(stop_reason="refusal"))
    with pytest.raises(AiError, match="declined"):
        refused.analyze(JPEG, "Analyze")
    assert refused.usage == Usage(1000, 200)
    with pytest.raises(AiError, match="no structured answer"):
        AnthropicBackend(client=fake_client()).analyze(JPEG, "Analyze")


def test_chat_streams_and_sends_the_whole_conversation():
    client = fake_client()
    backend = AnthropicBackend("claude-opus-5", client=client)
    history = [
        {"role": "user", "text": "Analyze", "jpeg": JPEG},
        {"role": "assistant", "text": "prior answer", "jpeg": None},
        {"role": "user", "text": "Is it leaking?", "jpeg": None},
    ]
    chunks = []
    assert backend.chat(history, chunks.append) == "Tighten the nut."
    call = client.messages.calls[-1]
    assert chunks == ["Tighten ", "the nut."] and call["system"] == CHAT_SYSTEM_PROMPT
    assert call["messages"][0]["content"][0]["type"] == "image"
    assert call["messages"][1] == {"role": "assistant", "content": "prior answer"}
    assert call["messages"][2]["content"] == [{"type": "text", "text": "Is it leaking?"}]
    assert backend.usage == Usage(300, 12)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (_status_error(anthropic.AuthenticationError, 401), "key was rejected"),
        (_status_error(anthropic.RateLimitError, 429), "Rate limited"),
        (_status_error(anthropic.InternalServerError, 500), "API error 500: rejected"),
        (anthropic.APIConnectionError(request=REQUEST), "Could not reach"),
    ],
)
def test_sdk_errors_become_ai_errors(error, message):
    backend = AnthropicBackend(client=fake_client(error=error))
    with pytest.raises(AiError, match=message):
        backend.analyze(JPEG, "Analyze")
    with pytest.raises(AiError, match=message):
        backend.chat([{"role": "user", "text": "hi", "jpeg": None}], print)
    with pytest.raises(AiError, match=message):
        backend.check()


def test_check_retrieves_the_model():
    client = fake_client()
    backend = AnthropicBackend("claude-opus-5", client=client)
    assert backend.check() == "Anthropic API reachable; model claude-opus-5"
    assert client.models.calls == ["claude-opus-5"]


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv(keychain.ANTHROPIC_KEY_ENV, raising=False)
    monkeypatch.setattr(keychain, "get_secret", lambda service, **options: None)
    with pytest.raises(AiError, match="API key"):
        AnthropicBackend()


def test_explicit_key_builds_an_sdk_client_without_network():
    backend = AnthropicBackend(api_key="placeholder-not-a-key")
    assert isinstance(backend.client, anthropic.Anthropic)
    assert backend.name == "Claude (claude-opus-5)"
    assert backend.max_image_width == 1280
    assert backend.cost_per_token == (5e-6, 25e-6)
