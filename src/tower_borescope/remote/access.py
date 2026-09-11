"""Access key for the phone monitor: generation, request parsing and checking.

Each server start creates a new random key that exists only in memory. A request
presents it in the ``key`` query parameter or in the cookie the page response sets,
and every comparison takes constant time.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qs, urlencode, urlsplit

KEY_BYTES: Final = 18
KEY_PARAMETER: Final = "key"
COOKIE_PREFIX: Final = "borescope_key_"
COOKIE_ATTRIBUTES: Final = "HttpOnly; SameSite=Strict; Path=/"


@dataclass(frozen=True, slots=True)
class RequestTarget:
    """Path and presented access key of a request target.

    Attributes:
        path: Target path without the query.
        key: First non-empty ``key`` query parameter, or None without one.
    """

    path: str
    key: str | None


def new_key() -> str:
    """Create a random access key.

    Returns:
        A URL-safe key of 24 characters encoding 18 bytes from the system's secure
        random source.
    """
    return secrets.token_urlsafe(KEY_BYTES)


def keyed_url(base: str, key: str) -> str:
    """Append the access key to an address as the ``key`` query parameter.

    Args:
        base: Address without a query, such as ``http://192.168.1.20:8765/``.
        key: Access key.

    Returns:
        The address with the key query.
    """
    return f"{base}?{urlencode({KEY_PARAMETER: key})}"


def parse_target(target: str) -> RequestTarget:
    """Split a request target into its path and presented key.

    Args:
        target: Request target from the request line, such as ``/stream?key=abc``.

    Returns:
        The path and key; a target that does not parse yields an empty path and no
        key, which no route accepts.
    """
    try:
        parts = urlsplit(target)
    except ValueError:
        return RequestTarget("", None)
    values = parse_qs(parts.query).get(KEY_PARAMETER)
    return RequestTarget(parts.path, values[0] if values else None)


def cookie_name(port: int) -> str:
    """Name of the access cookie for one server port.

    Browsers share cookies across the ports of a host, so the port in the name keeps
    two running servers from replacing each other's cookie.

    Args:
        port: Listening port of the server.

    Returns:
        The cookie name.
    """
    return f"{COOKIE_PREFIX}{port}"


def cookie_key(header: str, name: str) -> str | None:
    """Value of one cookie in a ``Cookie`` request header.

    Args:
        header: Header value with ``name=value`` pairs separated by semicolons.
        name: Cookie name to look up.

    Returns:
        The first value stored under ``name``, or None when the cookie is absent.
    """
    for item in header.split(";"):
        item_name, separator, value = item.strip().partition("=")
        if separator and item_name == name:
            return value.strip()
    return None


def set_cookie_value(name: str, key: str) -> str:
    """``Set-Cookie`` header value that stores the key for the page's own requests.

    Args:
        name: Cookie name from :func:`cookie_name`.
        key: Access key.

    Returns:
        The header value with the ``HttpOnly``, ``SameSite=Strict`` and ``Path=/``
        attributes.
    """
    return f"{name}={key}; {COOKIE_ATTRIBUTES}"


def key_matches(candidate: str | None, key: str) -> bool:
    """Compare a presented key with the server key in constant time.

    Args:
        candidate: Key from the query or the cookie, or None when absent.
        key: Server access key.

    Returns:
        True only when both keys are non-empty and equal.
    """
    if not candidate or not key:
        return False
    presented = candidate.encode("utf-8", "surrogatepass")
    return hmac.compare_digest(presented, key.encode("utf-8"))
