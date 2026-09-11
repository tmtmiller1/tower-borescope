"""Recovery of JSON objects from model replies that wrap them in prose or fences."""

from __future__ import annotations

import json
import re
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from tower_borescope.ai.base import AiError
from tower_borescope.ai.schema import Analysis, fallback_analysis

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_DECODER = json.JSONDecoder()


def extract_json(text: str) -> dict[str, Any]:
    """Return the first JSON object in a model reply.

    A fenced block (with or without a ``json`` tag) is preferred; otherwise the first
    brace that starts a decodable object is used, so leading and trailing prose is
    ignored.

    Args:
        text: The model's reply.

    Returns:
        The decoded object.

    Raises:
        ValueError: When the reply contains no complete JSON object.
    """
    body = text.strip()
    fence = _FENCE_RE.search(body)
    if fence:
        body = fence.group(1)
    start = body.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    while start >= 0:
        try:
            decoded, _end = _DECODER.raw_decode(body, start)
        except json.JSONDecodeError:
            start = body.find("{", start + 1)
            continue
        if isinstance(decoded, dict):
            return decoded
        start = body.find("{", start + 1)
    raise ValueError("unterminated or invalid JSON object in reply")


def parse_reply[ModelT: BaseModel](
    text: str, schema_model: type[ModelT], source: str
) -> ModelT:
    """Validate a reply as ``schema_model``, tolerating prose around the JSON.

    Args:
        text: The model's reply.
        schema_model: Expected answer type.
        source: Who answered, for the error message, such as ``"The model"``.

    Returns:
        The validated answer. An unusable reply to an analysis request becomes
        :func:`~tower_borescope.ai.schema.fallback_analysis` so the prose still shows.

    Raises:
        AiError: When a reply to any other request cannot be validated.
    """
    try:
        return schema_model.model_validate_json(text)
    except ValidationError:
        pass
    try:
        return schema_model.model_validate(extract_json(text))
    except (ValueError, ValidationError) as error:
        if schema_model is Analysis:
            return cast(ModelT, fallback_analysis(text))
        raise AiError(f"{source} did not return a usable answer: {error}") from error
