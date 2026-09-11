"""Tests for tower_borescope.ai.prompts: prompt text and the analysis prompt builder."""

from __future__ import annotations

import re

import pytest

from tower_borescope.ai.prompts import (
    ANALYZE_TEMPLATE,
    CHAT_SYSTEM_PROMPT,
    FOLLOWUP_INSTRUCTION,
    JSON_REPLY_INSTRUCTION,
    REPORT_SUMMARY_PROMPT,
    SCALE_PROMPT,
    SYSTEM_PROMPT,
    analyze_prompt,
)

PROMPTS = (
    SYSTEM_PROMPT,
    ANALYZE_TEMPLATE,
    SCALE_PROMPT,
    FOLLOWUP_INSTRUCTION,
    JSON_REPLY_INSTRUCTION,
    REPORT_SUMMARY_PROMPT,
)
EMOJI_RE = re.compile("[\U0001f300-\U0001faff☀-➿⬀-⯿]")
DASHES = ("—", "–")


@pytest.mark.parametrize("text", PROMPTS)
def test_prompts_have_no_dashes_emoji_or_joined_whitespace(text):
    assert not any(dash in text for dash in DASHES)
    assert not EMOJI_RE.search(text)
    assert "  " not in text and "\\" not in text


def test_system_prompt_keeps_box_instructions():
    assert "fractions of the image (x0, y0, x1, y1" in SYSTEM_PROMPT
    assert "found=false" in SCALE_PROMPT


def test_analyze_prompt_without_context_or_scale():
    text = analyze_prompt("   ", None)
    assert text.startswith("Analyze this scope view.\n\nFill every field.")


def test_analyze_prompt_adds_context_and_calibration():
    text = analyze_prompt(" under the sink ", 0.05)
    assert "\nContext from the homeowner: under the sink\n" in text
    assert "one pixel is 0.0500 mm" in text
    assert "about 64 mm wide" in text


def test_chat_system_prompt_appends_followup_instruction():
    assert CHAT_SYSTEM_PROMPT == f"{SYSTEM_PROMPT}\n\n{FOLLOWUP_INSTRUCTION}"
