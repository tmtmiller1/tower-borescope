"""Tests for tower_borescope.ai.ollama against a fake Ollama server on localhost.

The ``live_ai`` test sends a synthetic frame to the local Ollama named by
``TOWER_BORESCOPE_OLLAMA_URL`` and runs only with ``--live-ai``.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from synthetic import inspection_scene, textured_frame
from tower_borescope.ai.base import AiError, Usage
from tower_borescope.ai.conversation import Conversation
from tower_borescope.ai.images import encode_for_model, to_base64
from tower_borescope.ai.ollama import (
    PULL_HINT,
    RECOMMENDED_MODEL,
    OllamaBackend,
    looks_like_vision_model,
    model_capabilities,
    resolve_model,
)
from tower_borescope.ai.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT
from tower_borescope.ai.schema import (
    CONDITIONS,
    CONFIDENCES,
    FALLBACK_SUBJECT,
    SEVERITIES,
    Analysis,
    ScaleEstimate,
)
from tower_borescope.config import env_value
from tower_borescope.jpeg import encode_jpeg

JPEG = encode_jpeg(textured_frame(160, 120))
ANALYSIS_JSON = json.dumps(
    {
        "subject": "Copper elbow",
        "description": "A soldered copper elbow.",
        "condition": "Good overall",
        "issues": [{"label": "Flux residue", "severity": "minor", "note": "Green."}],
        "actions": ["Wipe the joint"],
        "parts_and_tools": [],
        "safety": [],
        "confidence": "high",
        "questions": [],
    }
)
SCALE_JSON = json.dumps(
    {
        "found": True,
        "reference_object": "M8 nut",
        "standard_size_mm": 13.0,
        "span": [0.2, 0.5, 0.6, 0.5],
        "confidence": "medium",
        "reasoning": "Hex across flats.",
    }
)


class OllamaHandler(BaseHTTPRequestHandler):
    def _quiet(self, *args):
        return None

    def _send_json(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _get(self):
        models = [{"name": name} for name in self.server.models]
        self._send_json({"models": models})

    def _post(self):
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length))
        if self.path == "/api/show":
            self._show(request["model"])
            return
        self.server.requests.append(request)
        if request.get("stream"):
            self._stream()
            return
        message = {"role": "assistant", "content": self.server.reply}
        self._send_json({"message": message, "prompt_eval_count": 120, "eval_count": 30})

    def _show(self, name):
        self.server.shows.append(name)
        capabilities = self.server.capabilities.get(name)
        if capabilities is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json({"capabilities": capabilities})

    def _stream(self):
        self.send_response(200)
        self.end_headers()
        events = [
            {"message": {"content": "Looks "}, "done": False},
            {"message": {"content": "dry."}, "done": False},
            {
                "message": {"content": ""},
                "done": True,
                "prompt_eval_count": 50,
                "eval_count": 2,
            },
        ]
        lines = [json.dumps(events[0]), "not json", *map(json.dumps, events[1:])]
        self.wfile.write("\n".join(lines).encode() + b"\n")

    do_GET = _get
    do_POST = _post
    log_message = _quiet


class FakeOllama(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), OllamaHandler)
        self.models = ["bge-m3:latest", RECOMMENDED_MODEL, "qwen3-vl:4b", "llava:7b"]
        self.capabilities = {
            "bge-m3:latest": ["embedding"],
            RECOMMENDED_MODEL: ["completion", "vision"],
            "qwen3-vl:4b": ["completion", "vision", "thinking"],
            "llava:7b": ["completion", "vision"],
        }
        self.reply = ANALYSIS_JSON
        self.requests = []
        self.shows = []

    @property
    def url(self):
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


@pytest.fixture
def ollama():
    server = FakeOllama()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("qwen3-vl:4b", True),
        ("llava:13b", True),
        ("MiniCPM-V:8b", True),
        ("gemma3:4b", True),
        ("bge-m3:latest", False),
        ("llama3.1:8b", False),
    ],
)
def test_looks_like_vision_model(name, expected):
    assert looks_like_vision_model(name) is expected


def test_list_models(ollama):
    assert OllamaBackend.list_models(f"{ollama.url}/") == ollama.models
    assert OllamaBackend.list_models("  ") == []


def test_list_models_unreachable_is_empty(ollama):
    url = ollama.url
    ollama.shutdown()
    ollama.server_close()
    assert OllamaBackend.list_models(url) == []


def test_resolve_model_prefers_configured_then_recommended(ollama):
    assert resolve_model(ollama.url, "") == RECOMMENDED_MODEL
    assert resolve_model(ollama.url, "llava") == "llava"
    assert resolve_model(ollama.url, "llava:7b") == "llava:7b"
    assert resolve_model(ollama.url, "qwen3-vl:4b") == "qwen3-vl:4b"
    assert resolve_model(ollama.url, "missing:1b") == RECOMMENDED_MODEL
    assert ollama.shows == []


def test_resolve_model_passes_over_thinking_variants(ollama):
    ollama.models = ["qwen3-vl:4b", "llava:7b"]
    assert resolve_model(ollama.url, "") == "llava:7b"
    ollama.models = ["bge-m3:latest", "qwen3-vl:4b"]
    assert resolve_model(ollama.url, "") == "qwen3-vl:4b"
    ollama.models = ["qwen3-vl:4b", "moondream:latest"]
    assert resolve_model(ollama.url, "") == "moondream:latest"


def test_model_capabilities(ollama):
    expected = {"completion", "vision", "thinking"}
    assert model_capabilities(f"{ollama.url}/", "qwen3-vl:4b") == expected
    assert model_capabilities(ollama.url, "unknown:1b") == frozenset()
    url = ollama.url
    ollama.shutdown()
    ollama.server_close()
    assert model_capabilities(url, "qwen3-vl:4b") == frozenset()


def test_resolve_model_without_vision_models(ollama):
    ollama.models = ["bge-m3:latest"]
    assert resolve_model(ollama.url, "") == "bge-m3:latest"
    assert resolve_model(ollama.url, "custom") == "custom"
    ollama.models = []
    assert resolve_model(ollama.url, "") == ""


def test_missing_url_names_the_variable():
    with pytest.raises(AiError, match="TOWER_BORESCOPE_OLLAMA_URL"):
        OllamaBackend("  ")


def test_backend_without_models_raises_and_flags_non_vision(ollama):
    ollama.models = ["bge-m3:latest"]
    assert OllamaBackend(ollama.url).name == "Ollama (bge-m3:latest, not a vision model)"
    ollama.models = []
    with pytest.raises(AiError, match="no models") as caught:
        OllamaBackend(ollama.url)
    assert PULL_HINT in str(caught.value)
    assert PULL_HINT == "ollama pull qwen3-vl:4b-instruct"


def test_backend_name_flags_thinking_models(ollama):
    backend = OllamaBackend(ollama.url, "qwen3-vl:4b")
    assert backend.model == "qwen3-vl:4b"
    assert backend.name == "Ollama (qwen3-vl:4b, thinks before answering)"


def test_analyze_sends_schema_image_and_no_token_cap(ollama):
    backend = OllamaBackend(f"{ollama.url}/")
    analysis = backend.analyze(JPEG, "Analyze this scope view.")
    request = ollama.requests[-1]
    assert request["format"] == Analysis.model_json_schema()
    assert request["think"] is False and request["stream"] is False
    assert "num_predict" not in request["options"]
    assert request["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert request["messages"][1]["images"] == [to_base64(JPEG)]
    assert analysis.subject == "Copper elbow" and backend.usage == Usage(120, 30)
    assert backend.name == "Ollama (qwen3-vl:4b-instruct)"


def test_analyze_parses_fenced_reply_and_falls_back_on_prose(ollama):
    backend = OllamaBackend(ollama.url, "llava:7b")
    ollama.reply = f"Here you go:\n```json\n{ANALYSIS_JSON}\n```"
    assert backend.analyze(JPEG, "Analyze").subject == "Copper elbow"
    ollama.reply = "I think it is a pipe."
    assert backend.analyze(JPEG, "Analyze").subject == FALLBACK_SUBJECT


def test_scale_parses_and_rejects_unusable_reply(ollama):
    backend = OllamaBackend(ollama.url)
    ollama.reply = SCALE_JSON
    assert backend.scale(JPEG, "scale").standard_size_mm == 13.0
    assert ollama.requests[-1]["format"] == ScaleEstimate.model_json_schema()
    ollama.reply = "no idea"
    with pytest.raises(AiError, match="did not return a usable answer"):
        backend.scale(JPEG, "scale")


def test_chat_streams_chunks_and_counts_usage(ollama):
    backend = OllamaBackend(ollama.url)
    chunks = []
    turn = {"role": "user", "text": "Leaking?", "jpeg": None}
    assert backend.chat([turn], chunks.append) == "Looks dry."
    request = ollama.requests[-1]
    assert chunks == ["Looks ", "dry."]
    assert request["stream"] is True and request["think"] is False
    assert request["messages"][0]["content"] == CHAT_SYSTEM_PROMPT
    assert "images" not in request["messages"][1]
    assert backend.usage == Usage(50, 2)


def test_check_reports_models_and_detects_missing_model(ollama):
    backend = OllamaBackend(ollama.url)
    expected = "qwen3-vl:4b-instruct available (4 model(s) installed)"
    assert backend.check().endswith(expected)
    ollama.models = ["qwen3-vl:8b"]
    assert "available" in backend.check()
    ollama.models = ["llava:7b"]
    with pytest.raises(AiError, match="not in Ollama. Available: llava:7b"):
        backend.check()
    ollama.models = []
    with pytest.raises(AiError, match="no models"):
        backend.check()


@pytest.mark.live_ai
def test_live_ollama_returns_normalized_analysis():
    url = env_value("OLLAMA_URL")
    if not url or not OllamaBackend.list_models(url):
        pytest.skip("TOWER_BORESCOPE_OLLAMA_URL is unset or Ollama is unreachable")
    backend = OllamaBackend(url)
    jpeg = encode_for_model(inspection_scene(), backend.max_image_width)
    analysis = Conversation(backend, jpeg, "inside a wall cavity").analyze()
    assert analysis.subject.strip()
    assert analysis.condition in CONDITIONS and analysis.confidence in CONFIDENCES
    assert all(issue.severity in SEVERITIES for issue in analysis.issues)
