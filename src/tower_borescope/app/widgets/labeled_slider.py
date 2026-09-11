"""Slider with a title on the left, the live value on the right and double-click reset."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QGridLayout, QLabel, QSlider, QWidget

from tower_borescope.app.widgets.layout import MUTED_LABEL

type ValueFormat = Callable[[float], str]
type ValueCallback = Callable[[float], object]


@dataclass(frozen=True, slots=True)
class SliderSpec:
    """Range and presentation of a labeled slider.

    Attributes:
        title: Text on the left above the slider.
        minimum: Lowest slider position.
        maximum: Highest slider position.
        fmt: Formats the scaled value for the label on the right.
        scale: Factor from slider position to value.
    """

    title: str
    minimum: int
    maximum: int
    fmt: ValueFormat
    scale: float = 1.0


class LabeledSlider(QWidget):
    """A horizontal slider that shows its value and resets on double click.

    Construction sets the initial value without calling ``on_change``.

    Attributes:
        spec: Range, title and value format.
        default: Value restored by a double click.
        on_change: Called with the new value after user or programmatic changes.
        title: Title label.
        value_label: Label showing the formatted value.
        slider: The slider, which refuses keyboard focus.
    """

    def __init__(
        self, spec: SliderSpec, value: float, on_change: ValueCallback | None = None
    ) -> None:
        super().__init__()
        self.spec = spec
        self.default = value
        self.on_change = on_change
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(2)
        self.title = QLabel(spec.title)
        self.value_label = QLabel()
        self.value_label.setObjectName(MUTED_LABEL)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(spec.minimum, spec.maximum)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.valueChanged.connect(self._changed)
        layout.addWidget(self.title, 0, 0)
        layout.addWidget(self.value_label, 0, 1)
        layout.addWidget(self.slider, 1, 0, 1, 2)
        self.set_value(value, silent=True)

    def value(self) -> float:
        """Current value: the slider position times the scale."""
        return self.slider.value() * self.spec.scale

    def set_value(self, value: float, silent: bool = False) -> None:
        """Move the slider to ``value``, clamped to the range.

        Args:
            value: New value in scaled units.
            silent: When True, ``on_change`` is not called.
        """
        self.slider.blockSignals(silent)
        self.slider.setValue(round(value / self.spec.scale))
        self.slider.blockSignals(False)
        self.value_label.setText(self.spec.fmt(self.value()))

    def _changed(self, _position: int) -> None:
        """Refresh the value label and notify the owner."""
        self.value_label.setText(self.spec.fmt(self.value()))
        if self.on_change is not None:
            self.on_change(self.value())

    def _mouse_double_click_event(self, _event: QMouseEvent) -> None:
        """Restore the default value."""
        self.set_value(self.default)

    mouseDoubleClickEvent = _mouse_double_click_event
