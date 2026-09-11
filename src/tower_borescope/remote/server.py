"""Phone monitor: the live view served on the local network as an MJPEG stream.

The pipeline calls :meth:`RemoteServer.publish` with each processed frame. A browser on
the same network opens ``http://<address>:<port>/?key=<key>`` and sees the picture with
snapshot and record buttons. Every route answers 403 unless the request carries the
access key of the current server start, in the query or in the cookie the page sets.
"""

from __future__ import annotations

import contextlib
import json
import socket
import socketserver
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
from tower_borescope.remote import access
from tower_borescope.remote.hub import FrameHub
from tower_borescope.remote.page import PAGE_HTML

DEFAULT_PORT = 8765
PORT_ATTEMPTS = 10
JPEG_QUALITY = 72
STOP_JOIN_SECONDS = 5.0
IPCONFIG_TIMEOUT_SECONDS = 2.0
BIND_ADDRESS = "0.0.0.0"
LOOPBACK_ADDRESS = "127.0.0.1"
ROUTE_PROBE_ADDRESS = "192.168.255.255"
LINK_LOCAL_PREFIX = "169.254"
INTERFACES = ("en0", "en1", "en2", "en3")
BOUNDARY = "frame"
PAGE_PATH = "/"
STREAM_PATH = "/stream"
FRAME_PATH = "/frame.jpg"
SNAPSHOT_PATH = "/snapshot"
RECORD_PATH = "/record"
PLAIN_TEXT = "text/plain"
FORBIDDEN_BODY = b"forbidden"
NOT_FOUND_BODY = b"not found"


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


@dataclass(frozen=True, slots=True)
class _Routes:
    """State and callbacks the request handler serves."""

    hub: FrameHub
    on_snapshot: Callable[[], object]
    on_record: Callable[[], bool]
    key: str


class _RemoteHttpServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying the routes and the access cookie name."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], routes: _Routes) -> None:
        super().__init__(address, _RemoteHandler)
        self.routes = routes
        self.cookie_name = access.cookie_name(self.server_port)

    def server_bind(self) -> None:
        """Bind the socket without the host name lookup ``HTTPServer`` performs.

        ``HTTPServer.server_bind`` resolves the bound address with ``socket.getfqdn``
        only to fill ``server_name``, and on macOS that reverse lookup can wait on
        mDNS without end. The bound address serves as the name instead.
        """
        socketserver.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class _RemoteHandler(BaseHTTPRequestHandler):
    """Serves the page, MJPEG stream, frames and buttons to requests with the key."""

    protocol_version = "HTTP/1.1"

    def _http_server(self) -> _RemoteHttpServer:
        """Server that accepted this request."""
        return cast(_RemoteHttpServer, self.server)

    def _routes(self) -> _Routes:
        """Routes of the server that accepted this request."""
        return self._http_server().routes

    def _log_message(self, format: str, *args: Any) -> None:
        """Discard access log lines, which would otherwise record the key query."""

    def _authorized_path(self) -> str | None:
        """Request path when the ``key`` query or the access cookie holds the key.

        Returns None after answering 403, so the request reaches no route.
        """
        target = access.parse_target(self.path)
        key = self._routes().key
        cookies = "; ".join(self.headers.get_all("Cookie") or [])
        cookie = access.cookie_key(cookies, self._http_server().cookie_name)
        if access.key_matches(target.key, key) or access.key_matches(cookie, key):
            return target.path
        self._send(HTTPStatus.FORBIDDEN, PLAIN_TEXT, FORBIDDEN_BODY)
        return None

    def _handle_get(self) -> None:
        """Serve the page, ``/stream`` or ``/frame.jpg`` to a request with the key."""
        path = self._authorized_path()
        if path is None:
            return
        if path == PAGE_PATH:
            self._send_page()
        elif path == STREAM_PATH:
            self._stream()
        elif path == FRAME_PATH:
            self._send(HTTPStatus.OK, "image/jpeg", self._routes().hub.latest or b"")
        else:
            self._send(HTTPStatus.NOT_FOUND, PLAIN_TEXT, NOT_FOUND_BODY)

    def _handle_post(self) -> None:
        """Run the snapshot or record callback for a request with the key."""
        path = self._authorized_path()
        if path is None:
            return
        routes = self._routes()
        if path == SNAPSHOT_PATH:
            routes.on_snapshot()
            self._send_json({"ok": True})
        elif path == RECORD_PATH:
            self._send_json({"recording": bool(routes.on_record())})
        else:
            self._send(HTTPStatus.NOT_FOUND, PLAIN_TEXT, NOT_FOUND_BODY)

    do_GET = _handle_get
    do_POST = _handle_post
    log_message = _log_message

    def _send(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
        cookie: str | None = None,
    ) -> None:
        """Send a complete uncached response, setting ``cookie`` when given."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _send_page(self) -> None:
        """Send the page and store the access key in a cookie for its own requests."""
        server = self._http_server()
        cookie = access.set_cookie_value(server.cookie_name, server.routes.key)
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", PAGE_HTML.encode(), cookie)

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

    def _stream_frames(self, hub: FrameHub) -> None:
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

    Each start creates a new access key, held only in memory, that every request must
    carry; :attr:`url` includes it.

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
        self._hub = FrameHub()
        self._key: str | None = None
        self._server: _RemoteHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def viewers(self) -> int:
        """Number of open ``/stream`` connections."""
        return self._hub.viewers

    @property
    def access_key(self) -> str | None:
        """Access key requests must carry while serving; None when stopped."""
        return self._key

    @property
    def url(self) -> str:
        """Address a phone opens, with the access key query while the server runs."""
        base = f"http://{lan_ip()}:{self.port}/"
        return base if self._key is None else access.keyed_url(base, self._key)

    def start(self) -> None:
        """Create a new access key, bind the port and serve on a background thread.

        Raises:
            OSError: When no port in the allowed range is free.
        """
        if self._server is not None:
            return
        self._hub = FrameHub()
        key = access.new_key()
        routes = _Routes(self._hub, self.on_snapshot, self.on_record, key)
        server = _bind(routes, self.port, self._attempts)
        self._server = server
        self._key = key
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
        self._key = None
        self._hub.close()
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=STOP_JOIN_SECONDS)
            self._thread = None
