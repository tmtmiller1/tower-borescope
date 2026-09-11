"""Phone monitor: the live view served on the local network as an MJPEG stream.

The pipeline calls :meth:`RemoteServer.publish` with each processed frame. A browser on
the same network opens ``http://<address>:<port>/`` and sees the picture with snapshot
and record buttons.
"""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

from tower_borescope.image_types import BgrImage
from tower_borescope.jpeg import encode_jpeg
from tower_borescope.remote.page import PAGE_HTML

DEFAULT_PORT = 8765
PORT_ATTEMPTS = 10
STREAM_FPS = 12
IDLE_PUBLISH_SECONDS = 1.0
JPEG_QUALITY = 72
VIEWER_WAIT_SECONDS = 2.0
STOP_JOIN_SECONDS = 5.0
IPCONFIG_TIMEOUT_SECONDS = 2.0
BIND_ADDRESS = "0.0.0.0"
LOOPBACK_ADDRESS = "127.0.0.1"
ROUTE_PROBE_ADDRESS = "192.168.255.255"
LINK_LOCAL_PREFIX = "169.254"
INTERFACES = ("en0", "en1", "en2", "en3")
BOUNDARY = "frame"


def _interface_address(interface: str) -> str | None:
    """IPv4 address of one network interface, skipping link-local addresses."""
    command = ["ipconfig", "getifaddr", interface]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=IPCONFIG_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    address = completed.stdout.strip()
    if not address or address.startswith(LINK_LOCAL_PREFIX):
        return None
    return address


def _route_address() -> str:
    """Local address of the default route, or the loopback address without one."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connecting a UDP socket sends no packets; it only selects a route.
        probe.connect((ROUTE_PROBE_ADDRESS, 1))
        return str(probe.getsockname()[0])
    except OSError:
        return LOOPBACK_ADDRESS
    finally:
        probe.close()


def lan_ip() -> str:
    """Wi-Fi or Ethernet address of this machine, which a phone on the network reaches.

    The ``en0`` to ``en3`` interfaces come first because a VPN can own the default
    route; the route lookup is the fallback.

    Returns:
        A dotted IPv4 address.
    """
    for interface in INTERFACES:
        address = _interface_address(interface)
        if address is not None:
            return address
    return _route_address()


class _FrameHub:
    """Latest encoded frame, shared by the publisher and the streaming handlers."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self.latest: bytes | None = None
        self.latest_at = 0.0
        self.viewers = 0
        self.closed = False

    def should_publish(self, now: float) -> bool:
        """Rate limit: the stream rate with viewers, one frame a second without."""
        elapsed = now - self.latest_at
        if elapsed < 1.0 / STREAM_FPS:
            return False
        return self.viewers > 0 or elapsed >= IDLE_PUBLISH_SECONDS

    def put(self, data: bytes, now: float) -> None:
        """Store a frame and wake every waiting stream."""
        with self._condition:
            self.latest = data
            self.latest_at = now
            self._condition.notify_all()

    def wait_newer(self, last: float) -> tuple[bytes | None, float]:
        """Latest frame once one newer than ``last`` arrives or the wait times out."""
        with self._condition:
            self._condition.wait_for(
                lambda: self.closed or self.latest_at > last, timeout=VIEWER_WAIT_SECONDS
            )
            return self.latest, self.latest_at

    def add_viewers(self, delta: int) -> None:
        """Adjust the open stream count."""
        with self._condition:
            self.viewers += delta

    def close(self) -> None:
        """End every stream loop."""
        with self._condition:
            self.closed = True
            self._condition.notify_all()


@dataclass(frozen=True, slots=True)
class _Routes:
    """State and callbacks the request handler serves."""

    hub: _FrameHub
    on_snapshot: Callable[[], object]
    on_record: Callable[[], bool]


class _RemoteHttpServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying the routes for its handlers."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], routes: _Routes) -> None:
        super().__init__(address, _RemoteHandler)
        self.routes = routes


