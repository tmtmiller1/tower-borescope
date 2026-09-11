"""AI tab logic: the backend, the background worker, analysis and follow-up questions.

Every model request runs in an :class:`AiWorker` thread. Its signals reach the GUI
thread through :class:`AiRunner`, a ``QObject`` living there, so result handlers may
update widgets directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtWidgets import QDialog

from tower_borescope.ai.base import AiError, Backend
from tower_borescope.ai.conversation import Conversation
from tower_borescope.ai.factory import make_backend
from tower_borescope.ai.images import encode_for_model
from tower_borescope.ai.schema import Analysis
from tower_borescope.ai.settings import AiConfig
from tower_borescope.app.dialogs.ai_settings import AiSettingsDialog
from tower_borescope.app.view.ai_boxes import boxes_from_analysis
from tower_borescope.app.window.ai_panel import AiActions, AiPanel
from tower_borescope.app.window.ai_transcript import (
    ASK_PREFIX,
    PENDING_HTML,
    AiTranscript,
    analyzing_html,
    error_html,
    status_text,
)
from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.freeze_controller import FreezeController
from tower_borescope.app.window.report_controller import ReportController
from tower_borescope.errors import BorescopeError

AI_TAB: Final = "AI"
SETTINGS_HINT: Final = "Open AI settings... to choose and configure a backend."
WORKER_ERRORS: Final = (
    BorescopeError,
    OSError,
    ValueError,
    RuntimeError,
    TypeError,
    KeyError,
)

type ChunkEmitter = Callable[[str], None]
type AiTask = Callable[[ChunkEmitter], object]
type ResultHandler = Callable[[object], None]
type TextHandler = Callable[[str], None]


def _ignore(_value: object) -> None:
    """Accept a value nobody asked for."""


class AiWorker(QThread):
    """Runs one AI request off the GUI thread.

    Attributes:
        chunk: Emits streamed answer text.
        result: Emits the task's return value.
        failed: Emits a message when the task raises.
        task: The request; it receives a function that emits ``chunk``.
    """

    chunk = Signal(str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, task: AiTask) -> None:
        super().__init__()
        self.task = task

    def _run(self) -> None:
        """Run the task and report its result or failure."""
        try:
            value = self.task(self.chunk.emit)
        except AiError as error:
            self.failed.emit(str(error))
            return
        except WORKER_ERRORS as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.result.emit(value)

    run = _run


class AiRunner(QObject):
    """Starts workers one at a time and delivers their signals on the GUI thread.

    Attributes:
        worker: The latest worker, or None before the first request.
    """

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.worker: AiWorker | None = None
        self._busy = False
        self._on_result: ResultHandler = _ignore
        self._on_failure: TextHandler = _ignore
        self._on_chunk: TextHandler = _ignore

    def busy(self) -> bool:
        """True while a request has not delivered its result or failure."""
        return self._busy

    def run(
        self,
        task: AiTask,
        on_result: ResultHandler,
        on_failure: TextHandler,
        on_chunk: TextHandler | None = None,
    ) -> bool:
        """Start ``task`` unless another request is running.

        Args:
            task: The request to run on the worker thread.
            on_result: Receives the task's return value on the GUI thread.
            on_failure: Receives the failure message on the GUI thread.
            on_chunk: Receives streamed text on the GUI thread, or None.

        Returns:
            True when the task started.
        """
        if self._busy:
            return False
        self.wait()
        self._busy = True
        self._on_result, self._on_failure = on_result, on_failure
        self._on_chunk = on_chunk or _ignore
        worker = AiWorker(task)
        worker.chunk.connect(self._deliver_chunk)
        worker.result.connect(self._deliver_result)
        worker.failed.connect(self._deliver_failure)
        self.worker = worker
        worker.start()
        return True

    def wait(self) -> None:
        """Block until the latest worker thread has ended."""
        if self.worker is not None:
            self.worker.wait()

    def _deliver_chunk(self, text: str) -> None:
        """Pass streamed text on."""
        self._on_chunk(text)

    def _deliver_result(self, value: object) -> None:
        """Mark the request done and pass its result on."""
        self._busy = False
        self._on_result(value)

    def _deliver_failure(self, message: str) -> None:
        """Mark the request done and pass its failure on."""
        self._busy = False
        self._on_failure(message)


class AiController:
    """Builds the backend lazily and runs analyses and follow-up questions.

    Attributes:
        ctx: Shared window state.
        freeze: Freezing and back to live.
        backend: The connected backend, or None until first needed.
        conversation: The current analysis conversation, or None.
        runner: Worker management.
        transcript: Follow-up questions and answers.
        report: Inspection report collection and writing.
        panel: The AI tab widgets.
    """

    def __init__(
        self,
        ctx: WindowContext,
        freeze: FreezeController,
        show_tab: Callable[[str], None],
    ) -> None:
        self.ctx = ctx
        self.freeze = freeze
        self._show_tab = show_tab
        self.backend: Backend | None = None
        self.conversation: Conversation | None = None
        self.runner = AiRunner(ctx.window)
        self.transcript = AiTranscript()
        self.report = ReportController(ctx, self)
        actions = AiActions(
            analyze=self.analyze,
            ask=self.ask,
            follow_link=self.follow_link,
            add_to_report=self.report.add_view,
            write_report=self.report.write,
            open_settings=self.open_settings,
            back_to_live=freeze.back_to_live,
        )
        self.panel = AiPanel(actions)
        self.update_status()

    def update_status(self, extra: str = "") -> None:
        """Show the backend and session cost under the panel."""
        self.panel.status.setText(status_text(self.backend, self.ctx.prefs.values, extra))

    def open_settings(self) -> None:
        """Open AI settings; saving them disconnects the current backend."""
        dialog = AiSettingsDialog(self.ctx.prefs.values, self.ctx.window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.ctx.prefs.remember(**dialog.current_config().to_dict())
            self.backend = None
            self.update_status()
            self.ctx.toast("AI settings saved")

    def client(self) -> Backend | None:
        """The configured backend, built on first use; failures show in the panel."""
        if self.backend is None:
            try:
                self.backend = make_backend(AiConfig.from_settings(self.ctx.prefs.values))
            except AiError as error:
                self.ctx.toast(str(error))
                self.panel.show_html(error_html(f"{error}\n\n{SETTINGS_HINT}"))
                return None
            self.update_status()
        return self.backend

    def focus_question(self) -> None:
        """Show the AI tab and put the cursor in the follow-up field."""
        self._show_tab(AI_TAB)
        self.panel.question.setFocus()

    def analyze(self) -> None:
        """Freeze the view and analyze the frozen frame."""
        if self.runner.busy():
            return
        client = self.client()
        if client is None:
            return
        if self.ctx.pipeline.last_frame is None:
            self.ctx.toast("No video yet")
            return
        frame = self.freeze.freeze_for_analysis()
        if frame is None:
            return
        self.ctx.view.ai_boxes = []
        self._show_tab(AI_TAB)
        jpeg = encode_for_model(frame, client.max_image_width)
        conversation = Conversation(
            client, jpeg, self.panel.context.text(), self.ctx.view.mm_per_px
        )
        self.conversation = conversation
        self.transcript.clear()
        self.panel.show_html(analyzing_html(client.describe()))
        self.panel.set_busy(True)
        self.runner.run(
            lambda _emit: conversation.analyze(), self._analysis_ready, self.show_failure
        )

    def _analysis_ready(self, value: object) -> None:
        """Draw the issue boxes and show the analysis."""
        self.panel.set_busy(False)
        if not isinstance(value, Analysis):
            self.show_failure("The AI returned no analysis.")
            return
        self.ctx.view.ai_boxes = boxes_from_analysis(value)
        self.ctx.view.update()
        self._render()
        self.update_status()
        worst = value.issues[0].severity if value.issues else "none"
        self.ctx.toast(f"{value.subject}: {len(value.issues)} issue(s), worst {worst}")

    def _render(self, extra_html: str = "") -> None:
        """Show the analysis and transcript in the panel."""
        conversation = self.conversation
        if conversation is not None and conversation.analysis is not None:
            self.panel.show_html(
                self.transcript.render(conversation.analysis, extra_html)
            )

    def follow_link(self, url: QUrl) -> None:
        """Ask a suggested question when its link is clicked."""
        text = url.toString()
        if text.startswith(ASK_PREFIX):
            self.panel.question.setText(text[len(ASK_PREFIX) :])
            self.ask()

    def ask(self) -> None:
        """Send the follow-up question and stream the answer into the panel."""
        question = self.panel.question.text().strip()
        conversation = self.conversation
        if not question:
            return
        if conversation is None or conversation.analysis is None:
            self.ctx.toast("Analyze a view first, then ask about it")
            return
        if self.runner.busy():
            return
        self.panel.question.clear()
        self.transcript.add_question(question)
        self.panel.set_busy(True)
        self._render(PENDING_HTML)
        self.runner.run(
            lambda emit: conversation.ask(question, emit),
            self._answer_done,
            self.show_failure,
            on_chunk=self._chunk,
        )

    def _chunk(self, text: str) -> None:
        """Show the answer as it arrives."""
        self._render(self.transcript.stream(text))

    def _answer_done(self, value: object) -> None:
        """Keep the complete answer in the transcript."""
        self.panel.set_busy(False)
        self.transcript.add_answer(str(value))
        self._render()
        self.update_status()

    def show_failure(self, message: str) -> None:
        """Show a failed request in the panel."""
        self.panel.set_busy(False)
        self.panel.show_html(error_html(message))
        self.ctx.toast("AI request failed")
