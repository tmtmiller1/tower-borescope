"""Tests for tower_borescope.ai.factory: backend dispatch and cost estimates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tower_borescope.ai.anthropic_backend import AnthropicBackend
from tower_borescope.ai.anythingllm import AnythingLLMBackend
from tower_borescope.ai.base import AiError
from tower_borescope.ai.factory import estimated_cost, make_backend
from tower_borescope.ai.ollama import OllamaBackend
from tower_borescope.ai.settings import AiConfig

OLLAMA_PLACEHOLDER = "http://ollama.invalid:11434"
ANYTHINGLLM_PLACEHOLDER = "http://anythingllm.invalid:3001"


def test_ollama_backend_resolves_an_installed_model(monkeypatch):
    monkeypatch.setattr(
        OllamaBackend, "list_models", staticmethod(lambda url: ["llava:7b"])
    )
    backend = make_backend(AiConfig(ollama_url=OLLAMA_PLACEHOLDER))
    assert isinstance(backend, OllamaBackend)
    assert backend.model == "llava:7b"


def test_ollama_without_url_names_the_variable():
    with pytest.raises(AiError, match="TOWER_BORESCOPE_OLLAMA_URL"):
        make_backend(AiConfig(ollama_url=""))


def test_anythingllm_backend_takes_the_given_key():
    config = AiConfig(
        backend="anythingllm",
        anythingllm_url=ANYTHINGLLM_PLACEHOLDER,
        anythingllm_workspace="home",
    )
    backend = make_backend(config, anythingllm_key="given-key")
    assert isinstance(backend, AnythingLLMBackend)
    assert backend.api_key == "given-key" and backend.workspace == "home"


def test_anthropic_backend_takes_the_given_key():
    config = AiConfig(backend="anthropic", anthropic_model="claude-opus-5")
    backend = make_backend(config, anthropic_key="placeholder-not-a-key")
    assert isinstance(backend, AnthropicBackend)
    assert backend.model == "claude-opus-5"


def test_unknown_backend_raises():
    with pytest.raises(AiError, match="Unknown AI backend 'openai'"):
        make_backend(AiConfig(backend="openai"))


def test_local_backends_cost_nothing_and_claude_uses_list_price():
    local = AnythingLLMBackend(ANYTHINGLLM_PLACEHOLDER, "home", "given-key")
    local.usage.add(1500, 600)
    assert estimated_cost(local) == 0.0
    hosted = AnthropicBackend(client=SimpleNamespace())
    hosted.usage.add(1500, 600)
    assert estimated_cost(hosted) == pytest.approx(1500 * 5e-6 + 600 * 25e-6)
