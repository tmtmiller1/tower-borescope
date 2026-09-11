"""Backend construction from the AI configuration, and cost estimates."""

from __future__ import annotations

from tower_borescope.ai.anythingllm import AnythingLLMBackend
from tower_borescope.ai.base import AiError, Backend
from tower_borescope.ai.ollama import OllamaBackend
from tower_borescope.ai.settings import BACKENDS, AiConfig


def make_backend(
    config: AiConfig,
    anythingllm_key: str | None = None,
    anthropic_key: str | None = None,
) -> Backend:
    """Build the backend named by ``config.backend``.

    Args:
        config: Backend choice and endpoints.
        anythingllm_key: AnythingLLM key; None reads the environment or Keychain.
        anthropic_key: Anthropic key; None reads the environment or Keychain.

    Returns:
        A ready backend.

    Raises:
        AiError: When the backend name is unknown or the backend cannot start.
    """
    if config.backend == "ollama":
        return OllamaBackend(config.ollama_url, config.ollama_model)
    if config.backend == "anythingllm":
        return AnythingLLMBackend(
            config.anythingllm_url, config.anythingllm_workspace, anythingllm_key
        )
    if config.backend == "anthropic":
        # The SDK import is deferred so that local backends start without loading it.
        from tower_borescope.ai.anthropic_backend import AnthropicBackend

        return AnthropicBackend(config.anthropic_model, anthropic_key)
    raise AiError(
        f"Unknown AI backend '{config.backend}'. Choose one of: {', '.join(BACKENDS)}"
    )


def estimated_cost(backend: Backend) -> float:
    """Dollars spent so far at the backend's list price; local backends cost nothing."""
    input_price, output_price = backend.cost_per_token
    usage = backend.usage
    return usage.input_tokens * input_price + usage.output_tokens * output_price
