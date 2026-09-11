"""Mouse handling for the measurement and annotation tools.

Tools are named by strings: the measurement kinds ``distance``, ``angle`` and ``area``,
the annotation kinds ``arrow``, ``circle``, ``text`` and ``freehand``, and
``calibrate``, which measures a known length for the scale.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QInputDialog, QWidget

from tower_borescope.app.view.overlays import OverlayModel
from tower_borescope.measure.shapes import MEASURE_KINDS, Annotation, Measurement, Point

AREA_TOOL = "area"
CALIBRATE_TOOL = "calibrate"
TEXT_TOOL = "text"
FREEHAND_TOOL = "freehand"
DRAG_TOOLS: tuple[str, ...] = ("arrow", "circle", FREEHAND_TOOL)
MIN_AREA_POINTS = 3
MIN_DRAG_POINTS = 2


@dataclass(frozen=True, slots=True)
class ToolSignals:
    """Reports from the tools to the widget.

    Attributes:
        finished: A measurement or calibration was completed.
        calibrated: Pixel length measured by the calibrate tool.
    """

    finished: Callable[[], None]
    calibrated: Callable[[float], None]


def ask_text(parent: QWidget) -> str | None:
    """Ask for the text of a note.

    Args:
        parent: Dialog parent.

    Returns:
        The stripped text, or None when the dialog is cancelled or left blank.
    """
    text, ok = QInputDialog.getText(parent, "Text annotation", "Text:")
    stripped = text.strip()
    return stripped if ok and stripped else None


class ToolController:
    """Turns clicks and drags in image coordinates into overlay items."""

    def __init__(
        self, overlays: OverlayModel, signals: ToolSignals, parent: QWidget
    ) -> None:
        """Bind the controller to a model.

        Args:
            overlays: Model receiving the items.
            signals: Completion reports.
            parent: Parent for the text dialog.
        """
        self._overlays = overlays
        self._signals = signals
        self._parent = parent

    def press(self, tool: str, point: Point) -> None:
        """Handle a left click with ``tool`` at an image point.

        Args:
            tool: Active tool name.
            point: Clicked image coordinates.
        """
        if tool in MEASURE_KINDS:
            self._press_measure(tool, point)
        elif tool == CALIBRATE_TOOL:
            self._press_calibrate(point)
        elif tool == TEXT_TOOL:
            text = ask_text(self._parent)
            if text is not None:
                self._overlays.finish_item(Annotation(TEXT_TOOL, [point], text))
        elif tool in DRAG_TOOLS:
            self._overlays.current = Annotation(tool, [point])

    def drag(self, point: Point, left_down: bool) -> None:
        """Extend a dragged annotation, or track the pointer for a measurement preview.

        Args:
            point: Image coordinates under the pointer.
            left_down: Whether the left button is held.
        """
        current = self._overlays.current
        if not isinstance(current, Annotation):
            self._overlays.hover = point
        elif current.kind == FREEHAND_TOOL:
            if left_down:
                current.points.append(point)
        elif current.points:
            current.points = [current.points[0], point]

    def release(self) -> bool:
        """Finish a dragged arrow, circle or stroke when the button is released.

        Returns:
            True when a dragged annotation ended, whether or not it was kept.
        """
        current = self._overlays.current
        if not isinstance(current, Annotation) or current.kind not in DRAG_TOOLS:
            return False
        if len(current.points) >= MIN_DRAG_POINTS:
            self._overlays.finish_item(current)
        self._overlays.current = None
        return True

    def close_area_or_cancel(self) -> None:
        """Close an area of three or more corners, else drop the item in progress."""
        current = self._overlays.current
        if (
            isinstance(current, Measurement)
            and current.kind == AREA_TOOL
            and len(current.points) >= MIN_AREA_POINTS
        ):
            current.closed = True
            self._overlays.finish_item(current)
            self._signals.finished()
        self._overlays.current = None

    def _press_measure(self, tool: str, point: Point) -> None:
        """Add a point to a measurement, finishing it once complete."""
        current = self._overlays.current
        if not isinstance(current, Measurement):
            current = Measurement(tool)
            self._overlays.current = current
        current.add_point(point)
        if current.complete:
            self._overlays.finish_item(current)
            self._overlays.current = None
            self._signals.finished()

    def _press_calibrate(self, point: Point) -> None:
        """Add a point to the calibration line and report its pixel length when done."""
        current = self._overlays.current
        if not isinstance(current, Measurement):
            current = Measurement("distance")
            self._overlays.current = current
        current.add_point(point)
        pixels = current.pixel_value() if current.complete else None
        if pixels is not None:
            self._overlays.current = None
            self._signals.calibrated(pixels)
            self._signals.finished()
