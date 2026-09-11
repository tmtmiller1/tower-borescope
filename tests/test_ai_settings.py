"""Tests for tower_borescope.ai.settings: defaults, environment URLs and round trips."""

from __future__ import annotations

import pytest

from tower_borescope.ai.settings import ANTHROPIC_MODEL, AiConfig

OLLAMA_VARIABLE = "TOWER_BORESCOPE_OLLAMA_URL"
ANYTHINGLLM_VARIABLE = "TOWER_BORESCOPE_ANYTHINGLLM_URL"
OLLAMA_PLACEHOLDER = "http://ollama.invalid:11434"
ANYTHINGLLM_PLACEHOLDER = "http://anythingllm.invalid:3001"


@pytest.fixture
def unset_urls(monkeypatch):
    monkeypatch.delenv(OLLAMA_VARIABLE, raising=False)
    monkeypatch.delenv(ANYTHINGLLM_VARIABLE, raising=False)


def test_defaults_to_local_ollama_with_empty_urls(unset_urls):
    config = AiConfig.from_settings({})
    assert config.backend == "ollama"
    assert config.ollama_url == "" and config.anythingllm_url == ""
    assert config.ollama_model == "" and config.anythingllm_workspace == ""
    assert config.anthropic_model == ANTHROPIC_MODEL


def test_urls_default_from_environment(monkeypatch):
    monkeypatch.setenv(OLLAMA_VARIABLE, OLLAMA_PLACEHOLDER)
    monkeypatch.setenv(ANYTHINGLLM_VARIABLE, f"  {ANYTHINGLLM_PLACEHOLDER}  ")
    config = AiConfig.from_settings(None)
    assert config.ollama_url == OLLAMA_PLACEHOLDER
    assert config.anythingllm_url == ANYTHINGLLM_PLACEHOLDER


def test_saved_settings_override_environment_unless_blank(monkeypatch):
    monkeypatch.setenv(OLLAMA_VARIABLE, OLLAMA_PLACEHOLDER)
    monkeypatch.setenv(ANYTHINGLLM_VARIABLE, ANYTHINGLLM_PLACEHOLDER)
    saved = {
        "ai_backend": "anythingllm",
        "ollama_url": "   ",
        "anythingllm_url": "http://saved.invalid:3001",
        "anythingllm_workspace": "home",
        "ollama_model": "llava:7b",
        "anthropic_model": 42,
    }
    config = AiConfig.from_settings(saved)
    assert config.backend == "anythingllm" and config.anythingllm_workspace == "home"
    assert config.ollama_url == OLLAMA_PLACEHOLDER
    assert config.anythingllm_url == "http://saved.invalid:3001"
    assert config.ollama_model == "llava:7b"
    assert config.anthropic_model == ANTHROPIC_MODEL


def test_to_dict_round_trips(unset_urls):
    config = AiConfig(
        backend="anthropic",
        ollama_url=OLLAMA_PLACEHOLDER,
        ollama_model="qwen3-vl:4b",
        anythingllm_url=ANYTHINGLLM_PLACEHOLDER,
        anythingllm_workspace="garage",
        anthropic_model=ANTHROPIC_MODEL,
    )
    saved = config.to_dict()
    assert saved["ai_backend"] == "anthropic"
    assert AiConfig.from_settings(saved) == config
