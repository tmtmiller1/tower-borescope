"""Tests for tower_borescope.app.window.ai_controller and its helpers with FakeBackend:
analysis with issue boxes, streamed follow-ups, suggested questions, reports with PDF,
settings and failures shown in the panel."""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog

from conftest import wait_until
from fakes import FAKE_ANSWER, FakeBackend
from tower_borescope.ai import keychain
from tower_borescope.ai.anythingllm import AnythingLLMBackend
from tower_borescope.ai.base import AiError
from tower_borescope.ai.ollama import OllamaBackend
from tower_borescope.ai.settings import BACKENDS, AiConfig
from tower_borescope.app.dialogs.ai_settings import AiSettingsDialog
from tower_borescope.app.window import ai_controller
from tower_borescope.app.window.ai_controller import AiWorker
from tower_borescope.app.window.ai_transcript import (
    AiTranscript,
    analyzing_html,
    error_html,
    status_text,
)
from tower_borescope.app.window.report_controller import html_to_pdf
from tower_borescope.config import data_paths
from tower_borescope.device.reader import Reader

READER = Reader.__name__


def toasts(win):
    return win.view.toasts.visible(time.monotonic())


class FailingBackend(FakeBackend):
    def analyze(self, jpeg, prompt):
        raise AiError("model crashed")


@pytest.fixture
def window(window):
    window.ai.backend = FakeBackend()
    window.ai.update_status()
    return window


def analyze(win):
    win.ai.analyze()
    return wait_until(lambda: bool(win.view.ai_boxes))


def test_analyze_freezes_and_draws_the_issue_boxes(window):
    assert analyze(window)
    assert window.view.frozen and window.ai.conversation.analysis is not None
    boxes = window.view.ai_boxes
    assert len(boxes) == 1 and boxes[0].label == "Mineral deposits at fitting"


def test_analysis_fills_the_panel_and_the_status(window):
    assert analyze(window)
    text = window.ai.panel.browser.toPlainText()
    assert "Mineral deposits" in text and "Ask next" in text
    status = window.ai.panel.status.text()
    assert FakeBackend.name in status and "no cost" in status
    assert window.tabs.tabText(window.tabs.currentIndex()) == "AI"
    assert window.ai.panel.analyze_btn.isEnabled()


def test_follow_up_answer_streams_into_the_panel(window):
    assert analyze(window)
    window.ai.panel.question.setText("Is it leaking?")
    window.ai.ask()
    browser = window.ai.panel.browser
    assert wait_until(lambda: "Probably old residue" in browser.toPlainText())
    assert "You: Is it leaking?" in browser.toPlainText()
    assert window.ai.panel.question.text() == ""
    assert wait_until(lambda: window.ai.transcript.html.count(FAKE_ANSWER) == 1)


def test_suggested_question_link_asks_it(window):
    assert analyze(window)
    question = window.ai.conversation.analysis.questions[1]
    window.ai.panel.browser.anchorClicked.emit(QUrl("ask:" + question))
    browser = window.ai.panel.browser
    assert wait_until(lambda: FAKE_ANSWER.split(";")[0] in browser.toPlainText())
    assert f"You: {question}" in browser.toPlainText()


