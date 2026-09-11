"""Tests for tower_borescope.ai.http against a small HTTP server on localhost."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tower_borescope.ai.base import AiError
from tower_borescope.ai.http import base_url, http_json, http_stream_lines

LOOPBACK = "127.0.0.1"


class RouteHandler(BaseHTTPRequestHandler):
    def _quiet(self, *args):
        return None

    def _send(self, status, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _get(self):
        routes = {
            "/json": (200, {"method": "GET", "probe": self.headers.get("X-Probe")}),
            "/error": (500, b"boom"),
            "/list": (200, [1, 2]),
            "/text": (200, b"not json"),
        }
        status, body = routes.get(self.path, (404, b"missing"))
        self._send(status, body)

    def _post(self):
        length = int(self.headers.get("Content-Length", 0))
        received = json.loads(self.rfile.read(length))
        if self.path == "/stream":
            self._send(200, b"line one\n\n   line two  \n")
        elif self.path == "/echo":
            content_type = self.headers.get("Content-Type")
            self._send(200, {"body": received, "content_type": content_type})
        else:
            self._send(404, b"no route")

    do_GET = _get
    do_POST = _post
    log_message = _quiet


@pytest.fixture
def server_url():
    httpd = ThreadingHTTPServer((LOOPBACK, 0), RouteHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def closed_url():
    probe = socket.socket()
    probe.bind((LOOPBACK, 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"http://{LOOPBACK}:{port}"


def test_get_sends_headers_and_decodes_object(server_url):
    reply = http_json(f"{server_url}/json", headers={"X-Probe": "yes"}, timeout=5)
    assert reply == {"method": "GET", "probe": "yes"}


def test_post_sends_json_body(server_url):
    reply = http_json(f"{server_url}/echo", {"a": [1, 2]}, timeout=5)
    assert reply == {"body": {"a": [1, 2]}, "content_type": "application/json"}


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/error", "HTTP 500 from .*/error: boom"),
        ("/list", "Expected a JSON object"),
        ("/text", "Invalid JSON"),
    ],
)
def test_bad_replies_raise_ai_error(server_url, path, message):
    with pytest.raises(AiError, match=message):
        http_json(f"{server_url}{path}", timeout=5)


def test_unreachable_server_raises_ai_error(closed_url):
    with pytest.raises(AiError, match="Could not reach"):
        http_json(f"{closed_url}/api/tags", timeout=2)
    with pytest.raises(AiError, match="Could not reach"):
        list(http_stream_lines(f"{closed_url}/stream", {}, timeout=2))


def test_stream_yields_stripped_non_blank_lines(server_url):
    lines = list(http_stream_lines(f"{server_url}/stream", {"go": True}, timeout=5))
    assert lines == ["line one", "line two"]


def test_stream_http_error_raises_ai_error(server_url):
    with pytest.raises(AiError, match="HTTP 404"):
        list(http_stream_lines(f"{server_url}/nowhere", {}, timeout=5))


def test_base_url_strips_and_requires_a_value():
    assert base_url("  http://ollama.invalid:11434/ ", "Ollama", "VAR") == (
        "http://ollama.invalid:11434"
    )
    with pytest.raises(AiError, match="TOWER_BORESCOPE_OLLAMA_URL"):
        base_url("   ", "Ollama", "TOWER_BORESCOPE_OLLAMA_URL")
