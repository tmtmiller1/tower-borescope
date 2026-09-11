"""Tools tab: freeze and compare, measurement and annotation tools, and meters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QWidget

from tower_borescope.app.widgets.labeled_slider import LabeledSlider, SliderSpec
from tower_borescope.app.widgets.layout import (
    button,
    checkbox,
    column,
    group,
    row,
    small_label,
)
from tower_borescope.measure.units import UNITS

MEASURE_TOOLS: Final = (("distance", "Distance"), ("angle", "Angle"), ("area", "Area"))
ANNOTATE_TOOLS: Final = (
    ("arrow", "Arrow"),
    ("circle", "Circle"),
    ("text", "Text"),
    ("freehand", "Draw"),
)
COMPARE_CHOICES: Final = ("Compare off", "Split", "Overlay")
NO_REFERENCE_TEXT: Final = "No reference image."
SCALE_AI_LABEL: Final = "Estimate scale with AI"
DEFAULT_OPACITY: Final = 50

type Action = Callable[[], None]
type Toggle = Callable[[bool], None]


def _percent(value: float) -> str:
    """A percentage slider value."""
    return f"{value:.0f}%"


OPACITY_SPEC: Final = SliderSpec("Overlay opacity", 0, 100, _percent)


@dataclass(frozen=True, slots=True)
class CompareActions:
    """Handlers for the FREEZE AND COMPARE group.

    Attributes:
        toggle_freeze: Freeze or unfreeze the view.
        pick_reference: Choose a reference image file.
        show_gallery: Open the gallery to choose a reference.
        set_mode: Called with the compare combo index.
        set_opacity: Called with the overlay opacity in percent.
    """

    toggle_freeze: Action
    pick_reference: Action
    show_gallery: Action
    set_mode: Callable[[int], None]
    set_opacity: Callable[[float], None]


class CompareGroup:
    """Freeze button, reference choice, compare mode and overlay opacity.

    Attributes:
        freeze_btn: Checkable freeze button.
        compare_label: Name of the reference image.
        compare_combo: Compare off, split or overlay.
        compare_opacity: Overlay opacity slider.
        box: The group box.
    """

    def __init__(self, actions: CompareActions) -> None:
        self.freeze_btn = button("Freeze  (Space)", actions.toggle_freeze, checkable=True)
        self.compare_combo = QComboBox()
        self.compare_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.compare_combo.addItems(list(COMPARE_CHOICES))
        self.compare_combo.currentIndexChanged.connect(actions.set_mode)
        self.compare_opacity = LabeledSlider(
            OPACITY_SPEC, DEFAULT_OPACITY, actions.set_opacity
        )
        self.compare_label = small_label(NO_REFERENCE_TEXT)
        self.box = group(
            "FREEZE AND COMPARE",
            self.freeze_btn,
            row(
                button("Reference from file...", actions.pick_reference),
                button("From gallery...", actions.show_gallery),
            ),
            self.compare_label,
            self.compare_combo,
            self.compare_opacity,
        )


@dataclass(frozen=True, slots=True)
class MeasureActions:
    """Handlers for the MEASURE AND ANNOTATE group.

    Attributes:
        toggle_tool: Called with a tool name; picks it, or drops it when active.
        undo: Remove the last measurement or annotation.
        clear: Remove every measurement and annotation.
        set_unit: Called with the unit combo index.
        calibrate: Start the calibration tool.
        estimate_scale: Ask the AI for a scale estimate.
    """

    toggle_tool: Callable[[str], None]
    undo: Action
    clear: Action
    set_unit: Callable[[int], None]
    calibrate: Action
    estimate_scale: Action


def _tool_slot(toggle: Callable[[str], None], key: str) -> Action:
    """A click handler that toggles the tool ``key``."""

    def slot() -> None:
        toggle(key)

    return slot


class MeasureGroup:
    """Tool buttons, undo and clear, units, calibration and scale status.

    Attributes:
        tool_buttons: Checkable tool buttons keyed by tool name.
        keep_check: Keeps earlier items when a new tool is picked.
        burn_check: Saves an annotated copy with snapshots.
        unit_combo: Unit choice; item data holds the unit key.
        scale_ai_btn: AI scale estimate button.
        calibration_label: Scale and field of view for the current resolution.
        scale_state: Focus lock status of the scale.
        box: The group box.
    """

    def __init__(self, actions: MeasureActions, unit: str) -> None:
        self.tool_buttons: dict[str, QPushButton] = {}
        rows = [
            self._tool_row(actions, tools) for tools in (MEASURE_TOOLS, ANNOTATE_TOOLS)
        ]
        self.keep_check = checkbox(
            "Keep previous when starting a new one",
            False,
            _ignore,
            "Off: picking a measure tool clears earlier measurements "
            "(annotation tools clear earlier annotations).",
        )
        self.burn_check = checkbox("Save an annotated copy with snapshots", True, _ignore)
        self.unit_combo = self._unit_combo(unit)
        self.unit_combo.currentIndexChanged.connect(actions.set_unit)
        self.scale_ai_btn = button(
            SCALE_AI_LABEL,
            actions.estimate_scale,
            "Claude finds something of standard size in view "
            "(a nut, screw head, pipe...) and proposes a scale.",
        )
        calibrate = button(
            "Calibrate scale...",
            actions.calibrate,
            "Click both ends of something of known length at your working distance, "
            "ideally at peak focus.",
        )
        self.calibration_label = small_label()
        self.scale_state = small_label()
        self.box = group(
            "MEASURE AND ANNOTATE",
            *rows,
            row(button("Undo", actions.undo), button("Clear", actions.clear)),
            self.keep_check,
            self.burn_check,
            row(QLabel("Units"), self.unit_combo),
            row(calibrate, self.scale_ai_btn),
            self.calibration_label,
            self.scale_state,
        )

    def _tool_row(
        self, actions: MeasureActions, tools: tuple[tuple[str, str], ...]
    ) -> QWidget:
        """A row of checkable tool buttons."""
        buttons: list[QWidget] = []
        for key, title in tools:
            push = button(title, _tool_slot(actions.toggle_tool, key), checkable=True)
            self.tool_buttons[key] = push
            buttons.append(push)
        return row(*buttons)

    @staticmethod
    def _unit_combo(unit: str) -> QComboBox:
        """Unit choice with ``unit`` selected."""
        combo = QComboBox()
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, label in UNITS.items():
            combo.addItem(label, key)
        keys = list(UNITS)
        combo.setCurrentIndex(keys.index(unit) if unit in keys else 0)
        return combo

    def show_tool(self, tool: str | None) -> None:
        """Check the button of ``tool`` and uncheck the others."""
        for key, push in self.tool_buttons.items():
            push.setChecked(key == tool)


def _ignore(_checked: bool) -> None:
    """Accept a toggle whose state is read when needed."""


class MetersGroup:
    """Focus meter and zebra stripe switches.

    Attributes:
        meters_check: Focus meter and histogram switch.
        zebra_check: Zebra stripe switch.
        box: The group box.
    """

    def __init__(
        self, on_meters: Toggle, on_zebra: Toggle, state: tuple[bool, bool]
    ) -> None:
        meters, zebra = state
        self.meters_check = checkbox("Focus meter and histogram", meters, on_meters)
        self.zebra_check = checkbox(
            "Zebra stripes on blown-out highlights", zebra, on_zebra
        )
        self.box = group("METERS", self.meters_check, self.zebra_check)


def tools_tab(
    compare: CompareGroup, measure: MeasureGroup, meters: MetersGroup
) -> QWidget:
    """The Tools tab contents: compare, measure and meters groups."""
    return column(compare.box, measure.box, meters.box)
