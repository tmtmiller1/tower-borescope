"""AI tab: context, Analyze, answers, follow-up questions, report and settings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QLineEdit, QTextBrowser, QWidget

from tower_borescope.app.style import AI_PANEL_STYLE, MUTED_TEXT
from tower_borescope.app.widgets.layout import button, column, group, row, small_label

ANALYZE_LABEL: Final = "Analyze what's in view"
ANALYZING_LABEL: Final = "Analyzing..."
PANEL_MIN_HEIGHT: Final = 240
INTRO_HTML: Final = (
    f"<div style='color:{MUTED_TEXT}'>Point the scope at something and press "
    "<b>Analyze</b>. The AI will identify it, judge its condition, outline any problems "
    "on the picture and tell you what to do next. Then ask follow-up questions below. "
    "<b>Back to live</b> (or Esc) returns to the camera.</div>"
)

type Action = Callable[[], None]


def report_label(count: int) -> str:
    """Report button text for ``count`` collected views."""
    return f"Report ({count})..."


@dataclass(frozen=True, slots=True)
class AiActions:
    """Handlers for the AI tab controls.

    Attributes:
        analyze: Freeze and analyze the view.
        ask: Send the follow-up question.
        follow_link: Called with a clicked link in the answer panel.
        add_to_report: Keep the analyzed view for the report.
        write_report: Write the inspection report.
        open_settings: Open the AI settings dialog.
        back_to_live: Clear the boxes and return to the live camera.
    """

    analyze: Action
    ask: Action
    follow_link: Callable[[QUrl], None]
    add_to_report: Action
    write_report: Action
    open_settings: Action
    back_to_live: Action


class AiPanel:
    """Widgets of the AI tab.

    Attributes:
        context: Where the scope is looking, sent with the analysis.
        analyze_btn: Analyze button.
        browser: Answer panel; refuses focus so Space still unfreezes.
        question: Follow-up question field.
        ask_btn: Ask button.
        add_btn: Add to report button.
        report_btn: Report button showing the number of collected views.
        status: Backend name and session cost.
        widget: The tab contents.
    """

    def __init__(self, actions: AiActions) -> None:
        self.context = QLineEdit()
        self.context.setPlaceholderText(
            "Where is this? e.g. under the kitchen sink, drain trap"
        )
        self.context.setClearButtonEnabled(True)
        self.analyze_btn = button(
            ANALYZE_LABEL,
            actions.analyze,
            name="primary",
            tip="Freezes the frame and asks the AI what it is, what condition it's in "
            "and what to do.",
        )
        self.browser = self._browser(actions)
        self.question = QLineEdit()
        self.question.setPlaceholderText("Ask a follow-up... (Enter)")
        self.question.returnPressed.connect(actions.ask)
        self.ask_btn = button("Ask", actions.ask)
        self.add_btn = button(
            "Add to report",
            actions.add_to_report,
            "Keeps this view and its analysis for the inspection report.",
        )
        self.report_btn = button(
            report_label(0),
            actions.write_report,
            "Writes an HTML + PDF inspection report from the views you added.",
        )
        self.status = small_label()
        self.widget = self._layout(actions)

    @staticmethod
    def _browser(actions: AiActions) -> QTextBrowser:
        """The read-only answer panel with in-app link handling."""
        browser = QTextBrowser()
        browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        browser.anchorClicked.connect(actions.follow_link)
        browser.setMinimumHeight(PANEL_MIN_HEIGHT)
        browser.setStyleSheet(AI_PANEL_STYLE)
        browser.setHtml(INTRO_HTML)
        return browser

    def _layout(self, actions: AiActions) -> QWidget:
        """The ASK CLAUDE group in a column."""
        live = button(
            "Back to live",
            actions.back_to_live,
            "Clears the AI boxes and returns to the live camera (Esc).",
        )
        return column(
            group(
                "ASK CLAUDE",
                self.context,
                self.analyze_btn,
                self.browser,
                row(self.question, self.ask_btn),
                row(self.add_btn, self.report_btn),
                row(button("AI settings...", actions.open_settings), live),
                self.status,
            )
        )

    def set_busy(self, busy: bool) -> None:
        """Disable Analyze and Ask while a request runs."""
        self.analyze_btn.setEnabled(not busy)
        self.ask_btn.setEnabled(not busy)
        self.analyze_btn.setText(ANALYZING_LABEL if busy else ANALYZE_LABEL)

    def show_html(self, html: str) -> None:
        """Replace the answer panel contents and scroll to the end."""
        self.browser.setHtml(html)
        bar = self.browser.verticalScrollBar()
        bar.setValue(bar.maximum())
