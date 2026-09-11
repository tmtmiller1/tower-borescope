"""Tests for tower_borescope.ai.parsing: JSON extraction and tolerant validation."""

from __future__ import annotations

import json

import pytest

from tower_borescope.ai.base import AiError
from tower_borescope.ai.parsing import extract_json, parse_reply
from tower_borescope.ai.schema import FALLBACK_SUBJECT, Analysis, ScaleEstimate

ANALYSIS = {
    "subject": "Drain trap",
    "description": "PVC trap with a slip nut.",
    "condition": "good",
    "issues": [],
    "actions": [],
    "parts_and_tools": [],
    "safety": [],
    "confidence": "high",
    "questions": [],
}


def test_extracts_fenced_object():
    assert extract_json('Sure! ```json\n{"a": {"b": 1}}\n``` done')["a"]["b"] == 1
    assert extract_json('```\n{"plain": true}\n```') == {"plain": True}


def test_extracts_embedded_object():
    assert extract_json('text {"x": [1,2]} trailing')["x"] == [1, 2]


def test_skips_braces_in_prose_and_inside_strings():
    assert extract_json('use {braces} then {"ok": true}') == {"ok": True}
    assert extract_json('{"note": "a } brace"} end') == {"note": "a } brace"}


@pytest.mark.parametrize("text", ["no object here", '{"a": 1', "[1, 2]"])
def test_missing_or_unterminated_object_raises_value_error(text):
    with pytest.raises(ValueError):
        extract_json(text)


def test_parse_reply_accepts_clean_and_wrapped_json():
    clean = parse_reply(json.dumps(ANALYSIS), Analysis, "The model")
    wrapped = parse_reply(f"Here it is:\n{json.dumps(ANALYSIS)}\nThanks", Analysis, "x")
    assert clean.subject == "Drain trap"
    assert wrapped == clean


@pytest.mark.parametrize("reply", ["It looks like a pipe.", '{"subject": "only"}'])
def test_unusable_analysis_reply_falls_back_to_prose(reply):
    analysis = parse_reply(reply, Analysis, "The model")
    assert analysis.subject == FALLBACK_SUBJECT
    assert analysis.description == reply


def test_unusable_scale_reply_raises_with_source():
    with pytest.raises(AiError, match="The workspace model did not return a usable"):
        parse_reply("no idea", ScaleEstimate, "The workspace model")
