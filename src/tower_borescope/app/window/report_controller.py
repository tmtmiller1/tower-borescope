"""Inspection reports: collecting analyzed views and writing HTML and PDF files."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QPdfWriter, QTextDocument

from tower_borescope.ai.report import ReportEntry, write_report
from tower_borescope.app.window.ai_panel import report_label
from tower_borescope.app.window.context import WindowContext

if TYPE_CHECKING:
    from tower_borescope.app.window.ai_controller import AiController

PDF_SUFFIX: Final = ".pdf"
TIME_FORMAT: Final = "%Y-%m-%d %H:%M"
WRITING_LABEL: Final = "Writing..."


def html_to_pdf(html_path: Path) -> Path | None:
    """Print an HTML report to a PDF file next to it.

    Args:
        html_path: The HTML report.

    Returns:
        The PDF path, or None when the report cannot be read or nothing was written.
    """
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError:
        return None
    document = QTextDocument()
    document.setHtml(html)
    pdf_path = html_path.with_suffix(PDF_SUFFIX)
    writer = QPdfWriter(str(pdf_path))
    document.print_(writer)
    del writer
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        return None
    return pdf_path


class ReportController:
    """Keeps analyzed views and writes them into a report.

    Attributes:
        ctx: Shared window state.
        ai: The AI controller that owns the backend and the worker.
        entries: Views added so far.
    """

    def __init__(self, ctx: WindowContext, ai: AiController) -> None:
        self.ctx = ctx
        self.ai = ai
        self.entries: list[ReportEntry] = []

    def _show_count(self) -> None:
        """Show the number of collected views on the report button."""
        self.ai.panel.report_btn.setText(report_label(len(self.entries)))

    def add_view(self) -> None:
        """Keep the current view and its analysis for the report."""
        conversation = self.ai.conversation
        if conversation is None or conversation.analysis is None:
            self.ctx.toast("Analyze a view first")
            return
        entry = ReportEntry(
            jpeg=conversation.jpeg,
            analysis=conversation.analysis,
            context=conversation.context,
            time=time.strftime(TIME_FORMAT),
        )
        self.entries.append(entry)
        self._show_count()
        self.ctx.toast(f"Added to report ({len(self.entries)} view(s))")

    def write(self) -> None:
        """Write the HTML report in the background, then a PDF beside it."""
        if not self.entries:
            self.ctx.toast("Add at least one analyzed view to the report first")
            return
        if self.ai.runner.busy():
            return
        client = self.ai.client()
        if client is None:
            return
        entries = list(self.entries)
        self.ai.panel.set_busy(True)
        self.ai.panel.report_btn.setText(WRITING_LABEL)
        self.ai.runner.run(
            lambda _emit: write_report(client, entries), self._written, self._failed
        )

    def _failed(self, message: str) -> None:
        """Restore the button and show the failure."""
        self._show_count()
        self.ai.show_failure(message)

    def _written(self, value: object) -> None:
        """Print the PDF, announce the report and open it."""
        self.ai.panel.set_busy(False)
        self._show_count()
        path = Path(str(value))
        pdf = html_to_pdf(path)
        suffix = " + PDF" if pdf is not None else ""
        self.ctx.toast(f"Report saved: {path.name}{suffix}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.ai.update_status()
