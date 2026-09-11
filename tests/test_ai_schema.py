"""Tests for tower_borescope.ai.schema: models, loose-output normalization, fallback."""

from __future__ import annotations

import json

import pytest

from tower_borescope.ai.schema import (
    CONDITIONS,
    FALLBACK_SUBJECT,
    FALLBACK_TEXT_LIMIT,
    Analysis,
    Issue,
    ScaleEstimate,
    fallback_analysis,
    normalize_analysis,
    normalize_scale,
)


def _analysis(condition="fair", confidence="medium", issues=None):
    return Analysis(
        subject="x",
        description="y",
        condition=condition,
        issues=issues or [],
        actions=[],
        parts_and_tools=[],
        safety=[],
        confidence=confidence,
        questions=[],
    )


def _scale(**changes):
    estimate = ScaleEstimate(
        found=True,
        reference_object="1/2 in copper pipe (5/8 in OD)",
        standard_size_mm=15.875,
        span=[0.30, 0.50, 0.70, 0.50],
        confidence="medium",
        reasoning="Pipe OD spans the frame's middle.",
    )
    return estimate.model_copy(update=changes)


def test_analysis_round_trips_through_json():
    box = [0.1, 0.2, 0.3, 0.4]
    original = _analysis(issues=[Issue(label="a", severity="low", note="n", box=box)])
    assert Analysis.model_validate(json.loads(original.model_dump_json())) == original


def test_json_schema_carries_enum_hints():
    schema = json.dumps(Analysis.model_json_schema())
    assert '"enum"' in schema
    assert all(f'"{name}"' in schema for name in CONDITIONS)
    assert '"enum"' in json.dumps(ScaleEstimate.model_json_schema())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Overall it looks Fair with some wear", "fair"),
        ("GOOD", "good"),
        ("excellent shape", "good"),
        ("ok I guess", "fair"),
        ("badly worn", "poor"),
        ("damaged", "poor"),
        ("???", "unknown"),
        ("", "unknown"),
    ],
)
def test_condition_maps_loose_text(raw, expected):
    assert normalize_analysis(_analysis(condition=raw)).condition == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Critical", "high"),
        ("severe leak", "high"),
        ("urgent", "high"),
        ("moderate", "medium"),
        ("minor", "low"),
        ("LOW", "low"),
        ("???", "info"),
    ],
)
def test_severity_maps_loose_text(raw, expected):
    issue = Issue(label="a", severity=raw, note="n")
    assert normalize_analysis(_analysis(issues=[issue])).issues[0].severity == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("High (functional test needed)", "high"), ("", "medium"), ("very sure", "medium")],
)
def test_confidence_maps_loose_text(raw, expected):
    assert normalize_analysis(_analysis(confidence=raw)).confidence == expected


def test_issues_sort_by_severity_and_boxes_are_cleaned():
    issues = [
        Issue(label="a", severity="Critical", note="n", box=[0.9, 0.9, 0.1, 0.1]),
        Issue(label="b", severity="minor", note="n", box=[0.5, 0.5]),
        Issue(label="c", severity="???", note="n", box=None),
        Issue(label="d", severity="medium", note="n", box=[-1.0, 0.2, 2.0, 0.8]),
    ]
    loose = normalize_analysis(_analysis(issues=issues))
    assert [issue.label for issue in loose.issues] == ["a", "d", "b", "c"]
    assert [issue.severity for issue in loose.issues] == ["high", "medium", "low", "info"]
    assert loose.issues[0].box == [0.1, 0.1, 0.9, 0.9]
    assert loose.issues[1].box == [0.0, 0.2, 1.0, 0.8]
    assert loose.issues[2].box is None and loose.issues[3].box is None


def test_thin_box_is_dropped():
    issue = Issue(label="a", severity="low", note="n", box=[0.5, 0.1, 0.503, 0.9])
    assert normalize_analysis(_analysis(issues=[issue])).issues[0].box is None


def test_horizontal_span_is_valid_and_kept():
    estimate = normalize_scale(_scale())
    assert estimate.found
    assert estimate.span == [0.30, 0.50, 0.70, 0.50]


def test_span_endpoint_order_is_preserved_and_clipped():
    assert normalize_scale(_scale(span=[0.7, 0.2, 0.3, 0.6])).span == [0.7, 0.2, 0.3, 0.6]
    clipped = normalize_scale(_scale(span=[-0.2, 0.5, 1.4, 0.5]))
    assert clipped.span == [0.0, 0.5, 1.0, 0.5]


@pytest.mark.parametrize(
    "span", [[0.5, 0.5, 0.5, 0.5], [0.5, 0.5, 0.503, 0.5], [0.1, 0.2], None]
)
def test_short_or_missing_span_clears_found(span):
    estimate = normalize_scale(_scale(span=span))
    assert not estimate.found
    assert estimate.span is None


def test_span_just_over_threshold_is_kept():
    assert normalize_scale(_scale(span=[0.5, 0.5, 0.506, 0.5])).found


def test_missing_size_clears_found_and_confidence_defaults_low():
    estimate = normalize_scale(_scale(standard_size_mm=0.0, confidence="dunno"))
    assert not estimate.found
    assert estimate.span == [0.30, 0.50, 0.70, 0.50]
    assert estimate.confidence == "low"


def test_fallback_analysis_keeps_prose():
    fallback = fallback_analysis("  just prose  ")
    assert fallback.subject == FALLBACK_SUBJECT
    assert fallback.description == "just prose"
    assert fallback.condition == "unknown" and fallback.confidence == "low"
    assert fallback.issues == [] and fallback.questions == []
    assert len(fallback_analysis("x" * 5000).description) == FALLBACK_TEXT_LIMIT
