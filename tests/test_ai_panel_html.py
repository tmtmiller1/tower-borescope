"""Tests for tower_borescope.ai.panel_html: analysis panel rich text."""

from __future__ import annotations

import pytest

from tower_borescope.ai.panel_html import CONDITION_COLORS, NO_ISSUES_TEXT, analysis_html
from tower_borescope.ai.schema import fallback_analysis


@pytest.fixture
def sample():
    from fakes import SAMPLE_ANALYSIS

    return SAMPLE_ANALYSIS.model_copy(deep=True)


def test_sample_analysis_renders_issues_and_lists(sample):
    text = analysis_html(sample)
    assert "1. Mineral deposits at fitting" in text and "MEDIUM" in text
    assert "2. Surface tarnish" in text and CONDITION_COLORS["fair"] in text
    assert "What to do" in text and "Adjustable wrench" in text
    assert "Shut the supply valve" in text and NO_ISSUES_TEXT not in text


def test_model_text_is_escaped(sample):
    sample.subject = "<script>alert(1)</script>"
    sample.issues[0].note = "a & b"
    text = analysis_html(sample)
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert "a &amp; b" in text


def test_clean_view_says_no_problems(sample):
    sample.issues = []
    assert NO_ISSUES_TEXT in analysis_html(sample)


def test_unstructured_answer_shows_prose_without_verdict():
    text = analysis_html(fallback_analysis("It is a pipe."))
    assert "It is a pipe." in text
    assert NO_ISSUES_TEXT not in text
