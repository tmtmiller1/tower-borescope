"""Tests for tower_borescope.remote.server: the access key, endpoints, streaming and
address lookup."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import string
import subprocess
import time

import pytest

from synthetic import textured_frame
from tower_borescope.jpeg import jpeg_size
from tower_borescope.remote import server
from tower_borescope.remote.server import (
    DEFAULT_PORT,
    PORT_ATTEMPTS,
    RemoteServer,
    lan_ip,
)

HOST = "127.0.0.1"
TIMEOUT = 5.0
COOKIE_ATTRIBUTES = "HttpOnly; SameSite=Strict; Path=/"
KEY_ALPHABET = set(string.ascii_letters + string.digits + "-_")
ROUTES = [
    ("GET", "/"),
    ("GET", "/stream"),
    ("GET", "/frame.jpg"),
    ("POST", "/snapshot"),
    ("POST", "/record"),
    ("GET", "/missing"),
    ("POST", "/missing"),
]
OPEN_ROUTES = [
    ("GET", "/", 200),
    ("GET", "/frame.jpg", 200),
    ("POST", "/snapshot", 200),
    ("POST", "/record", 200),
    ("GET", "/stream/extra", 404),
    ("POST", "/snapshots", 404),
]


class Callbacks:
    """Counts button presses and toggles the recording state."""

    def __init__(self):
        self.snapshots = 0
        self.recording = False

    def snapshot(self):
        self.snapshots += 1

    def record(self):
        self.recording = not self.recording
        return self.recording


@pytest.fixture
def callbacks():
    return Callbacks()


@pytest.fixture
def remote(callbacks):
    instance = RemoteServer(callbacks.snapshot, callbacks.record, port=0)
    instance.start()
    yield instance
    instance.stop()


def _request(port, method, target, headers=None):
    connection = http.client.HTTPConnection(HOST, port, timeout=TIMEOUT)
    connection.request(method, target, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response, body


def _keyed(remote, target):
    return f"{target}?key={remote.access_key}"


def _page_cookie(remote):
    response, _ = _request(remote.port, "GET", _keyed(remote, "/"))
    return response.getheader("Set-Cookie").split(";", 1)[0]


def _wait_until(predicate, action=None):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if predicate():
            return True
        if action is not None:
            action()
        time.sleep(0.1)
    return predicate()


def _read_part(response):
    assert response.readline() == b"--frame\r\n"
    headers = {}
    line = response.readline()
    while line != b"\r\n":
        name, value = line.decode().split(":", 1)
        headers[name.strip().lower()] = value.strip()
        line = response.readline()
    assert headers["content-type"] == "image/jpeg"
    return response.read(int(headers["content-length"]))


def _assert_streams(remote, target, headers=None):
    remote.publish(textured_frame(320, 240))
    connection = http.client.HTTPConnection(HOST, remote.port, timeout=TIMEOUT)
    connection.request("GET", target, headers=headers or {})
    response = connection.getresponse()
    assert response.status == 200
    assert "multipart/x-mixed-replace" in response.getheader("Content-Type")
    part = _read_part(response)
    assert part.startswith(b"\xff\xd8")
    assert jpeg_size(part) == (320, 240)
    assert remote.viewers == 1
    response.close()
    connection.close()
    frame = textured_frame(320, 240, seed=1)
    assert _wait_until(lambda: remote.viewers == 0, lambda: remote.publish(frame))


def _assert_refused(remote, callbacks, response, body):
    assert response.status == 403
    assert response.getheader("Content-Type") == "text/plain"
    assert body == b"forbidden"
    assert response.getheader("Set-Cookie") is None
    assert callbacks.snapshots == 0 and not callbacks.recording
    assert remote.viewers == 0


def test_page_served_at_root(remote):
    assert remote.port > 0
    response, body = _request(remote.port, "GET", _keyed(remote, "/"))
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert b"<title>Tower Borescope</title>" in body
    assert remote.access_key.encode() not in body


def test_page_sets_an_access_cookie_named_for_the_port(remote):
    response, _ = _request(remote.port, "GET", _keyed(remote, "/"))
    expected = f"borescope_key_{remote.port}={remote.access_key}; {COOKIE_ATTRIBUTES}"
    assert response.getheader("Set-Cookie") == expected


def test_access_key_is_long_and_url_safe(remote):
    assert len(remote.access_key) >= 24
    assert set(remote.access_key) <= KEY_ALPHABET


@pytest.mark.parametrize(("method", "target"), ROUTES)
def test_request_without_key_is_refused(remote, callbacks, method, target):
    response, body = _request(remote.port, method, target)
    _assert_refused(remote, callbacks, response, body)


@pytest.mark.parametrize(("method", "target"), ROUTES)
def test_request_with_wrong_key_is_refused(remote, callbacks, method, target):
    key = remote.access_key
    near = key[:-1] + ("B" if key.endswith("A") else "A")
    name = f"borescope_key_{remote.port}"
    attempts = [
        (f"{target}?key={near}", {}),
        (f"{target}?key=", {}),
        (f"{target}?key=%C3%A9", {}),
        (f"{target}?other={key}", {}),
        (target, {"Cookie": f"{name}={near}"}),
        (target, {"Cookie": f"{name}="}),
        (target, {"Cookie": f"borescope_key_1={key}"}),
    ]
    for request_target, headers in attempts:
        response, body = _request(remote.port, method, request_target, headers)
        _assert_refused(remote, callbacks, response, body)
        assert key.encode() not in body


def test_unparseable_target_is_refused(remote, callbacks):
    target = f"http://[bad/snapshot?key={remote.access_key}"
    response, body = _request(remote.port, "POST", target, {"Host": HOST})
    _assert_refused(remote, callbacks, response, body)


@pytest.mark.parametrize(("method", "target", "status"), OPEN_ROUTES)
def test_query_key_opens_every_route(remote, method, target, status):
    response, _ = _request(remote.port, method, _keyed(remote, target))
    assert response.status == status


@pytest.mark.parametrize(("method", "target", "status"), OPEN_ROUTES)
def test_page_cookie_opens_every_route(remote, method, target, status):
    cookie = f"theme=dark; {_page_cookie(remote)}; lang=en"
    response, _ = _request(remote.port, method, target, {"Cookie": cookie})
    assert response.status == status


def test_frame_endpoint_returns_latest_jpeg(remote):
    response, body = _request(remote.port, "GET", _keyed(remote, "/frame.jpg"))
    assert response.status == 200
    assert body == b""
    remote.publish(textured_frame(320, 240))
    _, body = _request(remote.port, "GET", _keyed(remote, "/frame.jpg"))
    assert jpeg_size(body) == (320, 240)


def test_stream_sends_jpeg_part_after_publish(remote):
    _assert_streams(remote, _keyed(remote, "/stream"))


def test_stream_accepts_the_page_cookie(remote):
    _assert_streams(remote, "/stream?1712345678", {"Cookie": _page_cookie(remote)})


def test_stop_ends_open_streams(callbacks):
    instance = RemoteServer(callbacks.snapshot, callbacks.record, port=0)
    instance.start()
    connection = http.client.HTTPConnection(HOST, instance.port, timeout=TIMEOUT)
    connection.request("GET", _keyed(instance, "/stream"))
    response = connection.getresponse()
    assert _wait_until(lambda: instance.viewers == 1)
    instance.stop()
    assert _wait_until(lambda: instance.viewers == 0)
    response.close()
    connection.close()


def test_snapshot_and_record_invoke_callbacks(remote, callbacks):
    response, body = _request(remote.port, "POST", _keyed(remote, "/snapshot"))
    assert response.status == 200
    assert json.loads(body) == {"ok": True}
    assert callbacks.snapshots == 1
    _, body = _request(remote.port, "POST", _keyed(remote, "/record"))
    assert json.loads(body) == {"recording": True}
    _, body = _request(remote.port, "POST", _keyed(remote, "/record"))
    assert json.loads(body) == {"recording": False}
    response, _ = _request(remote.port, "POST", _keyed(remote, "/unknown"))
    assert response.status == 404
    assert callbacks.snapshots == 1


def test_requests_write_no_log_lines(remote, capsys):
    _request(remote.port, "GET", _keyed(remote, "/"))
    _request(remote.port, "GET", "/frame.jpg?key=wrong")
    captured = capsys.readouterr()
    assert remote.access_key not in captured.out + captured.err
    assert "GET" not in captured.err


def test_publish_is_rate_limited_without_viewers(remote):
    remote.publish(textured_frame(320, 240))
    _, first = _request(remote.port, "GET", _keyed(remote, "/frame.jpg"))
    remote.publish(textured_frame(320, 240, seed=5))
    _, second = _request(remote.port, "GET", _keyed(remote, "/frame.jpg"))
    assert first == second


def test_stop_releases_the_port(callbacks):
    instance = RemoteServer(callbacks.snapshot, callbacks.record, port=0)
    instance.start()
    port = instance.port
    instance.stop()
    instance.stop()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((HOST, port), timeout=TIMEOUT).close()
    again = RemoteServer(callbacks.snapshot, callbacks.record, port=port)
    again.start()
    assert again.port == port
    again.stop()


def test_url_has_no_key_while_stopped(callbacks, monkeypatch):
    monkeypatch.setattr(server, "lan_ip", lambda: "10.0.0.5")
    instance = RemoteServer(callbacks.snapshot, callbacks.record, port=0)
    assert instance.access_key is None
    assert instance.url == "http://10.0.0.5:0/"
    instance.start()
    key = instance.access_key
    assert instance.url == f"http://10.0.0.5:{instance.port}/?key={key}"
    instance.stop()
    assert instance.access_key is None
    assert instance.url == f"http://10.0.0.5:{instance.port}/"


def test_restart_creates_a_new_key(callbacks, monkeypatch):
    monkeypatch.setattr(server, "lan_ip", lambda: "10.0.0.5")
    instance = RemoteServer(callbacks.snapshot, callbacks.record, port=0)
    instance.start()
    first = instance.access_key
    instance.stop()
    instance.start()
    try:
        second = instance.access_key
        assert second is not None and second != first
        assert instance.url == f"http://10.0.0.5:{instance.port}/?key={second}"
        response, _ = _request(instance.port, "GET", f"/?key={first}")
        assert response.status == 403
        response, _ = _request(instance.port, "GET", f"/?key={second}")
        assert response.status == 200
    finally:
        instance.stop()


def test_failed_start_creates_no_key(callbacks, remote):
    busy = RemoteServer(callbacks.snapshot, callbacks.record, port=remote.port)
    with pytest.raises(OSError):
        busy.start()
    assert busy.access_key is None


def test_default_port_scans_upward(callbacks):
    first = RemoteServer(callbacks.snapshot, callbacks.record)
    second = RemoteServer(callbacks.snapshot, callbacks.record)
    first.start()
    try:
        second.start()
        try:
            ports = range(DEFAULT_PORT, DEFAULT_PORT + PORT_ATTEMPTS)
            assert first.port in ports
            assert second.port in ports
            assert first.port != second.port
            assert first.access_key != second.access_key
        finally:
            second.stop()
    finally:
        first.stop()


def test_url_uses_lan_address_and_key(remote, monkeypatch):
    monkeypatch.setattr(server, "lan_ip", lambda: "10.0.0.5")
    assert remote.url == f"http://10.0.0.5:{remote.port}/?key={remote.access_key}"


def test_lan_ip_prefers_interface_address(monkeypatch):
    def fake_run(command, **kwargs):
        address = {"en0": "169.254.10.20\n", "en1": "192.168.1.50\n"}.get(command[2], "")
        return subprocess.CompletedProcess(command, 0, stdout=address, stderr="")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    assert lan_ip() == "192.168.1.50"


def test_lan_ip_falls_back_to_route_lookup(monkeypatch):
    def failing_run(command, **kwargs):
        raise OSError("ipconfig unavailable")

    monkeypatch.setattr(server.subprocess, "run", failing_run)
    address = ipaddress.ip_address(lan_ip())
    assert address.version == 4
    assert not address.is_link_local


def test_lan_ip_without_route_is_loopback(monkeypatch):
    class Unrouted:
        def __init__(self, *args):
            pass

        def connect(self, address):
            raise OSError("network is unreachable")

        def close(self):
            pass

    def timed_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 2.0)

    monkeypatch.setattr(server.subprocess, "run", timed_out)
    monkeypatch.setattr(server.socket, "socket", Unrouted)
    assert lan_ip() == HOST
