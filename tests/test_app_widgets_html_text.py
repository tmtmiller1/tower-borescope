"""Tests for tower_borescope.app.widgets.html_text: rich text escaping."""

from __future__ import annotations

from tower_borescope.app.widgets.html_text import html_escape


def test_escapes_markup_and_quotes():
    text = "<a href='x'>\"Tom & Jerry\"</a>"
    assert html_escape(text) == (
        "&lt;a href=&#39;x&#39;&gt;&quot;Tom &amp; Jerry&quot;&lt;/a&gt;"
    )


def test_ampersand_is_escaped_first():
    assert html_escape("&lt;") == "&amp;lt;"


def test_converts_non_strings():
    assert html_escape(12.5) == "12.5"
