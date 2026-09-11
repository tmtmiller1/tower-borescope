"""Rich text for the analysis panel in the application window."""

from __future__ import annotations

import html
from collections.abc import Iterator

from tower_borescope.ai.schema import FALLBACK_SUBJECT, Analysis, Issue

SEVERITY_COLORS: dict[str, str] = {
    "high": "#ff5a3c",
    "medium": "#f0b429",
    "low": "#4c8dff",
    "info": "#9aa0a6",
}
CONDITION_COLORS: dict[str, str] = {
    "good": "#38c172",
    "fair": "#f0b429",
    "poor": "#ff5a3c",
    "unknown": "#9aa0a6",
}
MUTED_COLOR = "#9aa0a6"
NOTE_COLOR = "#cfd2d6"
GOOD_COLOR = "#38c172"
NO_ISSUES_TEXT = "No problems identified in this view."
HEADING_STYLE = "margin-top:10px;font-weight:600"


def _header(analysis: Analysis) -> list[str]:
    """Subject, condition and confidence, then the description."""
    color = CONDITION_COLORS.get(analysis.condition, MUTED_COLOR)
    condition = (
        f"<span style='color:{color};font-weight:600'>"
        f"{html.escape(analysis.condition)}</span>"
    )
    return [
        f"<div style='font-size:15px;font-weight:600'>"
        f"{html.escape(analysis.subject)}</div>",
        f"<div style='color:{MUTED_COLOR};margin:2px 0 8px 0'>Condition: {condition}"
        f" &nbsp;|&nbsp; confidence {html.escape(analysis.confidence)}</div>",
        f"<div>{html.escape(analysis.description)}</div>",
    ]


def _issue(number: int, issue: Issue) -> str:
    """One numbered issue in its severity color."""
    color = SEVERITY_COLORS.get(issue.severity, MUTED_COLOR)
    return (
        f"<div style='margin:4px 0'><span style='color:{color};font-weight:700'>"
        f"{number}. {html.escape(issue.label)}</span> "
        f"<span style='color:{color};font-size:11px'>"
        f"{html.escape(issue.severity.upper())}</span><br>"
        f"<span style='color:{NOTE_COLOR}'>{html.escape(issue.note)}</span></div>"
    )


def _lists(analysis: Analysis) -> Iterator[str]:
    """Numbered action, parts and safety lists that have items."""
    sections = (
        ("What to do", analysis.actions),
        ("Parts and tools", analysis.parts_and_tools),
        ("Safety", analysis.safety),
    )
    for heading, items in sections:
        if items:
            entries = "".join(f"<li>{html.escape(item)}</li>" for item in items)
            yield (
                f"<div style='{HEADING_STYLE}'>{heading}</div>"
                f"<ol style='margin:2px 0 0 -18px'>{entries}</ol>"
            )


def analysis_html(analysis: Analysis) -> str:
    """Render an analysis as Qt rich text for the dark analysis panel.

    Args:
        analysis: Normalized analysis.

    Returns:
        HTML with every model-provided value escaped.
    """
    parts = _header(analysis)
    if analysis.issues:
        parts.append(f"<div style='{HEADING_STYLE}'>Issues</div>")
        parts.extend(_issue(n, issue) for n, issue in enumerate(analysis.issues, 1))
    elif analysis.subject != FALLBACK_SUBJECT:
        parts.append(
            f"<div style='margin-top:10px;color:{GOOD_COLOR}'>{NO_ISSUES_TEXT}</div>"
        )
    parts.extend(_lists(analysis))
    return "".join(parts)
