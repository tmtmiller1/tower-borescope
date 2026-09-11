"""Tests for tower_borescope.remote.page: the phone monitor HTML."""

from __future__ import annotations

from tower_borescope.remote.page import PAGE_HTML

EM_DASH = "\u2014"
EN_DASH = "\u2013"


def test_page_names_the_application():
    assert "<title>Tower Borescope</title>" in PAGE_HTML


def test_page_uses_every_endpoint():
    assert 'src="/stream"' in PAGE_HTML
    assert "fetch('/snapshot'" in PAGE_HTML
    assert "fetch('/record'" in PAGE_HTML
    assert "j.recording" in PAGE_HTML


def test_page_text_is_plain():
    assert EM_DASH not in PAGE_HTML
    assert EN_DASH not in PAGE_HTML
    assert PAGE_HTML.isascii()
    assert max(len(line) for line in PAGE_HTML.splitlines()) <= 90
