"""HTML inspection reports built from several analyzed views."""

from __future__ import annotations

import html
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tower_borescope.ai.base import AiError, Backend
from tower_borescope.ai.images import to_base64
from tower_borescope.ai.prompts import REPORT_SUMMARY_PROMPT
from tower_borescope.ai.schema import Analysis, Issue
from tower_borescope.config import data_paths

DEFAULT_TITLE = "Scope inspection report"
SEVERITY_COLORS: dict[str, str] = {
    "high": "#c0392b",
    "medium": "#d68910",
    "low": "#2874a6",
    "info": "#6c757d",
}
DEFAULT_COLOR = "#6c757d"
REPORT_CSS = """
body{font-family:-apple-system,Helvetica,Arial,sans-serif;
max-width:900px;margin:32px auto;padding:0 20px;color:#222;line-height:1.45}
h1{font-size:26px;margin-bottom:4px}
h2{font-size:19px;margin-top:36px;border-bottom:1px solid #ddd;padding-bottom:4px}
.meta{color:#666;font-size:13px}
img{max-width:100%;border-radius:6px;border:1px solid #ddd}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;color:#fff;font-size:12px;
font-weight:600;margin-right:6px}
.issue{margin:8px 0} ul{margin:6px 0}
.summary{background:#f6f7f9;padding:14px 18px;border-radius:8px}
@media print{h2{page-break-before:always} h2:first-of-type{page-break-before:auto}}
"""


@dataclass(frozen=True, slots=True)
class ReportEntry:
    """One analyzed view in a report.

    Attributes:
        jpeg: The frame.
        analysis: Its analysis.
        context: Homeowner notes for the view.
        time: Capture time as display text.
    """

    jpeg: bytes
    analysis: Analysis
    context: str = ""
    time: str = ""


def _summary_prompt(entries: Sequence[ReportEntry]) -> str:
    """The executive-summary request with every view's findings as JSON."""
    findings: list[str] = []
    for index, entry in enumerate(entries, 1):
        label = f"View {index} ({entry.time})"
        if entry.context:
            label = f"{label} - {entry.context}"
        details = json.dumps(entry.analysis.model_dump(), indent=1)
        findings.append(f"{label}:\n{details}")
    return "\n\n".join([REPORT_SUMMARY_PROMPT, *findings])


def write_report(
    backend: Backend, entries: Sequence[ReportEntry], title: str = DEFAULT_TITLE
) -> Path:
    """Ask the backend for an executive summary and write the HTML report.

    Args:
        backend: Model that writes the summary.
        entries: Views in report order.
        title: Report heading.

    Returns:
        Path of the HTML file inside ``data_paths().reports``.

    Raises:
        AiError: When the backend fails or the file cannot be written.
    """
    summary = backend.summarize(_summary_prompt(entries))
    folder = data_paths().reports
    path = folder / f"report_{datetime.now():%Y%m%d_%H%M%S}.html"
    page = render_report_html(title, summary, entries, backend.describe())
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
    except OSError as error:
        raise AiError(f"Could not write the report to {path}: {error}") from error
    return path


def _header(title: str, view_count: int, model_name: str) -> str:
    """Document head, title and meta line."""
    heading = html.escape(title)
    stamp = datetime.now().strftime("%B %d, %Y %H:%M")
    meta = f"{stamp} | {view_count} view(s) | analysis by {html.escape(model_name)}"
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{heading}</title>\n'
        f"<style>{REPORT_CSS}</style></head><body>\n"
        f'<h1>{heading}</h1>\n<div class="meta">{meta}</div>'
    )


def _summary_section(summary: str) -> str:
    """The summary, one paragraph per blank-line separated block."""
    paragraphs = "".join(
        f"<p>{html.escape(block)}</p>" for block in summary.split("\n\n") if block.strip()
    )
    return f'<h2>Summary</h2><div class="summary">{paragraphs}</div>'


def _issue_html(issue: Issue) -> str:
    """One issue with a colored severity badge."""
    color = SEVERITY_COLORS.get(issue.severity, DEFAULT_COLOR)
    badge = (
        f"<span class='badge' style='background:{color}'>"
        f"{html.escape(issue.severity)}</span>"
    )
    return (
        f"<div class='issue'>{badge}<b>{html.escape(issue.label)}</b>: "
        f"{html.escape(issue.note)}</div>"
    )


def _list_sections(analysis: Analysis) -> Iterator[str]:
    """Bulleted action, parts and safety lists that have items."""
    sections = (
        ("Recommended actions", analysis.actions),
        ("Parts and tools", analysis.parts_and_tools),
        ("Safety", analysis.safety),
    )
    for heading, items in sections:
        if items:
            bullets = "".join(f"<li>{html.escape(item)}</li>" for item in items)
            yield f"<p><b>{heading}</b></p><ul>{bullets}</ul>"


def _entry_section(index: int, entry: ReportEntry) -> str:
    """One view: heading, meta line, image, description, issues and lists."""
    analysis = entry.analysis
    meta = html.escape(entry.time)
    if entry.context:
        meta = f"{meta} | {html.escape(entry.context)}"
    parts = [
        f"<h2>View {index}: {html.escape(analysis.subject)}</h2>",
        f"<div class='meta'>{meta}</div>",
        f"<p><img src='data:image/jpeg;base64,{to_base64(entry.jpeg)}'></p>",
        f"<p>{html.escape(analysis.description)}</p>",
        f"<p><b>Condition:</b> {html.escape(analysis.condition)} &nbsp; "
        f"<b>Confidence:</b> {html.escape(analysis.confidence)}</p>",
    ]
    if analysis.issues:
        parts.append("<p><b>Issues</b></p>")
        parts.extend(_issue_html(issue) for issue in analysis.issues)
    parts.extend(_list_sections(analysis))
    return "\n".join(parts)


def render_report_html(
    title: str, summary: str, entries: Sequence[ReportEntry], model_name: str = "AI"
) -> str:
    """Render a self-contained report page with embedded images.

    Args:
        title: Report heading.
        summary: Executive summary; blank lines separate paragraphs.
        entries: Views in report order.
        model_name: Backend description for the meta line.

    Returns:
        The HTML document.
    """
    parts = [_header(title, len(entries), model_name), _summary_section(summary)]
    parts.extend(_entry_section(index, entry) for index, entry in enumerate(entries, 1))
    parts.append("</body></html>")
    return "\n".join(parts)
