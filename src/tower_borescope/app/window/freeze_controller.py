"""Freezing the view and every way back to the live camera."""

from __future__ import annotations

from typing import Final

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton

from tower_borescope.app.window.context import WindowContext
from tower_borescope.image_types import BgrImage

FROZEN_TOAST: Final = "Frozen: measure, annotate or analyze; Esc or Space for live"
LIVE_TOAST: Final = "Live"


class FreezeController:
    """Holds a frozen frame and keeps the freeze button and menu item in step.

    Attributes:
        ctx: Shared window state.
        frozen_frame: Copy of the processed frame taken when freezing, or None.
    """

    def __init__(self, ctx: WindowContext) -> None:
        self.ctx = ctx
        self.frozen_frame: BgrImage | None = None
        self._indicators: list[QAbstractButton | QAction] = []

    def add_indicator(self, control: QAbstractButton | QAction) -> None:
        """Check ``control`` whenever the view is frozen."""
        self._indicators.append(control)
        control.setChecked(self.ctx.view.frozen)

    def set_frozen(self, frozen: bool) -> None:
        """Freeze or unfreeze the view; unfreezing also clears the AI boxes.

        Args:
            frozen: True holds the current frame.
        """
        view = self.ctx.view
        last = self.ctx.pipeline.last_frame
        if frozen and last is not None:
            self.frozen_frame = last.copy()
        view.set_frozen(frozen)
        if not frozen:
            view.ai_boxes = []
        for control in self._indicators:
            control.setChecked(frozen)
        view.update()

    def freeze_for_analysis(self) -> BgrImage | None:
        """Freeze on the latest frame unless a frozen frame is held, and return it.

        Returns:
            The frozen frame, or None before the first frame arrives.
        """
        if not self.ctx.view.frozen or self.frozen_frame is None:
            self.set_frozen(True)
        return self.frozen_frame

    def toggle_freeze(self) -> None:
        """Freeze a live view or return a frozen one to live, with a toast."""
        self.set_frozen(not self.ctx.view.frozen)
        self.ctx.toast(FROZEN_TOAST if self.ctx.view.frozen else LIVE_TOAST)

    def back_to_live(self) -> None:
        """Clear the AI boxes and unfreeze (Back to live, Esc, the FROZEN badge)."""
        was_frozen = self.ctx.view.frozen
        self.set_frozen(False)
        if was_frozen:
            self.ctx.toast(LIVE_TOAST)
