"""Tests for tower_borescope.app.dialogs.ai_settings with the Keychain, Ollama and
AnythingLLM replaced, so no test reads or writes real keys or reaches a service."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from fakes import FakeBackend
from tower_borescope.ai import keychain
from tower_borescope.ai.anythingllm import AnythingLLMBackend
from tower_borescope.ai.base import AiError
from tower_borescope.ai.ollama import OllamaBackend
from tower_borescope.app.dialogs import ai_settings
from tower_borescope.app.dialogs.ai_settings import AiSettingsDialog

SETTINGS = {
    "ai_backend": "ollama",
    "ollama_url": "http://ollama.test:11434",
    "ollama_model": "llama3:8b",
    "anythingllm_url": "http://allm.test:3001",
    "anythingllm_workspace": "inspect",
}


class FakeKeychain:
    def __init__(self):
        self.stored = {}
        self.error = None

    def set_secret(self, service, value):
        if self.error is not None:
            raise self.error
        self.stored[service] = value


@pytest.fixture
def fake_keychain(monkeypatch):
    fake = FakeKeychain()

    def refuse(*args, **kwargs):
        raise AssertionError("the real Keychain must not be touched")

    monkeypatch.setattr(keychain.subprocess, "run", refuse)
    monkeypatch.setattr(keychain, "set_secret", fake.set_secret)
    monkeypatch.setattr(keychain, "get_secret", lambda service, **kwargs: None)
    monkeypatch.setattr(keychain, "anthropic_key", lambda: None)
    monkeypatch.setattr(keychain, "anythingllm_key", lambda: "stored-key")
    return fake


@pytest.fixture
def services(monkeypatch):
    models = ["qwen3-vl:4b", "llama3:8b"]
    monkeypatch.setattr(OllamaBackend, "list_models", staticmethod(lambda url: models))
    spaces = [("inspect", "Inspection"), ("notes", "Notes")]
    monkeypatch.setattr(
        AnythingLLMBackend, "list_workspaces", staticmethod(lambda url, key=None: spaces)
    )
    return models


@pytest.fixture
def dialog(qapp, fake_keychain, services):
    return AiSettingsDialog(dict(SETTINGS))


def test_builds_with_ollama_selected(dialog):
    assert dialog.windowTitle() == "AI settings"
    assert dialog.selected_backend() == "ollama"
    assert not dialog.sections["ollama"].isHidden()
    assert dialog.sections["anythingllm"].isHidden()
    assert dialog.sections["anthropic"].isHidden()


def test_lists_models_workspaces_and_key_state(dialog):
    assert dialog.ollama_model.count() == 3
    assert dialog.ollama_model.itemText(0) == "(auto: first vision model)"
    assert dialog.ollama_model.itemText(2) == "llama3:8b   (not a vision model)"
    assert dialog.ollama_model.currentData() == "llama3:8b"
    assert dialog.allm_workspace.currentData() == "inspect"
    assert dialog.allm_key.placeholderText() == "stored in Keychain"
    assert dialog.anthropic_key.placeholderText() == "paste an Anthropic API key"


def test_defaults_to_ollama_without_settings(qapp, fake_keychain, services):
    assert AiSettingsDialog({}).selected_backend() == "ollama"


def test_switching_backend_shows_one_section(dialog):
    dialog.backend_combo.setCurrentIndex(2)
    assert dialog.selected_backend() == "anthropic"
    assert dialog.sections["ollama"].isHidden()
    assert not dialog.sections["anthropic"].isHidden()
    dialog.backend_combo.setCurrentIndex(1)
    assert not dialog.sections["anythingllm"].isHidden()


def test_current_config_reads_the_fields(dialog):
    dialog.backend_combo.setCurrentIndex(1)
    dialog.ollama_model.setCurrentIndex(1)
    dialog.allm_workspace.setCurrentIndex(1)
    dialog.anthropic_model.setText("  ")
    config = dialog.current_config().to_dict()
    assert config == {
        "ai_backend": "anythingllm",
        "ollama_url": "http://ollama.test:11434",
        "ollama_model": "qwen3-vl:4b",
        "anythingllm_url": "http://allm.test:3001",
        "anythingllm_workspace": "notes",
        "anthropic_model": "claude-opus-5",
    }


def test_typed_workspace_is_read_from_the_text(qapp, fake_keychain, monkeypatch):
    monkeypatch.setattr(OllamaBackend, "list_models", staticmethod(lambda url: []))
    monkeypatch.setattr(
        AnythingLLMBackend, "list_workspaces", staticmethod(lambda url, key=None: [])
    )
    dialog = AiSettingsDialog({"anythingllm_workspace": "garage"})
    assert dialog.allm_workspace.currentText() == "garage"
    assert dialog.current_config().anythingllm_workspace == "garage"
    assert dialog.result_label.text().startswith("Ollama not reachable at")


def test_save_stores_typed_keys_in_the_keychain(dialog, fake_keychain):
    assert AiSettingsDialog.accept is AiSettingsDialog._accept
    dialog.allm_key.setText(" allm-secret ")
    dialog.anthropic_key.setText("sk-test")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert fake_keychain.stored == {
        keychain.ANYTHINGLLM_SERVICE: "allm-secret",
        keychain.ANTHROPIC_SERVICE: "sk-test",
    }


def test_save_without_keys_stores_nothing(dialog, fake_keychain):
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert fake_keychain.stored == {}


def test_keychain_failure_keeps_the_dialog_open(dialog, fake_keychain):
    fake_keychain.error = AiError("denied")
    dialog.anthropic_key.setText("sk-test")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.result_label.text() == "Error: Could not store the key: denied"


def test_connection_test_reports_success_and_failure(dialog, monkeypatch):
    built = []

    def fake_make_backend(config, anythingllm_key=None, anthropic_key=None):
        built.append((config.backend, anthropic_key))
        return FakeBackend()

    monkeypatch.setattr(ai_settings, "make_backend", fake_make_backend)
    dialog.anthropic_key.setText("sk-typed")
    dialog.test_connection()
    assert dialog.result_label.text() == "OK: fake ok"
    assert built == [("ollama", "sk-typed")]

    def failing(config, anythingllm_key=None, anthropic_key=None):
        raise AiError("Ollama is not running")

    monkeypatch.setattr(ai_settings, "make_backend", failing)
    dialog.test_connection()
    assert dialog.result_label.text() == "Error: Ollama is not running"