def test_report_is_written_with_a_pdf(window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", opened.append)
    assert analyze(window)
    window.ai.panel.add_btn.click()
    assert window.ai.panel.report_btn.text() == "Report (1)..."
    window.ai.panel.report_btn.click()
    reports = data_paths().reports
    assert wait_until(lambda: bool(opened), 15.0)
    assert any(reports.glob("report_*.pdf"))
    assert opened[0].toLocalFile().endswith(".html")
    assert window.ai.panel.report_btn.text() == "Report (1)..."


def test_requests_need_an_analysis_first(window):
    window.ai.panel.question.setText("Anything?")
    window.ai.ask()
    assert "Analyze a view first, then ask about it" in toasts(window)
    window.ai.report.add_view()
    assert "Analyze a view first" in toasts(window)
    window.ai.report.write()
    assert "Add at least one analyzed view to the report first" in toasts(window)


def test_backend_construction_failure_shows_in_the_panel(window, monkeypatch):
    def refuse(config):
        raise AiError("Ollama is not running")

    monkeypatch.setattr(ai_controller, "make_backend", refuse)
    window.ai.backend = None
    window.ai.analyze()
    text = window.ai.panel.browser.toPlainText()
    assert "Ollama is not running" in text and "AI settings" in text
    assert not window.view.frozen
    assert "Ollama is not running" in toasts(window)


def test_request_failure_shows_in_the_panel(window):
    window.ai.backend = FailingBackend()
    window.ai.analyze()
    browser = window.ai.panel.browser
    assert wait_until(lambda: "model crashed" in browser.toPlainText())
    assert window.ai.panel.analyze_btn.isEnabled()
    assert "AI request failed" in toasts(window)
    assert not window.ai.runner.busy()


def test_settings_dialog_saves_the_config_and_disconnects(window, monkeypatch):
    class AcceptingDialog:
        def __init__(self, settings, parent):
            self.settings = settings

        def exec(self):
            return QDialog.DialogCode.Accepted

        def current_config(self):
            return AiConfig(backend="anthropic")

    monkeypatch.setattr(ai_controller, "AiSettingsDialog", AcceptingDialog)
    window.ai.open_settings()
    assert window.ai.ctx.prefs.values["ai_backend"] == "anthropic"
    assert window.ai.backend is None
    assert (
        window.ai.panel.status.text()
        == "Claude via the Anthropic API (not connected yet)"
    )
    assert "AI settings saved" in toasts(window)


def test_settings_dialog_builds_from_the_window_settings(window, monkeypatch):
    monkeypatch.setattr(keychain, "get_secret", lambda service, **kwargs: None)
    monkeypatch.setattr(keychain, "set_secret", lambda service, value: None)
    monkeypatch.setattr(OllamaBackend, "list_models", staticmethod(lambda url: []))
    monkeypatch.setattr(
        AnythingLLMBackend, "list_workspaces", staticmethod(lambda url, key=None: [])
    )
    dialog = AiSettingsDialog(window.ctx.prefs.values, window)
    assert dialog.current_config().backend in BACKENDS
    dialog.close()


def run_worker(task):
    results, failures = [], []
    worker = AiWorker(task)
    worker.result.connect(results.append)
    worker.failed.connect(failures.append)
    worker.start()
    worker.wait()
    wait_until(lambda: bool(results or failures), 2.0)
    return results, failures


def test_worker_reports_results_and_failures(qapp):
    assert AiWorker.run is AiWorker._run
    assert run_worker(lambda emit: 42) == ([42], [])
    assert run_worker(lambda emit: int("x"))[1][0].startswith("ValueError: ")

    def ai_failure(emit):
        raise AiError("quota exceeded")

    assert run_worker(ai_failure) == ([], ["quota exceeded"])


def test_status_text_and_rich_text_helpers():
    assert status_text(None, {}) == "Local model via Ollama (not connected yet)"
    backend = FakeBackend()
    backend.cost_per_token = (0.001, 0.002)
    backend.usage.add(1000, 500)
    assert (
        status_text(backend, {}, "done")
        == f"{FakeBackend.name}; this session about $2.00; done"
    )
    assert "1 to 2 minutes" in analyzing_html("<model>")
    assert "&lt;model&gt;" in analyzing_html("<model>")
    assert error_html("a\nb").count("<br>") == 1
    transcript = AiTranscript()
    transcript.add_question("<why>")
    assert "You: &lt;why&gt;" in transcript.html
    assert transcript.stream("one\n") and "one<br>" in transcript.stream("two")


def test_html_to_pdf(tmp_path, qapp):
    assert html_to_pdf(tmp_path / "missing.html") is None
    page = tmp_path / "report.html"
    page.write_text("<h1>Report</h1><p>Body</p>", encoding="utf-8")
    pdf = html_to_pdf(page)
    assert pdf == tmp_path / "report.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    assert READER == "Reader"
