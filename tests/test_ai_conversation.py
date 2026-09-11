"""Tests for tower_borescope.ai.conversation on the deterministic fake backend."""

from __future__ import annotations

import pytest

from synthetic import textured_frame
from tower_borescope.ai.base import Usage
from tower_borescope.ai.conversation import Conversation, estimate_scale
from tower_borescope.ai.factory import estimated_cost
from tower_borescope.ai.schema import Analysis, fallback_analysis
from tower_borescope.jpeg import encode_jpeg

JPEG = encode_jpeg(textured_frame(320, 240))


@pytest.fixture
def backend():
    from fakes import FakeBackend

    return FakeBackend()


def test_analyze_keeps_the_image_in_the_first_user_turn(backend):
    conversation = Conversation(backend, JPEG, "under the sink", 0.05)
    analysis = conversation.analyze()
    first, second = conversation.messages
    assert analysis.subject.startswith("Copper") and conversation.analysis is analysis
    assert first["role"] == "user" and first["jpeg"] == JPEG
    assert "under the sink" in first["text"] and "0.0500 mm" in first["text"]
    assert second["role"] == "assistant" and second["jpeg"] is None
    assert Analysis.model_validate_json(second["text"]) == analysis


def test_analyze_normalizes_loose_backend_output(backend):
    loose = fallback_analysis("prose")
    loose.condition = "Looks POOR"
    loose.confidence = "fairly high"
    backend.analyze = lambda jpeg, prompt: loose
    analysis = Conversation(backend, JPEG).analyze()
    assert analysis.condition == "poor" and analysis.confidence == "high"


def test_ask_streams_and_records_both_turns(backend):
    conversation = Conversation(backend, JPEG)
    conversation.analyze()
    chunks = []
    answer = conversation.ask("Is it leaking?", chunks.append)
    assert answer.startswith("Probably") and len(chunks) > 3
    assert "".join(chunks) == answer
    assert conversation.messages[-2] == {
        "role": "user",
        "text": "Is it leaking?",
        "jpeg": None,
    }
    assert conversation.messages[-1] == {
        "role": "assistant",
        "text": answer,
        "jpeg": None,
    }
    assert all(message["jpeg"] is None for message in conversation.messages[1:])


def test_estimate_scale_normalizes_the_estimate(backend):
    estimate = estimate_scale(backend, JPEG)
    assert estimate.found
    assert estimate.span == [0.30, 0.50, 0.70, 0.50]


def test_local_fake_backend_counts_usage_without_cost(backend):
    Conversation(backend, JPEG).analyze()
    assert backend.usage == Usage(1500, 600)
    assert estimated_cost(backend) == 0.0