class _RemoteHandler(BaseHTTPRequestHandler):
    """Serves the page, the MJPEG stream, single frames and the button actions."""

    protocol_version = "HTTP/1.1"

    def _routes(self) -> _Routes:
        """Routes of the server that accepted this request."""
        return cast(_RemoteHttpServer, self.server).routes

    def _log_message(self, format: str, *args: Any) -> None:
        """Discard access log lines."""

    def _handle_get(self) -> None:
        """Serve ``/stream``, ``/frame.jpg`` or the page."""
        if self.path.startswith("/stream"):
            self._stream()
        elif self.path.startswith("/frame.jpg"):
            self._send(HTTPStatus.OK, "image/jpeg", self._routes().hub.latest or b"")
        else:
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", PAGE_HTML.encode())

    def _handle_post(self) -> None:
        """Run the snapshot or record callback."""
        routes = self._routes()
        if self.path.startswith("/snapshot"):
            routes.on_snapshot()
            self._send_json({"ok": True})
        elif self.path.startswith("/record"):
            self._send_json({"recording": bool(routes.on_record())})
        else:
            self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found")

    do_GET = _handle_get
    do_POST = _handle_post
    log_message = _log_message

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        """Send a complete uncached response."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, bool]) -> None:
        """Send a JSON object."""
        self._send(HTTPStatus.OK, "application/json", json.dumps(payload).encode())

    def _stream(self) -> None:
        """Send frames as multipart JPEG parts until the viewer disconnects."""
        hub = self._routes().hub
        self.close_connection = True
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        hub.add_viewers(1)
        try:
            with contextlib.suppress(OSError):
                self._stream_frames(hub)
        finally:
            hub.add_viewers(-1)

    def _stream_frames(self, hub: _FrameHub) -> None:
        """Write each new frame, repeating the latest after a quiet interval."""
        last = 0.0
        while not hub.closed:
            data, last = hub.wait_newer(last)
            if data is None or hub.closed:
                continue
            header = f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
            header += f"Content-Length: {len(data)}\r\n\r\n"
            self.wfile.write(header.encode())
            self.wfile.write(data)
            self.wfile.write(b"\r\n")
            self.wfile.flush()


def _bind(routes: _Routes, first_port: int, attempts: int) -> _RemoteHttpServer:
    """Bind the first free port of ``attempts`` ports starting at ``first_port``."""
    last_error: OSError | None = None
    for port in range(first_port, first_port + attempts):
        try:
            return _RemoteHttpServer((BIND_ADDRESS, port), routes)
        except OSError as error:
            last_error = error
    last_port = first_port + attempts - 1
    raise OSError(f"no free port between {first_port} and {last_port}: {last_error}")


class RemoteServer:
    """HTTP server streaming processed frames to browsers on the local network.

    Attributes:
        on_snapshot: Called when a viewer presses Snapshot.
        on_record: Called when a viewer presses Record; returns True while recording.
        port: Listening port once started; the requested port before that.
    """

    def __init__(
        self,
        on_snapshot: Callable[[], object],
        on_record: Callable[[], bool],
        port: int | None = None,
    ) -> None:
        """Configure the server without binding a socket.

        Args:
            on_snapshot: Snapshot callback, run on a request thread.
            on_record: Record toggle callback, run on a request thread.
            port: Port to bind. None tries 8765 and the nine ports above it; 0 lets
                the operating system choose.
        """
        self.on_snapshot = on_snapshot
        self.on_record = on_record
        self.port = DEFAULT_PORT if port is None else port
        self._attempts = PORT_ATTEMPTS if port is None else 1
        self._hub = _FrameHub()
        self._server: _RemoteHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def viewers(self) -> int:
        """Number of open ``/stream`` connections."""
        return self._hub.viewers

    @property
    def url(self) -> str:
        """Address a phone on the local network opens."""
        return f"http://{lan_ip()}:{self.port}/"

    def start(self) -> None:
        """Bind the port and serve requests on a background thread.

        Raises:
            OSError: When no port in the allowed range is free.
        """
        if self._server is not None:
            return
        self._hub = _FrameHub()
        routes = _Routes(self._hub, self.on_snapshot, self.on_record)
        server = _bind(routes, self.port, self._attempts)
        self._server = server
        self.port = int(server.socket.getsockname()[1])
        self._thread = threading.Thread(
            target=server.serve_forever, name="remote-server", daemon=True
        )
        self._thread.start()

    def publish(self, image: BgrImage) -> None:
        """Encode a processed frame for viewers, limited to the stream frame rate.

        Args:
            image: Processed BGR frame.
        """
        now = time.monotonic()
        if not self._hub.should_publish(now):
            return
        try:
            data = encode_jpeg(image, JPEG_QUALITY)
        except ValueError:
            return
        self._hub.put(data, now)

    def stop(self) -> None:
        """End open streams, stop serving and close the listening socket."""
        server = self._server
        if server is None:
            return
        self._server = None
        self._hub.close()
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=STOP_JOIN_SECONDS)
            self._thread = None
