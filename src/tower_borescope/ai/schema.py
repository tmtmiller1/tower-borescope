"""Structured answers from vision models and normalization of loose model output.

Small local models often ignore the enum hints in a JSON schema and answer with free
text such as "Critical" or "Overall it looks fair". The normalization functions map
those values onto the fixed vocabularies the application draws with, clip boxes and
spans to the image, and sort issues by severity.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, Field

SEVERITIES: tuple[str, ...] = ("high", "medium", "low", "info")
CONDITIONS: tuple[str, ...] = ("good", "fair", "poor", "unknown")
CONFIDENCES: tuple[str, ...] = ("low", "medium", "high")

SEVERITY_ORDER: dict[str, int] = {name: rank for rank, name in enumerate(SEVERITIES)}
UNRANKED_SEVERITY = len(SEVERITIES)
MIN_EXTENT = 0.005
COORDINATE_COUNT = 4
FALLBACK_SUBJECT = "Unstructured answer"
FALLBACK_TEXT_LIMIT = 2000

CONDITION_SYNONYMS: dict[str, str] = {
    "excellent": "good",
    "ok": "fair",
    "bad": "poor",
    "damaged": "poor",
}
SEVERITY_SYNONYMS: dict[str, str] = {
    "critical": "high",
    "severe": "high",
    "urgent": "high",
    "moderate": "medium",
    "minor": "low",
}


class Issue(BaseModel):
    """One problem visible in the frame.

    Attributes:
        label: Short name of the problem.
        severity: One of ``SEVERITIES``.
        note: Observation and its consequence.
        box: ``[x0, y0, x1, y1]`` as fractions of the image, or None.
    """

    label: str = Field(description="Short name of the problem, e.g. 'Corroded fitting'")
    severity: str = Field(
        description="One of: info, low, medium, high",
        json_schema_extra={"enum": list(SEVERITIES)},
    )
    note: str = Field(description="What you see and why it matters, 1-2 sentences")
    box: list[float] | None = Field(
        default=None,
        description="[x0, y0, x1, y1] as fractions 0..1 (exactly four numbers), or null",
    )


class Analysis(BaseModel):
    """A structured inspection of one frame.

    Attributes:
        subject: Main object or material in view.
        description: What is visible.
        condition: One of ``CONDITIONS``.
        issues: Problems, most severe first after normalization.
        actions: Next steps in order.
        parts_and_tools: Parts, materials or tools likely needed.
        safety: Safety warnings.
        confidence: One of ``CONFIDENCES``.
        questions: Follow-up questions worth asking.
    """

    subject: str = Field(
        description=(
            "The main object or material in view (not the location), in a few words, "
            "e.g. 'Smoke detector on drywall'"
        )
    )
    description: str = Field(description="What is visible, 1-3 sentences")
    condition: str = Field(
        description="One of: good, fair, poor, unknown",
        json_schema_extra={"enum": list(CONDITIONS)},
    )
    issues: list[Issue]
    actions: list[str]
    parts_and_tools: list[str] = Field(
        description="Parts, materials or tools likely needed; empty if none"
    )
    safety: list[str] = Field(description="Safety warnings; empty if none")
    confidence: str = Field(
        description="One of: low, medium, high",
        json_schema_extra={"enum": list(CONFIDENCES)},
    )
    questions: list[str]


class ScaleEstimate(BaseModel):
    """A scale reference recognized in the frame.

    Attributes:
        found: True when an object of standard size is visible.
        reference_object: The object used as the reference.
        standard_size_mm: Real length of the referenced dimension.
        span: ``[x0, y0, x1, y1]`` endpoints of that dimension as fractions, or None.
        confidence: One of ``CONFIDENCES``.
        reasoning: Why the reference was chosen.
    """

    found: bool = Field(
        description="True if something of a known standard size is clearly visible"
    )
    reference_object: str = Field(
        description=(
            "What was used as the reference, e.g. '1/2 in copper pipe (5/8 in OD)'"
        )
    )
    standard_size_mm: float = Field(
        description=(
            "The real size of the referenced dimension in millimetres; 0 if not found"
        )
    )
    span: list[float] | None = Field(
        default=None,
        description=(
            "[x0, y0, x1, y1] fractions 0..1: the two ends of that dimension in the image"
        ),
    )
    confidence: str = Field(
        description="One of: low, medium, high",
        json_schema_extra={"enum": list(CONFIDENCES)},
    )
    reasoning: str = Field(
        description=(
            "One or two sentences on why this reference and how sure the "
            "identification is"
        )
    )


def _pick(
    text: str | None,
    options: tuple[str, ...],
    default: str,
    synonyms: Mapping[str, str] | None = None,
) -> str:
    """Map free text onto one of ``options``.

    An exact match wins, then the first option contained in the text, then the first
    synonym contained in the text, then ``default``.
    """
    lowered = (text or "").strip().lower()
    if lowered in options:
        return lowered
    for option in options:
        if option in lowered:
            return option
    for word, option in (synonyms or {}).items():
        if word in lowered:
            return option
    return default


def _clipped(values: list[float] | None) -> list[float] | None:
    """Four coordinates clamped to ``[0, 1]``, or None for any other shape."""
    if values is None or len(values) != COORDINATE_COUNT:
        return None
    return [min(max(float(value), 0.0), 1.0) for value in values]


def _clean_box(box: list[float] | None) -> list[float] | None:
    """A box with ordered corners and some width and height, else None."""
    clipped = _clipped(box)
    if clipped is None:
        return None
    x0, x1 = sorted((clipped[0], clipped[2]))
    y0, y1 = sorted((clipped[1], clipped[3]))
    if x1 - x0 > MIN_EXTENT and y1 - y0 > MIN_EXTENT:
        return [x0, y0, x1, y1]
    return None


def _clean_span(span: list[float] | None) -> list[float] | None:
    """Two endpoints of a measured dimension with some length, else None.

    Unlike a box, a span keeps its point order and may be exactly horizontal or
    vertical.
    """
    clipped = _clipped(span)
    if clipped is None:
        return None
    x0, y0, x1, y1 = clipped
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return clipped if length > MIN_EXTENT else None


def normalize_analysis(analysis: Analysis) -> Analysis:
    """Coerce loose values into the vocabulary the application draws with.

    Args:
        analysis: Model answer; modified in place.

    Returns:
        The same analysis, with issues sorted most severe first.
    """
    analysis.condition = _pick(
        analysis.condition, CONDITIONS, "unknown", CONDITION_SYNONYMS
    )
    analysis.confidence = _pick(analysis.confidence, CONFIDENCES, "medium")
    for issue in analysis.issues:
        issue.severity = _pick(issue.severity, SEVERITIES, "info", SEVERITY_SYNONYMS)
        issue.box = _clean_box(issue.box)
    analysis.issues.sort(
        key=lambda issue: SEVERITY_ORDER.get(issue.severity, UNRANKED_SEVERITY)
    )
    return analysis


def normalize_scale(estimate: ScaleEstimate) -> ScaleEstimate:
    """Clean a scale estimate so a found reference always carries a usable span.

    Args:
        estimate: Model answer; modified in place.

    Returns:
        The same estimate, with ``found`` cleared when the span or size is missing.
    """
    estimate.confidence = _pick(estimate.confidence, CONFIDENCES, "low")
    estimate.span = _clean_span(estimate.span)
    if estimate.found and (estimate.span is None or estimate.standard_size_mm <= 0):
        estimate.found = False
    return estimate


def fallback_analysis(text: str) -> Analysis:
    """Wrap an unparseable reply so the application still shows what the model said.

    Args:
        text: The model's prose reply.

    Returns:
        An analysis with ``FALLBACK_SUBJECT``, unknown condition and low confidence.
    """
    return Analysis(
        subject=FALLBACK_SUBJECT,
        description=text.strip()[:FALLBACK_TEXT_LIMIT],
        condition="unknown",
        issues=[],
        actions=[],
        parts_and_tools=[],
        safety=[],
        confidence="low",
        questions=[],
    )
