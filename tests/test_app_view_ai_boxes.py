"""Tests for tower_borescope.app.view.ai_boxes: boxes from located AI issues."""

from __future__ import annotations

from fakes import SAMPLE_ANALYSIS
from tower_borescope.ai.schema import Issue
from tower_borescope.app.view.ai_boxes import AiBox, boxes_from_analysis


def test_located_issues_become_boxes():
    boxes = boxes_from_analysis(SAMPLE_ANALYSIS)
    assert boxes == [
        AiBox(0.42, 0.30, 0.68, 0.55, "Mineral deposits at fitting", "medium")
    ]
    box = boxes[0]
    assert (box.x0, box.y1, box.label, box.severity) == (
        0.42,
        0.55,
        "Mineral deposits at fitting",
        "medium",
    )


def test_issues_without_four_numbers_are_skipped():
    analysis = SAMPLE_ANALYSIS.model_copy(deep=True)
    analysis.issues = [
        Issue(label="short", severity="low", note="", box=[0.1, 0.2, 0.3]),
        Issue(label="none", severity="low", note="", box=None),
        Issue(label="ok", severity="high", note="", box=[0.1, 0.2, 0.3, 0.4]),
        Issue(label="long", severity="low", note="", box=[0.1, 0.2, 0.3, 0.4, 0.5]),
    ]
    boxes = boxes_from_analysis(analysis)
    assert [box.label for box in boxes] == ["ok"]
    assert boxes[0] == (0.1, 0.2, 0.3, 0.4, "ok", "high")


def test_no_issues_give_no_boxes():
    analysis = SAMPLE_ANALYSIS.model_copy(update={"issues": []})
    assert boxes_from_analysis(analysis) == []
