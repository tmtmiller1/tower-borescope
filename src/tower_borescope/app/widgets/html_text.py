"""Escaping of text placed into Qt rich text."""

from __future__ import annotations

from typing import Final

REPLACEMENTS: Final = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#39;"),
)


def html_escape(text: object) -> str:
    """Escape a value for HTML text or a quoted attribute.

    Args:
        text: Any value; it is converted with ``str`` first.

    Returns:
        The text with ampersands, angle brackets and both quote characters escaped.
    """
    escaped = str(text)
    for character, entity in REPLACEMENTS:
        escaped = escaped.replace(character, entity)
    return escaped
