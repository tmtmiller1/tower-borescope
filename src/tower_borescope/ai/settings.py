"""AI backend selection and endpoints read from the settings file and environment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tower_borescope.config import env_value

DEFAULT_BACKEND = "ollama"
ANTHROPIC_MODEL = "claude-opus-5"
BACKENDS: tuple[str, ...] = ("ollama", "anythingllm", "anthropic")
OLLAMA_URL_ENV = "OLLAMA_URL"
ANYTHINGLLM_URL_ENV = "ANYTHINGLLM_URL"


def _text(settings: Mapping[str, Any], key: str, default: str) -> str:
    """A non-blank string setting, else ``default``."""
    value = settings.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


@dataclass(slots=True)
class AiConfig:
    """Which backend to use and how to reach it.

    Attributes:
        backend: One of ``BACKENDS``.
        ollama_url: Ollama base address; empty when unconfigured.
        ollama_model: Preferred Ollama model; empty selects an installed vision model.
        anythingllm_url: AnythingLLM base address; empty when unconfigured.
        anythingllm_workspace: AnythingLLM workspace slug.
        anthropic_model: Claude model identifier.
    """

    backend: str = DEFAULT_BACKEND
    ollama_url: str = ""
    ollama_model: str = ""
    anythingllm_url: str = ""
    anythingllm_workspace: str = ""
    anthropic_model: str = ANTHROPIC_MODEL

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None = None) -> AiConfig:
        """Build a configuration from saved settings.

        Blank or missing URLs fall back to ``TOWER_BORESCOPE_OLLAMA_URL`` and
        ``TOWER_BORESCOPE_ANYTHINGLLM_URL``; an unset variable leaves the URL empty.

        Args:
            settings: The application settings dictionary, or None.

        Returns:
            The resolved configuration.
        """
        values: Mapping[str, Any] = settings or {}
        return cls(
            backend=_text(values, "ai_backend", DEFAULT_BACKEND),
            ollama_url=_text(values, "ollama_url", env_value(OLLAMA_URL_ENV) or ""),
            ollama_model=_text(values, "ollama_model", ""),
            anythingllm_url=_text(
                values, "anythingllm_url", env_value(ANYTHINGLLM_URL_ENV) or ""
            ),
            anythingllm_workspace=_text(values, "anythingllm_workspace", ""),
            anthropic_model=_text(values, "anthropic_model", ANTHROPIC_MODEL),
        )

    def to_dict(self) -> dict[str, str]:
        """Settings keys and values for saving."""
        return {
            "ai_backend": self.backend,
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "anythingllm_url": self.anythingllm_url,
            "anythingllm_workspace": self.anythingllm_workspace,
            "anthropic_model": self.anthropic_model,
        }
