"""JSON and line-streaming HTTP calls to local model servers, using only the standard
library.

Every failure surfaces as :class:`~tower_borescope.ai.base.AiError` with the URL, so
the application can show it without a traceback.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from typing import Any

from tower_borescope.ai.base import AiError

LOCAL_TIMEOUT = 600.0
ERROR_BODY_LIMIT = 300


def base_url(url: str, service: str, variable: str) -> str:
    """Return a configured base address without a trailing slash.

    Args:
        url: Address from the settings or the environment.
        service: Service name used in the error message.
        variable: Environment variable that supplies the address.

    Returns:
        The address, stripped.

    Raises:
        AiError: When the address is blank; the message names ``variable``.
    """
    stripped = url.strip().rstrip("/")
    if not stripped:
        raise AiError(
            f"The {service} URL is not set. Set {variable} in the .env file "
            "or enter the URL in AI settings."
        )
    return stripped


def _request(
    url: str, payload: object | None, headers: Mapping[str, str] | None
) -> urllib.request.Request:
    """A GET request without a payload, else a JSON POST request."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    return request


def _open(request: urllib.request.Request, timeout: float) -> Any:
    """Open a request, translating transport failures into AiError."""
    url = request.full_url
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")[:ERROR_BODY_LIMIT]
        raise AiError(f"HTTP {error.code} from {url}: {body}") from error
    except urllib.error.URLError as error:
        raise AiError(f"Could not reach {url}: {error.reason}") from error
    except OSError as error:
        raise AiError(f"Connection to {url} failed: {error}") from error


def http_json(
    url: str,
    payload: object | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = LOCAL_TIMEOUT,
) -> dict[str, Any]:
    """Send one request and decode a JSON object reply.

    Args:
        url: Full endpoint address.
        payload: JSON body; None sends a GET request.
        headers: Extra request headers.
        timeout: Seconds to wait; a local model may need minutes to load.

    Returns:
        The decoded reply object.

    Raises:
        AiError: When the server is unreachable, returns an HTTP error, or replies
            with something other than a JSON object.
    """
    with _open(_request(url, payload, headers), timeout) as response:
        try:
            body = response.read()
        except OSError as error:
            raise AiError(f"Connection to {url} failed: {error}") from error
    try:
        decoded = json.loads(body.decode(errors="replace"))
    except json.JSONDecodeError as error:
        raise AiError(f"Invalid JSON from {url}: {error}") from error
    if not isinstance(decoded, dict):
        raise AiError(f"Expected a JSON object from {url}")
    return decoded


def http_stream_lines(
    url: str,
    payload: object,
    headers: Mapping[str, str] | None = None,
    timeout: float = LOCAL_TIMEOUT,
) -> Iterator[str]:
    """POST a JSON body and yield each non-blank line of the streamed reply.

    Args:
        url: Full endpoint address.
        payload: JSON body.
        headers: Extra request headers.
        timeout: Seconds to wait for each read.

    Yields:
        Reply lines with surrounding whitespace removed.

    Raises:
        AiError: When the server is unreachable, returns an HTTP error, or the
            connection drops mid-stream.
    """
    with _open(_request(url, payload, headers), timeout) as response:
        try:
            for raw in response:
                line = raw.decode(errors="replace").strip()
                if line:
                    yield line
        except OSError as error:
            raise AiError(f"Connection to {url} failed: {error}") from error
