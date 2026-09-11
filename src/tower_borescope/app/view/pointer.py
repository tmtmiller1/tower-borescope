"""Mouse and wheel dispatch for the video view.

A left click on the FROZEN badge asks for live video, a click near the split-compare
divider drags it, a click with a tool goes to the tool controller, and any other left
drag pans the zoomed image. The wheel zooms about the pointer and a double click
resets the zoom or closes an area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent

from tower_borescope.app.view.geometry import (
    ZOOM_MIN,
    split_fraction,
    split_position,
    wheel_zoom,
)
from tower_borescope.app.view.tools import AREA_TOOL

if TYPE_CHECKING:
    from tower_borescope.app.view.video_view import VideoView

SPLIT_GRAB_PIXELS = 12.0
COMPARE_SPLIT = "split"


def _on_live_badge(view: VideoView, pos: QPointF) -> bool:
    """True when ``pos`` is on the painted FROZEN badge."""
    rect = view.live_badge_rect
    return view.frozen and rect is not None and rect.contains(pos)


def _near_split(view: VideoView, pos: QPointF) -> bool:
    """True when ``pos`` is close enough to grab the split divider."""
    divider = split_position(view.image_rect(), view.split)
    return abs(pos.x() - divider) < SPLIT_GRAB_PIXELS


def _split_cursor(view: VideoView, pos: QPointF) -> Qt.CursorShape:
    """Cursor for split-compare mode: a resize arrow over the divider."""
    if _near_split(view, pos):
        return Qt.CursorShape.SplitHCursor
    if view.tool:
        return Qt.CursorShape.CrossCursor
    return Qt.CursorShape.OpenHandCursor


def _drag_tool(view: VideoView, event: QMouseEvent) -> None:
    """Pass pointer movement to the tool controller."""
    mapper = view.mapper()
    if mapper is None:
        return
    left_down = bool(event.buttons() & Qt.MouseButton.LeftButton)
    view.tools.drag(mapper.to_image(event.position()), left_down)
    view.update()


class PointerHandler:
    """Routes mouse and wheel events of one :class:`VideoView`."""

    def __init__(self, view: VideoView) -> None:
        """Bind the handler to its view.

        Args:
            view: Widget whose state the events change.
        """
        self._view = view
        self._drag_from: tuple[QPointF, QPointF] | None = None
        self._drag_split = False

    def press(self, event: QMouseEvent) -> None:
        """Handle a mouse button press."""
        view = self._view
        if view.image is None:
            return
        pos = event.position()
        button = event.button()
        if button == Qt.MouseButton.RightButton:
            if view.tool:
                view.tools.close_area_or_cancel()
                view.update()
        elif button == Qt.MouseButton.LeftButton:
            if _on_live_badge(view, pos):
                view.live_requested.emit()
            else:
                self._press_left(pos)

    def move(self, event: QMouseEvent) -> None:
        """Handle pointer movement: divider drag, pan, tool preview or cursor shape."""
        view = self._view
        if view.image is None:
            return
        pos = event.position()
        if self._drag_split:
            view.split = split_fraction(view.image_rect(), pos.x())
            view.update()
        elif self._drag_from is not None and view.zoom > ZOOM_MIN:
            start, pan = self._drag_from
            view.pan = pan + (pos - start)
            view.update()
        elif view.tool and view.overlays.current is not None:
            _drag_tool(view, event)
        elif view.compare_mode == COMPARE_SPLIT:
            view.setCursor(_split_cursor(view, pos))

    def release(self, event: QMouseEvent) -> None:
        """End drags and finish dragged annotations."""
        view = self._view
        self._drag_split = False
        self._drag_from = None
        if not view.tool:
            view.setCursor(Qt.CursorShape.OpenHandCursor)
        elif view.tools.release():
            view.update()

    def double_click(self, event: QMouseEvent) -> None:
        """Close an area with the area tool, or reset the zoom without a tool."""
        view = self._view
        if view.tool == AREA_TOOL:
            view.tools.close_area_or_cancel()
            view.update()
        elif not view.tool:
            view.set_zoom(ZOOM_MIN)

    def wheel(self, event: QWheelEvent) -> None:
        """Zoom about the pointer."""
        view = self._view
        if view.image is None:
            return
        zoom = wheel_zoom(view.zoom, event.angleDelta().y())
        view.set_zoom(zoom, event.position())

    def _press_left(self, pos: QPointF) -> None:
        """Start a divider drag, a tool action or a pan."""
        view = self._view
        mapper = view.mapper()
        if view.compare_mode == COMPARE_SPLIT and _near_split(view, pos):
            self._drag_split = True
        elif view.tool and mapper is not None:
            view.tools.press(view.tool, mapper.to_image(pos))
            view.update()
        else:
            self._drag_from = (pos, QPointF(view.pan))
            view.setCursor(Qt.CursorShape.ClosedHandCursor)
