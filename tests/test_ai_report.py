"""Tests for tower_borescope.ai.report: HTML rendering and report files."""

from __future__ import annotations

import pytest

from synthetic import textured_frame
from tower_borescope.ai.base import AiError
from tower_borescope.ai.images import to_base64
from tower_borescope.ai.report import ReportEntry, render_report_html, write_report
from tower_borescope.ai.schema import fallback_analysis
from tower_borescope.config import data_paths
from tower_borescope.jpeg import encode_jpeg

JPEG = encode_jpeg(textured_frame(320, 240))
TIME = "2026-09-10 18:30"


@pytest.fixture
def entry():
    from fakes import SAMPLE_ANALYSIS

    return ReportEntry(JPEG, SAMPLE_ANALYSIS, "under sink", TIME)


@pytest.fixture
def backend():
    from fakes import FakeBackend

    return FakeBackend()


def test_render_includes_summary_and_image(entry):
    page = render_report_html("Test <report>", "Para one.\n\nPara two.", [entry], "Fake")
    assert f"data:image/jpeg;base64,{to_base64(JPEG)}" in page
    assert "<p>Para one.</p>" in page and "<p>Para two.</p>" in page
    assert "<title>Test &lt;report&gt;</title>" in page and "<report>" not in page
    assert "1 view(s) | analysis by Fake" in page
    assert page.endswith("</body></html>")


def test_render_includes_findings_without_em_dashes(entry):
    page = render_report_html("Report", "Summary.", [entry], "Fake")
    assert "Copper supply" in page and "<b>Mineral deposits at fitting</b>: " in page
    assert "under sink" in page and "Recommended actions" in page
    assert "—" not in page


def test_entry_without_issues_lists_or_context_omits_sections():
    bare = ReportEntry(JPEG, fallback_analysis("Only prose."), "", TIME)
    page = render_report_html("Report", "Summary.", [bare])
    assert "Issues" not in page and "Recommended actions" not in page
    assert "analysis by AI" in page and f"<div class='meta'>{TIME}</div>" in page


def test_write_report_saves_html_in_the_reports_folder(backend, entry):
    prompts = []
    summarize = backend.summarize
    backend.summarize = lambda prompt: prompts.append(prompt) or summarize(prompt)
    path = write_report(backend, [entry])
    assert path.parent == data_paths().reports and path.is_file()
    assert path.name.startswith("report_") and path.suffix == ".html"
    text = path.read_text(encoding="utf-8")
    assert "Probably old residue" in text and "Fake (test)" in text
    assert f"View 1 ({TIME}) - under sink:" in prompts[0]


def test_unwritable_reports_folder_raises_ai_error(backend, entry, monkeypatch, tmp_path):
    blocker = tmp_path / "occupied"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setenv("TOWER_BORESCOPE_REPORTS_DIR", str(blocker))
    with pytest.raises(AiError, match="Could not write the report"):
        write_report(backend, [entry], title="Blocked")
