"""Measurement and annotation model with undo history."""

from __future__ import annotations

from collections.abc import Callable

from tower_borescope.measure.shapes import (
    Annotation,
    Measurement,
    OverlaySnapshot,
    Point,
)

type OverlayItem = Measurement | Annotation


class OverlayModel:
    """Finished measurements and annotations, the item being drawn, and undo history.

    Attributes:
        measurements: Finished measurements, oldest first.
        annotations: Finished annotations, oldest first.
        current: Item being drawn with a tool, or None.
        hover: Image point under the pointer while a measurement is drawn, or None.
    """

    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        """Create an empty model.

        Args:
            on_change: Called after every change to the finished items.
        """
        self.measurements: list[Measurement] = []
        self.annotations: list[Annotation] = []
        self.current: OverlayItem | None = None
        self.hover: Point | None = None
        self._history: list[OverlayItem] = []
        self._on_change = on_change

    def finish_item(self, item: OverlayItem) -> None:
        """Add a finished item and remember it for undo.

        Args:
            item: A completed measurement or annotation.
        """
        if isinstance(item, Measurement):
            self.measurements.append(item)
        else:
            self.annotations.append(item)
        self._history.append(item)
        self._changed()

    def undo(self) -> None:
        """Drop the item being drawn, else remove the most recently finished one."""
        if self.current is not None:
            self.current = None
        elif self._history:
            self._remove(self._history.pop())
        self._changed()

    def clear(self) -> None:
        """Remove every item, including the one being drawn."""
        self.measurements = []
        self.annotations = []
        self.current = None
        self._history = []
        self._changed()

    def clear_measurements(self) -> None:
        """Remove every finished measurement, keeping the annotations."""
        self.measurements = []
        self._history = [item for item in self._history if isinstance(item, Annotation)]
        self._changed()

    def clear_annotations(self) -> None:
        """Remove every finished annotation, keeping the measurements."""
        self.annotations = []
        self._history = [item for item in self._history if isinstance(item, Measurement)]
        self._changed()

    def snapshot(self, mm_per_px: float | None, unit: str) -> OverlaySnapshot:
        """Copy of the finished items for saving or rendering.

        Args:
            mm_per_px: Image scale for labels, or None to label in pixels.
            unit: A key of ``measure.units.UNITS``.

        Returns:
            A frozen snapshot holding new lists of the same items.
        """
        return OverlaySnapshot(
            list(self.measurements), list(self.annotations), mm_per_px, unit
        )

    def _remove(self, item: OverlayItem) -> None:
        """Remove one finished item from its list, compared by identity."""
        if isinstance(item, Measurement):
            self.measurements = [kept for kept in self.measurements if kept is not item]
        else:
            self.annotations = [kept for kept in self.annotations if kept is not item]

    def _changed(self) -> None:
        """Notify the owner."""
        if self._on_change is not None:
            self._on_change()
