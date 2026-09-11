"""Reference images for split and overlay comparison with the live view."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog

from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.tools_panel import CompareActions, CompareGroup

COMPARE_MODES: Final = ("off", "split", "overlay")
SPLIT_INDEX: Final = 1
PERCENT: Final = 100.0
IMAGE_FILTER: Final = "Images (*.png *.jpg *.jpeg)"
TOOLS_TAB: Final = "Tools"


class CompareController:
    """Loads a reference image and sets the compare mode and overlay opacity.

    Attributes:
        ctx: Shared window state.
        group: The FREEZE AND COMPARE group.
    """

    def __init__(
        self,
        ctx: WindowContext,
        toggle_freeze: Callable[[], None],
        show_gallery: Callable[[], None],
        show_tab: Callable[[str], None],
    ) -> None:
        self.ctx = ctx
        self._show_tab = show_tab
        actions = CompareActions(
            toggle_freeze=toggle_freeze,
            pick_reference=self.pick_reference,
            show_gallery=show_gallery,
            set_mode=self.set_mode,
            set_opacity=self.set_opacity,
        )
        self.group = CompareGroup(actions)

    def pick_reference(self) -> None:
        """Choose a reference image file."""
        path, _ = QFileDialog.getOpenFileName(
            self.ctx.window, "Reference image", str(self.ctx.paths.pictures), IMAGE_FILTER
        )
        if path:
            self.set_reference(path)

    def set_reference(self, path: str) -> None:
        """Load a reference image and show it split beside the live view.

        Args:
            path: Image file.
        """
        image = QImage(path)
        if image.isNull():
            self.ctx.toast("Could not load that image")
            return
        view = self.ctx.view
        view.compare_image = image.convertToFormat(QImage.Format.Format_RGB888)
        self.group.compare_label.setText("Reference: " + Path(path).name)
        if self.group.compare_combo.currentIndex() == 0:
            self.group.compare_combo.setCurrentIndex(SPLIT_INDEX)
        self._show_tab(TOOLS_TAB)
        view.update()

    def set_mode(self, index: int) -> None:
        """Apply the compare combo choice: off, split or overlay."""
        view = self.ctx.view
        view.compare_mode = COMPARE_MODES[index]
        if index and view.compare_image is None:
            self.ctx.toast("Choose a reference image first")
        view.update()

    def set_opacity(self, value: float) -> None:
        """Apply the overlay opacity, given in percent."""
        self.ctx.view.compare_opacity = value / PERCENT
        self.ctx.view.update()
