"""Measurement tools, units, calibration, the focus-locked scale status and the AI
scale estimate."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QInputDialog, QMessageBox

from tower_borescope.ai.conversation import estimate_scale
from tower_borescope.ai.images import encode_for_model
from tower_borescope.ai.schema import ScaleEstimate
from tower_borescope.app.view.ai_boxes import AiBox
from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.tools_panel import (
    SCALE_AI_LABEL,
    MeasureActions,
    MeasureGroup,
)
from tower_borescope.device.constants import MODES
from tower_borescope.measure.calibration import SOURCE_AI, SOURCE_MEASURED, Calibration
from tower_borescope.measure.shapes import ANNOTATE_KINDS, MEASURE_KINDS
from tower_borescope.measure.units import UNITS, format_length, to_mm, unit_name

if TYPE_CHECKING:
    from tower_borescope.app.window.ai_controller import AiController
    from tower_borescope.app.window.freeze_controller import FreezeController

CALIBRATE_TOOL: Final = "calibrate"
SCALED_TOOLS: Final = ("distance", "area")
INCH_UNITS: Final = ("in", "frac", "ftin")
SCALE_TIMER_MS: Final = 500
MIN_REFERENCE_PIXELS: Final = 8.0
SPAN_COORDINATES: Final = 4
TOOLS_TAB: Final = "Tools"
LENGTH_RANGE: Final = (0.001, 100000.0)
LENGTH_DECIMALS: Final = 3
FOCUS_UNKNOWN_TEXT: Final = (
    "Focus check unavailable (calibration predates it: recalibrate once)."
)
FOCUS_OK_TEXT: Final = "OK: Picture is at the calibrated focus: measurements are valid."
FOCUS_OFF_TEXT: Final = (
    "Check: Sharpness differs from calibration: move closer/farther until the focus "
    "meter matches, or measurements will be off."
)


class MeasureController:
    """Picks tools, converts units and keeps the scale for each resolution.

    Attributes:
        ctx: Shared window state.
        group: The MEASURE AND ANNOTATE group.
        scale: The AI scale estimate.
    """

    def __init__(
        self,
        ctx: WindowContext,
        ai: AiController,
        freeze: FreezeController,
        show_tab: Callable[[str], None],
    ) -> None:
        self.ctx = ctx
        self._show_tab = show_tab
        self.scale = ScaleEstimator(ctx, ai, freeze, self)
        actions = MeasureActions(
            toggle_tool=self.toggle_tool,
            undo=ctx.view.overlays.undo,
            clear=ctx.view.overlays.clear,
            set_unit=self.set_unit,
            calibrate=self.calibrate_start,
            estimate_scale=self.scale.estimate,
        )
        ctx.view.unit = str(ctx.prefs.values.get("unit", "mm"))
        if ctx.view.unit not in UNITS:
            ctx.view.unit = "mm"
        ctx.view.mm_per_px = ctx.pipeline.state.calibration.mm_per_px(
            ctx.pipeline.state.mode
        )
        self.group = MeasureGroup(actions, ctx.view.unit)
        self._timer = QTimer(ctx.window)
        self._timer.timeout.connect(self.update_scale_state)
        self._timer.start(SCALE_TIMER_MS)

    def burn_in(self) -> bool:
        """True when snapshots also save an annotated copy."""
        return self.group.burn_check.isChecked()

    def toggle_tool(self, tool: str) -> None:
        """Pick ``tool``, or drop it when it is already active."""
        self.set_tool(None if self.ctx.view.tool == tool else tool)

    def finish_tool(self) -> None:
        """Drop the active tool after it finished an item."""
        self.set_tool(None)

    def set_tool(self, tool: str | None) -> None:
        """Activate a tool; a new one replaces earlier items of its kind unless kept.

        Args:
            tool: A measurement, annotation or calibration tool name, or None.
        """
        view = self.ctx.view
        overlays = view.overlays
        if tool and not self.group.keep_check.isChecked():
            if tool in MEASURE_KINDS and overlays.measurements:
                overlays.clear_measurements()
            elif tool in ANNOTATE_KINDS and overlays.annotations:
                overlays.clear_annotations()
        view.set_tool(tool)
        self.group.show_tool(tool)
        if tool in SCALED_TOOLS and view.mm_per_px is None:
            self.ctx.toast(
                "Not calibrated: values are in pixels (Tools > Calibrate Scale)"
            )

    def set_unit(self, index: int) -> None:
        """Show lengths in the unit at combo ``index`` and remember it."""
        unit = str(self.group.unit_combo.itemData(index))
        self.ctx.view.unit = unit
        self.ctx.prefs.remember(unit=unit)
        self.update_calibration_label()
        self.ctx.view.update()

    def calibrate_start(self) -> None:
        """Start the two-click calibration tool."""
        self.set_tool(CALIBRATE_TOOL)
        self._show_tab(TOOLS_TAB)

    def calibrate_finish(self, pixels: float) -> None:
        """Ask for the real length of the clicked span and calibrate from it.

        Args:
            pixels: Distance between the two calibration clicks in image pixels.
        """
        unit = self.ctx.view.unit
        low, high = LENGTH_RANGE
        value, ok = QInputDialog.getDouble(
            self.ctx.window,
            "Calibrate scale",
            f"Real length of what you clicked ({unit_name(unit)}):",
            1.0 if unit in INCH_UNITS else 10.0,
            low,
            high,
            LENGTH_DECIMALS,
        )
        if ok:
            focus = self.ctx.view.focus_raw
            self.apply_calibration(pixels, to_mm(value, unit), SOURCE_MEASURED, focus)

    def apply_calibration(
        self, pixels: float, millimetres: float, source: str, focus: float | None
    ) -> None:
        """Store a scale for the current resolution and announce it.

        Args:
            pixels: Reference length in image pixels.
            millimetres: Real reference length.
            source: ``SOURCE_MEASURED`` or ``SOURCE_AI``.
            focus: Focus score when the reference was taken, for the focus lock.
        """
        state = self.ctx.pipeline.state
        calibration = state.calibration
        calibration.set_from(state.mode, pixels, millimetres, focus=focus, source=source)
        view = self.ctx.view
        view.mm_per_px = calibration.mm_per_px(state.mode)
        self.ctx.prefs.remember(calibration=calibration.to_dict())
        self.update_calibration_label()
        mode = MODES[state.mode]
        how = "estimated" if source == SOURCE_AI else "calibrated"
        length = format_length(view.mm_per_px or 0.0, view.unit)
        self.ctx.toast(f"Scale {how} at {mode.width}x{mode.height}: 1 px = {length}")
        view.update()

    def mode_changed(self, key: str) -> None:
        """Use the scale of the new resolution and clear items drawn at the old one."""
        self.ctx.view.mm_per_px = self.ctx.pipeline.state.calibration.mm_per_px(key)
        self.ctx.view.overlays.clear()
        self.update_calibration_label(key)

    def update_calibration_label(self, mode: str | None = None) -> None:
        """Describe the scale and field of view of ``mode``, or the current mode."""
        key = mode or self.ctx.pipeline.state.mode
        calibration = self.ctx.pipeline.state.calibration
        text = calibration_text(calibration, key, self.ctx.view.unit)
        self.group.calibration_label.setText(text)

    def update_scale_state(self) -> None:
        """Compare the current sharpness with the sharpness at calibration."""
        state = self.ctx.pipeline.state
        view = self.ctx.view
        ok = state.calibration.focus_ok(state.mode, view.focus_raw)
        if ok != view.scale_ok:
            view.scale_ok = ok
            view.update()
        calibrated = state.calibration.mm_per_px(state.mode) is not None
        self.group.scale_state.setText(focus_text(calibrated, ok))


def calibration_text(calibration: Calibration, mode: str, unit: str) -> str:
    """Scale and field of view of ``mode``, or a note that it is not calibrated.

    Args:
        calibration: Scales per mode.
        mode: A key of ``device.constants.MODES``.
        unit: A key of ``measure.units.UNITS``.

    Returns:
        The calibration label text.
    """
    scale = calibration.mm_per_px(mode)
    size = MODES[mode]
    if not scale:
        return (
            f"No scale for {size.width}x{size.height}: measurements are in pixels. "
            "Calibrate with a known length, or let AI estimate it from something in view."
        )
    how = "estimated by AI" if calibration.source(mode) == SOURCE_AI else "calibrated"
    width = format_length(scale * size.width, unit)
    height = format_length(scale * size.height, unit)
    return (
        f"Scale {how} for {size.width}x{size.height}: field of view about {width} x "
        f"{height}. Valid at the distance it was set at; the focus check below "
        "tells you when you're there."
    )


def focus_text(calibrated: bool, focus_ok: bool | None) -> str:
    """Focus lock status: empty without a scale, else unknown, OK or Check."""
    if not calibrated:
        return ""
    if focus_ok is None:
        return FOCUS_UNKNOWN_TEXT
    return FOCUS_OK_TEXT if focus_ok else FOCUS_OFF_TEXT


def _usable(estimate: ScaleEstimate) -> bool:
    """True when an estimate names a reference with a span and a positive size."""
    span = estimate.span
    return (
        estimate.found
        and span is not None
        and len(span) == SPAN_COORDINATES
        and estimate.standard_size_mm > 0
    )


class ScaleEstimator:
    """Asks the AI for an object of standard size and offers it as the scale.

    Attributes:
        ctx: Shared window state.
        ai: The AI controller that owns the backend and the worker.
        freeze: Freezing, so the estimate uses a still frame.
        measure: Applies an accepted scale.
    """

    def __init__(
        self,
        ctx: WindowContext,
        ai: AiController,
        freeze: FreezeController,
        measure: MeasureController,
    ) -> None:
        self.ctx = ctx
        self.ai = ai
        self.freeze = freeze
        self.measure = measure
        self._focus: float | None = None

    def estimate(self) -> None:
        """Freeze the view and ask the AI for a scale reference."""
        if self.ai.runner.busy():
            return
        client = self.ai.client()
        if client is None or self.ctx.pipeline.last_frame is None:
            return
        frame = self.freeze.freeze_for_analysis()
        if frame is None:
            return
        button = self.measure.group.scale_ai_btn
        button.setEnabled(False)
        button.setText("Estimating...")
        self._focus = self.ctx.view.focus_raw
        jpeg = encode_for_model(frame, client.max_image_width)
        self.ai.runner.run(
            lambda _emit: estimate_scale(client, jpeg), self._ready, self._failed
        )

    def _reset_button(self) -> None:
        """Enable the estimate button again."""
        button = self.measure.group.scale_ai_btn
        button.setEnabled(True)
        button.setText(SCALE_AI_LABEL)

    def _failed(self, message: str) -> None:
        """Restore the button and show the failure."""
        self._reset_button()
        self.ai.show_failure(message)

    def _ready(self, value: object) -> None:
        """Show the reference and apply it as the scale when confirmed."""
        self._reset_button()
        self.ai.update_status()
        image = self.ctx.view.image
        if not isinstance(value, ScaleEstimate) or not _usable(value) or image is None:
            reasoning = value.reasoning if isinstance(value, ScaleEstimate) else ""
            self.ctx.toast("AI found nothing of known size in this view")
            QMessageBox.information(
                self.ctx.window,
                "Scale estimate",
                "Nothing of a standard size is clearly visible.\n\n" + reasoning,
            )
            return
        x0, y0, x1, y1 = value.span or []
        width, height = image.width(), image.height()
        pixels = math.hypot((x1 - x0) * width, (y1 - y0) * height)
        if pixels < MIN_REFERENCE_PIXELS:
            self.ctx.toast("AI reference too small to use")
            return
        label = f"ref: {value.reference_object}"
        box = AiBox(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), label, "low")
        self.ctx.view.ai_boxes = [box]
        self.ctx.view.update()
        if self._confirm(value, pixels, (width, height)):
            size = value.standard_size_mm
            self.measure.apply_calibration(pixels, size, SOURCE_AI, self._focus)
        self.ctx.view.ai_boxes = []
        self.ctx.view.update()

    def _confirm(
        self, estimate: ScaleEstimate, pixels: float, frame: tuple[int, int]
    ) -> bool:
        """Ask whether to use the estimated scale."""
        unit = self.ctx.view.unit
        mm_per_px = estimate.standard_size_mm / pixels
        width = format_length(mm_per_px * frame[0], unit)
        height = format_length(mm_per_px * frame[1], unit)
        size = format_length(estimate.standard_size_mm, unit)
        text = (
            f"Reference: {estimate.reference_object}\n"
            f"Standard size: {size} across {pixels:.0f} px\n"
            f"Confidence: {estimate.confidence}\n\n{estimate.reasoning}\n\n"
            f"Resulting scale: field of view about {width} x {height}.\n\n"
            "Use this scale? (Marked as AI-estimated; a measured calibration is more "
            "accurate.)"
        )
        answer = QMessageBox.question(self.ctx.window, "Scale estimate", text)
        return answer == QMessageBox.StandardButton.Yes
