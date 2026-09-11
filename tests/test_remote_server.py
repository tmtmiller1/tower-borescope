"""Tests for tower_borescope.remote.server: endpoints, streaming and address lookup."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
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


def _request(port, method, path):
    connection = http.client.HTTPConnection(HOST, port, timeout=TIMEOUT)
    connection.request(method, path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response, body


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


def test_page_served_at_root(remote):
    assert remote.port > 0
    response, body = _request(remote.port, "GET", "/")
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert b"<title>Tower Borescope</title>" in body


def test_frame_endpoint_returns_latest_jpeg(remote):
    response, body = _request(remote.port, "GET", "/frame.jpg")
    assert response.status == 200
    assert body == b""
    remote.publish(textured_frame(320, 240))
    _, body = _request(remote.port, "GET", "/frame.jpg")
    assert jpeg_size(body) == (320, 240)


def test_stream_sends_jpeg_part_after_publish(remote):
    remote.publish(textured_frame(320, 240))
    connection = http.client.HTTPConnection(HOST, remote.port, timeout=TIMEOUT)
    connection.request("GET", "/stream")
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


def test_stop_ends_open_streams(callbacks):
    instance = RemoteServer(callbacks.snapshot, callbacks.record, port=0)
    instance.start()
    connection = http.client.HTTPConnection(HOST, instance.port, timeout=TIMEOUT)
    connection.request("GET", "/stream")
    response = connection.getresponse()
    assert _wait_until(lambda: instance.viewers == 1)
    instance.stop()
    assert _wait_until(lambda: instance.viewers == 0)
    response.close()
    connection.close()


def test_snapshot_and_record_invoke_callbacks(remote, callbacks):
    response, body = _request(remote.port, "POST", "/snapshot")
    assert response.status == 200
    assert json.loads(body) == {"ok": True}
    assert callbacks.snapshots == 1
    _, body = _request(remote.port, "POST", "/record")
    assert json.loads(body) == {"recording": True}
    _, body = _request(remote.port, "POST", "/record")
    assert json.loads(body) == {"recording": False}
    response, _ = _request(remote.port, "POST", "/unknown")
    assert response.status == 404


def test_publish_is_rate_limited_without_viewers(remote):
    remote.publish(textured_frame(320, 240))
    _, first = _request(remote.port, "GET", "/frame.jpg")
    remote.publish(textured_frame(320, 240, seed=5))
    _, second = _request(remote.port, "GET", "/frame.jpg")
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
        finally:
            second.stop()
    finally:
        first.stop()


def test_url_uses_lan_address(remote, monkeypatch):
    monkeypatch.setattr(server, "lan_ip", lambda: "10.0.0.5")
    assert remote.url == f"http://10.0.0.5:{remote.port}/"


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
