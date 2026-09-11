"""Claude through the Anthropic SDK.

Structured answers use ``messages.parse`` with the pydantic model as the output
format; follow-up answers stream through ``messages.stream``. SDK errors become
:class:`~tower_borescope.ai.base.AiError` with a plain message.
"""

from __future__ import annotations

from collections.abc import Sequence

import anthropic
from anthropic.types import ImageBlockParam, MessageParam, TextBlockParam
from pydantic import BaseModel

from tower_borescope.ai.base import (
    HOSTED_IMAGE_WIDTH,
    AiError,
    Backend,
    ChatMessage,
    TextCallback,
)
from tower_borescope.ai.images import to_base64
from tower_borescope.ai.keychain import anthropic_key
from tower_borescope.ai.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT
from tower_borescope.ai.schema import Analysis, ScaleEstimate
from tower_borescope.ai.settings import ANTHROPIC_MODEL

INPUT_TOKEN_PRICE = 5e-6
OUTPUT_TOKEN_PRICE = 25e-6
MAX_TOKENS = 16000


def _content(text: str, jpeg: bytes | None) -> list[ImageBlockParam | TextBlockParam]:
    """User content blocks: the image first when present, then the text."""
    blocks: list[ImageBlockParam | TextBlockParam] = []
    if jpeg:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": to_base64(jpeg),
                },
            }
        )
    blocks.append({"type": "text", "text": text})
    return blocks


def _api_message(message: ChatMessage) -> MessageParam:
    """One conversation turn in the Messages API shape."""
    if message["role"] == "user":
        return {"role": "user", "content": _content(message["text"], message.get("jpeg"))}
    return {"role": "assistant", "content": message["text"]}


def _api_error(error: anthropic.APIError) -> AiError:
    """A plain-language AiError for an SDK error."""
    if isinstance(error, anthropic.AuthenticationError):
        return AiError("The Anthropic API key was rejected.")
    if isinstance(error, anthropic.RateLimitError):
        return AiError("Rate limited by the Anthropic API; wait a moment and retry.")
    if isinstance(error, anthropic.APIConnectionError):
        return AiError("Could not reach the Anthropic API.")
    if isinstance(error, anthropic.APIStatusError):
        return AiError(f"Anthropic API error {error.status_code}: {error.message}")
    return AiError(f"Anthropic API error: {error.message}")


def _client(api_key: str | None) -> anthropic.Anthropic:
    """An SDK client for ``api_key`` or the stored key."""
    key = api_key or anthropic_key()
    if not key:
        raise AiError("Anthropic needs an API key: enter it in AI settings.")
    return anthropic.Anthropic(api_key=key)


class AnthropicBackend(Backend):
    """Claude with list-price cost tracking.

    Attributes:
        model: Claude model identifier.
        client: Anthropic SDK client.
    """

    cost_per_token = (INPUT_TOKEN_PRICE, OUTPUT_TOKEN_PRICE)
    max_image_width = HOSTED_IMAGE_WIDTH

    def __init__(
        self,
        model: str = ANTHROPIC_MODEL,
        api_key: str | None = None,
        *,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.name = f"Claude ({model})"
        self.client = client if client is not None else _client(api_key)

    def _structured[ModelT: BaseModel](
        self, jpeg: bytes, prompt: str, schema_model: type[ModelT]
    ) -> ModelT:
        """Request an answer parsed into ``schema_model``."""
        messages: list[MessageParam] = [
            {"role": "user", "content": _content(prompt, jpeg)}
        ]
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                output_format=schema_model,
            )
        except anthropic.APIError as error:
            raise _api_error(error) from error
        self.usage.add(response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            raise AiError("The model declined to analyze this image.")
        parsed = response.parsed_output
        if parsed is None:
            raise AiError("The model returned no structured answer.")
        return parsed

    def analyze(self, jpeg: bytes, prompt: str) -> Analysis:
        """Return a structured analysis of one JPEG frame."""
        return self._structured(jpeg, prompt, Analysis)

    def scale(self, jpeg: bytes, prompt: str) -> ScaleEstimate:
        """Return a scale estimate for one JPEG frame."""
        return self._structured(jpeg, prompt, ScaleEstimate)

    def chat(self, messages: Sequence[ChatMessage], on_text: TextCallback) -> str:
        """Stream an answer, sending the whole conversation."""
        api_messages = [_api_message(message) for message in messages]
        parts: list[str] = []
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=CHAT_SYSTEM_PROMPT,
                messages=api_messages,
            ) as stream:
                for text in stream.text_stream:
                    parts.append(text)
                    on_text(text)
                final = stream.get_final_message()
        except anthropic.APIError as error:
            raise _api_error(error) from error
        self.usage.add(final.usage.input_tokens, final.usage.output_tokens)
        return "".join(parts)

    def check(self) -> str:
        """Confirm the API accepts the key and knows the model."""
        try:
            self.client.models.retrieve(self.model)
        except anthropic.APIError as error:
            raise _api_error(error) from error
        return f"Anthropic API reachable; model {self.model}"
