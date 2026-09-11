"""Image tab: color, detail filters, view mode and reset."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel

from tower_borescope.app.pipeline.state import PipelineState
from tower_borescope.app.widgets.labeled_slider import LabeledSlider, SliderSpec
from tower_borescope.app.widgets.layout import button, checkbox, column, group, row
from tower_borescope.imaging.view_modes import VIEW_MODES

PERCENT: Final = 100

type Toggle = Callable[[bool], None]


def _signed(value: float) -> str:
    """A brightness offset with its sign."""
    return f"{value:+.0f}"


def _factor(value: float) -> str:
    """A percentage slider value shown as a factor."""
    return f"{value / PERCENT:.2f}"


def _percent(value: float) -> str:
    """A percentage slider value."""
    return f"{value:.0f}%"


BRIGHTNESS_SPEC: Final = SliderSpec("Brightness", -100, 100, _signed)
CONTRAST_SPEC: Final = SliderSpec("Contrast", 50, 200, _factor)
SATURATION_SPEC: Final = SliderSpec("Saturation", 0, 200, _factor)
GLARE_SPEC: Final = SliderSpec("Glare reduction", 0, 100, _percent)
DENOISE_SPEC: Final = SliderSpec("Temporal denoise", 0, 90, _percent)


@dataclass(frozen=True, slots=True)
class ImageActions:
    """Handlers for the Image tab controls.

    Attributes:
        set_enhance: Enhance switch.
        set_awb: Auto white balance switch.
        set_grade: Called with a color control name and its value.
        set_filter: Called with ``"glare"`` or ``"denoise"`` and a strength from 0 to 1.
        set_stabilize: Stabilization switch.
        set_view_mode: Called with the view mode name.
        reset: Reset every image setting.
    """

    set_enhance: Toggle
    set_awb: Toggle
    set_grade: Callable[[str, float], None]
    set_filter: Callable[[str, float], None]
    set_stabilize: Toggle
    set_view_mode: Callable[[str], None]
    reset: Callable[[], None]


class ImagePanel:
    """Widgets of the Image tab.

    Attributes:
        awb_check: Auto white balance switch.
        brightness: Brightness slider.
        contrast: Contrast slider in percent.
        saturation: Saturation slider in percent.
        enhance_check: Enhance switch.
        stabilize_check: Stabilization switch.
        denoise: Temporal denoise slider in percent.
        glare: Glare reduction slider in percent.
        mode_combo: View mode choice.
        widget: The tab contents.
    """

    def __init__(self, actions: ImageActions, state: PipelineState) -> None:
        self._color_controls(actions, state)
        self._detail_controls(actions, state)
        reset = button(
            "Reset image settings",
            actions.reset,
            "Double-click any slider to reset just that one.",
        )
        self.widget = column(
            group(
                "COLOR", self.awb_check, self.brightness, self.contrast, self.saturation
            ),
            group(
                "DETAIL",
                self.enhance_check,
                self.stabilize_check,
                self.denoise,
                self.glare,
                row(QLabel("View mode"), self.mode_combo),
            ),
            reset,
        )

    def _color_controls(self, actions: ImageActions, state: PipelineState) -> None:
        """White balance switch and the brightness, contrast and saturation sliders."""
        grade = state.grade
        self.awb_check = checkbox("Auto white balance", grade.awb, actions.set_awb)
        self.brightness = LabeledSlider(
            BRIGHTNESS_SPEC,
            grade.brightness,
            lambda v: actions.set_grade("brightness", int(v)),
        )
        self.contrast = LabeledSlider(
            CONTRAST_SPEC,
            grade.contrast * PERCENT,
            lambda v: actions.set_grade("contrast", round(v / PERCENT, 2)),
        )
        self.saturation = LabeledSlider(
            SATURATION_SPEC,
            grade.saturation * PERCENT,
            lambda v: actions.set_grade("saturation", round(v / PERCENT, 2)),
        )

    def _detail_controls(self, actions: ImageActions, state: PipelineState) -> None:
        """Enhance, stabilization, denoise, glare and the view mode choice."""
        self.enhance_check = checkbox(
            "Enhance  (deblock, contrast, sharpen)", state.enhanced, actions.set_enhance
        )
        self.glare = LabeledSlider(
            GLARE_SPEC,
            state.glare * PERCENT,
            lambda v: actions.set_filter("glare", round(v / PERCENT, 2)),
        )
        self.denoise = LabeledSlider(
            DENOISE_SPEC,
            state.denoise * PERCENT,
            lambda v: actions.set_filter("denoise", round(v / PERCENT, 2)),
        )
        self.denoise.setToolTip(
            "Averages the picture over time where nothing moves. "
            "Cleaner still shots; slight trails on motion."
        )
        self.stabilize_check = checkbox(
            "Stabilize handheld shake", state.stabilize, actions.set_stabilize
        )
        self.mode_combo = QComboBox()
        self.mode_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_combo.addItems(list(VIEW_MODES))
        self.mode_combo.setCurrentText(state.view_mode)
        self.mode_combo.currentTextChanged.connect(actions.set_view_mode)
