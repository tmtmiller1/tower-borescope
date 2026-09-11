"""Rotation, mirror, grid, view zoom, the sidebar and full screen."""

from __future__ import annotations

from typing import Final

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.view_panel import OrientationActions, OrientationGroup
from tower_borescope.imaging.geometry import ROTATIONS

ROTATE_BLOCKED_TOAST: Final = "Stop recording before rotating (it changes the video size)"


class ViewController:
    """Handlers for the VIEW group and the window layout toggles.

    Attributes:
        ctx: Shared window state.
        sidebar: The controls column beside the video.
        orientation: The VIEW group.
        menu_actions: Checkable menu items keyed by name, once the menus exist.
    """

    def __init__(self, ctx: WindowContext, sidebar: QWidget) -> None:
        self.ctx = ctx
        self.sidebar = sidebar
        actions = OrientationActions(
            rotate_left=self.rotate_left,
            rotate_right=self.rotate_right,
            set_mirror=self.set_mirror,
            set_grid=self.set_grid,
            set_zoom=ctx.view.set_zoom,
        )
        self.orientation = OrientationGroup(actions, ctx.pipeline.state.mirror)
        self.menu_actions: dict[str, QAction] = {}

    def _sync(self, name: str, on: bool) -> None:
        """Check or uncheck the menu item for ``name``."""
        action = self.menu_actions.get(name)
        if action is not None:
            action.setChecked(on)

    def rotate(self, direction: int) -> None:
        """Rotate by quarter turns; refused while recording processed video.

        Args:
            direction: 1 for clockwise, -1 for counter-clockwise.
        """
        pipeline = self.ctx.pipeline
        if pipeline.recording and not pipeline.state.raw_recording:
            self.ctx.toast(ROTATE_BLOCKED_TOAST)
            return
        pipeline.state.rotation = (pipeline.state.rotation + direction) % len(ROTATIONS)
        pipeline.reset_stabilizer()
        self.ctx.view.overlays.clear()
        self.ctx.prefs.remember(rotation=pipeline.state.rotation)

    def rotate_left(self) -> None:
        """Rotate a quarter turn counter-clockwise."""
        self.rotate(-1)

    def rotate_right(self) -> None:
        """Rotate a quarter turn clockwise."""
        self.rotate(1)

    def set_mirror(self, on: bool) -> None:
        """Mirror the picture; measurements no longer match and are cleared."""
        self.ctx.pipeline.state.mirror = on
        self._sync("mirror", on)
        self.ctx.view.overlays.clear()
        self.ctx.prefs.remember(mirror=on)

    def set_grid(self, on: bool) -> None:
        """Show or hide the grid and crosshair."""
        self.ctx.view.grid = on
        self._sync("grid", on)
        self.ctx.view.update()

    def toggle_sidebar(self) -> None:
        """Show or hide the controls."""
        self.sidebar.setVisible(self.sidebar.isHidden())
        self._sync("sidebar", not self.sidebar.isHidden())

    def toggle_fullscreen(self) -> None:
        """Enter full screen without controls, or return to the normal window."""
        window = self.ctx.window
        if window.isFullScreen():
            window.showNormal()
            self.sidebar.setVisible(True)
        else:
            window.showFullScreen()
            self.sidebar.setVisible(False)
        self._sync("fullscreen", window.isFullScreen())
        self._sync("sidebar", not self.sidebar.isHidden())
