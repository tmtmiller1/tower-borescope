"""A workspace in a local AnythingLLM through its developer API.

The workspace's model must accept images. Structured answers come from asking for a
JSON object that matches the schema. AnythingLLM keeps the thread history per session
id, so an analysis starts a new session and follow-up questions continue it.
"""

from __future__ import annotations

import json
import urllib.parse
import uuid
from collections.abc import Iterable, Sequence
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
from tower_borescope.ai.keychain import anythingllm_key
from tower_borescope.ai.parsing import parse_reply
from tower_borescope.ai.prompts import (
    CHAT_SYSTEM_PROMPT,
    JSON_REPLY_INSTRUCTION,
    SYSTEM_PROMPT,
)
from tower_borescope.ai.schema import Analysis, ScaleEstimate

ANYTHINGLLM_URL_VARIABLE = "TOWER_BORESCOPE_ANYTHINGLLM_URL"
SSE_DATA_PREFIX = "data:"
STREAM_TEXT_TYPES: tuple[str | None, ...] = ("textResponseChunk", "textResponse", None)
LIST_TIMEOUT = 5.0
CHECK_TIMEOUT = 10.0


def _new_session() -> str:
    """A fresh AnythingLLM session id."""
    return str(uuid.uuid4())


def _attachment(jpeg: bytes) -> dict[str, str]:
    """An image attachment in AnythingLLM's data URL form."""
    return {
        "name": "frame.jpg",
        "mime": "image/jpeg",
        "contentString": f"data:image/jpeg;base64,{to_base64(jpeg)}",
    }


def _workspaces(data: dict[str, Any]) -> list[tuple[str, str]]:
    """``(slug, name)`` pairs from a ``/api/v1/workspaces`` reply."""
    items = data.get("workspaces")
    if not isinstance(items, list):
        return []
    return [
        (str(item["slug"]), str(item.get("name") or item["slug"]))
        for item in items
        if isinstance(item, dict) and "slug" in item
    ]


def _sse_event(line: str) -> dict[str, Any] | None:
    """The JSON object of one server-sent ``data:`` line, else None."""
    if not line.startswith(SSE_DATA_PREFIX):
        return None
    try:
        decoded = json.loads(line[len(SSE_DATA_PREFIX) :].strip())
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _collect_stream(lines: Iterable[str], on_text: TextCallback) -> str:
    """Join the text chunks of a stream-chat reply, forwarding each to ``on_text``."""
    parts: list[str] = []
    for line in lines:
        event = _sse_event(line)
        if event is None:
            continue
        if event.get("error"):
            raise AiError(f"AnythingLLM: {event['error']}")
        chunk = event.get("textResponse") or ""
        if chunk and event.get("type") in STREAM_TEXT_TYPES:
            parts.append(str(chunk))
            on_text(str(chunk))
        if event.get("close"):
            break
    return "".join(parts)


class AnythingLLMBackend(Backend):
    """A vision-capable AnythingLLM workspace.

    Attributes:
        url: AnythingLLM base address.
        workspace: Workspace slug.
        api_key: Developer API key, or None when none is configured.
        session: Current session id.
    """

    max_image_width = LOCAL_IMAGE_WIDTH

    def __init__(self, url: str, workspace: str, api_key: str | None = None) -> None:
        super().__init__()
        self.url = base_url(url, "AnythingLLM", ANYTHINGLLM_URL_VARIABLE)
        self.workspace = workspace
        self.api_key = api_key or anythingllm_key()
        self.name = f"AnythingLLM ({workspace or 'no workspace'})"
        self.session = _new_session()

    def _headers(self) -> dict[str, str]:
        """Authorization headers; raises AiError when no key is configured."""
        if not self.api_key:
            raise AiError(
                "AnythingLLM needs its API key: create one in AnythingLLM under "
                "Settings > Tools > Developer API, then enter it in AI settings."
            )
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _workspace_url(self, action: str) -> str:
        """Endpoint for a workspace action; raises AiError when none is chosen."""
        if not self.workspace:
            raise AiError("Choose an AnythingLLM workspace in AI settings.")
        slug = urllib.parse.quote(self.workspace, safe="")
        return f"{self.url}/api/v1/workspace/{slug}/{action}"

    def _payload(self, text: str, jpeg: bytes | None) -> dict[str, Any]:
        """A chat request body for the current session."""
        payload: dict[str, Any] = {
            "message": text,
            "mode": "chat",
            "sessionId": self.session,
        }
        if jpeg:
            payload["attachments"] = [_attachment(jpeg)]
        return payload

    def _structured[ModelT: BaseModel](
        self, jpeg: bytes, prompt: str, schema_model: type[ModelT]
    ) -> ModelT:
        """Ask a new session for a JSON answer matching ``schema_model``."""
        url = self._workspace_url("chat")
        self.session = _new_session()
        schema = json.dumps(schema_model.model_json_schema())
        text = f"{SYSTEM_PROMPT}\n\n{prompt}\n\n{JSON_REPLY_INSTRUCTION}\n{schema}"
        data = http_json(url, self._payload(text, jpeg), self._headers())
        if data.get("error"):
            raise AiError(f"AnythingLLM: {data['error']}")
        metrics = data.get("metrics")
        if isinstance(metrics, dict):
            self.usage.add(metrics.get("prompt_tokens"), metrics.get("completion_tokens"))
        reply = str(data.get("textResponse") or "")
        return parse_reply(reply, schema_model, "The workspace model")

    def analyze(self, jpeg: bytes, prompt: str) -> Analysis:
        """Return a structured analysis of one JPEG frame."""
        return self._structured(jpeg, prompt, Analysis)

    def scale(self, jpeg: bytes, prompt: str) -> ScaleEstimate:
        """Return a scale estimate for one JPEG frame."""
        return self._structured(jpeg, prompt, ScaleEstimate)

    def chat(self, messages: Sequence[ChatMessage], on_text: TextCallback) -> str:
        """Stream an answer to the last turn; the session holds the earlier turns."""
        last = messages[-1]
        text = last["text"]
        if len(messages) == 1:
            text = f"{CHAT_SYSTEM_PROMPT}\n\n{text}"
        url = self._workspace_url("stream-chat")
        payload = self._payload(text, last.get("jpeg"))
        return _collect_stream(http_stream_lines(url, payload, self._headers()), on_text)

    def check(self) -> str:
        """Confirm AnythingLLM answers and the workspace exists."""
        data = http_json(
            f"{self.url}/api/v1/workspaces",
            headers=self._headers(),
            timeout=CHECK_TIMEOUT,
        )
        names = [slug for slug, _title in _workspaces(data)]
        listed = ", ".join(names) or "none"
        if self.workspace and self.workspace not in names:
            raise AiError(f"Workspace '{self.workspace}' not found. Available: {listed}")
        return f"AnythingLLM at {self.url}: workspaces {listed}"

    @staticmethod
    def list_workspaces(url: str, api_key: str | None = None) -> list[tuple[str, str]]:
        """``(slug, name)`` pairs; empty without a key or a reachable server."""
        key = api_key or anythingllm_key()
        address = url.strip().rstrip("/")
        if not key or not address:
            return []
        headers = {"Authorization": f"Bearer {key}"}
        try:
            data = http_json(
                f"{address}/api/v1/workspaces", headers=headers, timeout=LIST_TIMEOUT
            )
        except AiError:
            return []
        return _workspaces(data)
