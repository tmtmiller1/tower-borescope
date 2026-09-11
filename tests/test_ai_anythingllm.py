"""Tests for tower_borescope.ai.anythingllm against a fake AnythingLLM server on loopback.

Stored keys are stubbed for every test, so the real Keychain is never read.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from synthetic import textured_frame
from tower_borescope.ai import keychain
from tower_borescope.ai.anythingllm import AnythingLLMBackend
from tower_borescope.ai.base import AiError, Usage
from tower_borescope.ai.images import to_base64
from tower_borescope.ai.prompts import (
    CHAT_SYSTEM_PROMPT,
    JSON_REPLY_INSTRUCTION,
    SYSTEM_PROMPT,
)
from tower_borescope.ai.schema import FALLBACK_SUBJECT
from tower_borescope.jpeg import encode_jpeg

JPEG = encode_jpeg(textured_frame(160, 120))
API_KEY = "test-key"
WORKSPACES = [{"slug": "home", "name": "Home"}, {"slug": "garage"}]
ANALYSIS_REPLY = """Sure, here is the JSON:
```json
{"subject": "Vent duct", "description": "Foil duct.", "condition": "poor",
 "issues": [], "actions": [], "parts_and_tools": [], "safety": [],
 "confidence": "medium", "questions": []}
```"""
STREAM_EVENTS = [
    {"type": "textResponseChunk", "textResponse": "Dry ", "close": False},
    {"type": "textResponseChunk", "textResponse": "joint.", "close": False},
    {"type": "finalizeResponseStream", "textResponse": "ignored", "close": True},
    {"type": "textResponseChunk", "textResponse": "after close"},
]


class AnythingHandler(BaseHTTPRequestHandler):
    def _quiet(self, *args):
        return None

    def _send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        return self.headers.get("Authorization") == f"Bearer {API_KEY}"

    def _get(self):
        if not self._authorized():
            self._send_json(403, {"error": "No valid api key"})
            return
        self._send_json(200, {"workspaces": WORKSPACES})

    def _post(self):
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length))
        self.server.requests.append(
            (self.path, request, self.headers.get("Authorization"))
        )
        if self.path.endswith("/stream-chat"):
            self._stream()
            return
        reply = {"textResponse": self.server.reply, "error": self.server.error}
        reply["metrics"] = {"prompt_tokens": 90, "completion_tokens": 20}
        self._send_json(200, reply)

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        events = self.server.stream_events
        lines = [
            ": keepalive",
            "data: not-json",
            *(f"data: {json.dumps(e)}" for e in events),
        ]
        self.wfile.write("\n\n".join(lines).encode() + b"\n\n")

    do_GET = _get
    do_POST = _post
    log_message = _quiet


class FakeAnythingLLM(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), AnythingHandler)
        self.reply = ANALYSIS_REPLY
        self.error = None
        self.stream_events = STREAM_EVENTS
        self.requests = []

    @property
    def url(self):
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


@pytest.fixture(autouse=True)
def no_stored_keys(monkeypatch):
    monkeypatch.delenv(keychain.ANYTHINGLLM_KEY_ENV, raising=False)
    monkeypatch.setattr(keychain, "get_secret", lambda service, **options: None)


@pytest.fixture
def server():
    fake = FakeAnythingLLM()
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    yield fake
    fake.shutdown()
    fake.server_close()


@pytest.fixture
def backend(server):
    return AnythingLLMBackend(server.url, "home", API_KEY)


def test_missing_url_names_the_variable():
    with pytest.raises(AiError, match="TOWER_BORESCOPE_ANYTHINGLLM_URL"):
        AnythingLLMBackend("", "home", API_KEY)


def test_list_workspaces_needs_a_valid_key(server):
    listed = AnythingLLMBackend.list_workspaces(f"{server.url}/", API_KEY)
    assert listed == [("home", "Home"), ("garage", "garage")]
    assert AnythingLLMBackend.list_workspaces(server.url, "wrong") == []
    assert AnythingLLMBackend.list_workspaces(server.url) == []
    assert AnythingLLMBackend.list_workspaces("", API_KEY) == []


def test_analyze_starts_a_session_with_image_and_schema(server, backend):
    first_session = backend.session
    analysis = backend.analyze(JPEG, "Analyze this scope view.")
    path, request, authorization = server.requests[-1]
    assert path == "/api/v1/workspace/home/chat" and authorization == f"Bearer {API_KEY}"
    assert backend.session != first_session and request["sessionId"] == backend.session
    image = request["attachments"][0]
    assert image["contentString"] == f"data:image/jpeg;base64,{to_base64(JPEG)}"
    assert request["message"].startswith(SYSTEM_PROMPT)
    assert JSON_REPLY_INSTRUCTION in request["message"]
    assert analysis.subject == "Vent duct" and backend.usage == Usage(90, 20)


def test_prose_reply_falls_back_and_error_field_raises(server, backend):
    server.reply = "It is a dryer vent, looks fine."
    assert backend.analyze(JPEG, "Analyze").subject == FALLBACK_SUBJECT
    with pytest.raises(AiError, match="did not return a usable answer"):
        backend.scale(JPEG, "scale")
    server.error = "model offline"
    with pytest.raises(AiError, match="AnythingLLM: model offline"):
        backend.analyze(JPEG, "Analyze")


def test_chat_continues_the_session_and_streams_until_close(server, backend):
    backend.analyze(JPEG, "Analyze")
    chunks = []
    history = [
        {"role": "user", "text": "Analyze", "jpeg": JPEG},
        {"role": "assistant", "text": "{}", "jpeg": None},
        {"role": "user", "text": "Is it leaking?", "jpeg": None},
    ]
    assert backend.chat(history, chunks.append) == "Dry joint."
    path, request, _authorization = server.requests[-1]
    assert chunks == ["Dry ", "joint."] and path.endswith("/home/stream-chat")
    assert request["message"] == "Is it leaking?" and "attachments" not in request
    assert request["sessionId"] == backend.session


def test_first_chat_turn_carries_the_system_prompt(server, backend):
    assert backend.summarize("Summarize the views") == "Dry joint."
    _path, request, _authorization = server.requests[-1]
    assert request["message"] == f"{CHAT_SYSTEM_PROMPT}\n\nSummarize the views"


def test_stream_error_event_raises(server, backend):
    server.stream_events = [{"type": "abort", "error": "context too long", "close": True}]
    with pytest.raises(AiError, match="context too long"):
        backend.summarize("hello")


def test_missing_key_or_workspace_raise(server):
    without_key = AnythingLLMBackend(server.url, "home")
    with pytest.raises(AiError, match="API key"):
        without_key.analyze(JPEG, "Analyze")
    without_workspace = AnythingLLMBackend(server.url, "", API_KEY)
    assert without_workspace.name == "AnythingLLM (no workspace)"
    with pytest.raises(AiError, match="workspace"):
        without_workspace.summarize("hello")


def test_check_lists_workspaces_and_detects_unknown_one(server, backend):
    assert backend.check() == f"AnythingLLM at {server.url}: workspaces home, garage"
    with pytest.raises(AiError, match="Workspace 'attic' not found"):
        AnythingLLMBackend(server.url, "attic", API_KEY).check()
