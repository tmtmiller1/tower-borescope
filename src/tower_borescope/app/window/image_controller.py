"""Image settings: color, enhance, filters, view mode, meters and zebra stripes."""

from __future__ import annotations

from typing import Final

from PySide6.QtGui import QAction

from tower_borescope.app.pipeline.state import NORMAL_VIEW
from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.image_panel import ImageActions, ImagePanel
from tower_borescope.app.window.tools_panel import MetersGroup

DENOISE: Final = "denoise"
GLARE: Final = "glare"
FILTERS: Final = (GLARE, DENOISE)
GRADE_CONTROLS: Final = ("brightness", "contrast", "saturation")
NEUTRAL_SLIDERS: Final = (("brightness", 0), ("contrast", 100), ("saturation", 100))


class ImageController:
    """Applies image settings to the pipeline and remembers them.

    Attributes:
        ctx: Shared window state.
        panel: The Image tab widgets.
        meters: The METERS group of the Tools tab.
        menu_actions: Checkable menu items keyed by setting, once the menus exist.
    """

    def __init__(self, ctx: WindowContext) -> None:
        self.ctx = ctx
        state = ctx.pipeline.state
        actions = ImageActions(
            set_enhance=self.set_enhance,
            set_awb=self.set_awb,
            set_grade=self.set_grade,
            set_filter=self.set_filter,
            set_stabilize=self.set_stabilize,
            set_view_mode=self.set_view_mode,
            reset=self.reset,
        )
        self.panel = ImagePanel(actions, state)
        self.meters = MetersGroup(
            self.set_meters, self.set_zebra, (state.meters, state.zebra)
        )
        self.menu_actions: dict[str, QAction] = {}

    def _sync(self, name: str, on: bool) -> None:
        """Check or uncheck the menu item for ``name``."""
        action = self.menu_actions.get(name)
        if action is not None:
            action.setChecked(on)

    def set_enhance(self, on: bool) -> None:
        """Turn enhance on or off."""
        self.ctx.pipeline.state.enhanced = on
        self._sync("enhance", on)
        self.ctx.prefs.remember(enhance=on)

    def set_awb(self, on: bool) -> None:
        """Turn auto white balance on or off."""
        self.ctx.pipeline.state.grade.awb = on
        self._sync("awb", on)
        self.ctx.prefs.remember(awb=on)

    def set_grade(self, name: str, value: float) -> None:
        """Set brightness, contrast or saturation.

        Args:
            name: One of ``GRADE_CONTROLS``.
            value: Brightness offset, or contrast or saturation factor.
        """
        if name not in GRADE_CONTROLS:
            raise ValueError(f"unknown color control: {name}")
        setattr(self.ctx.pipeline.state.grade, name, value)
        self.ctx.prefs.remember(**{name: value})

    def set_filter(self, name: str, strength: float) -> None:
        """Set glare reduction or temporal denoise strength.

        Args:
            name: ``"glare"`` or ``"denoise"``.
            strength: From 0 (off) to 1.
        """
        if name not in FILTERS:
            raise ValueError(f"unknown filter: {name}")
        setattr(self.ctx.pipeline.state, name, strength)
        if name == DENOISE:
            self.ctx.pipeline.reset_denoiser()
        self.ctx.prefs.remember(**{name: strength})

    def set_stabilize(self, on: bool) -> None:
        """Turn stabilization on or off, starting from a fresh camera path."""
        self.ctx.pipeline.state.stabilize = on
        self.ctx.pipeline.reset_stabilizer()
        self._sync("stabilize", on)
        self.ctx.prefs.remember(stabilize=on)

    def set_view_mode(self, mode: str) -> None:
        """Select a view mode such as Normal or Outline."""
        self.ctx.pipeline.state.view_mode = mode
        self.ctx.prefs.remember(view_mode=mode)

    def set_meters(self, on: bool) -> None:
        """Show or hide the focus meter and histogram."""
        self.ctx.pipeline.state.meters = on
        self.ctx.view.show_meters = on
        self._sync("meters", on)
        self.ctx.prefs.remember(meters=on)
        self.ctx.view.update()

    def set_zebra(self, on: bool) -> None:
        """Stripe blown-out highlights."""
        self.ctx.pipeline.state.zebra = on
        self.ctx.prefs.remember(zebra=on)

    def reset(self) -> None:
        """Restore every image setting to its default."""
        state = self.ctx.pipeline.state
        state.grade.reset()
        panel = self.panel
        for slider in (panel.brightness, panel.contrast, panel.saturation, panel.glare):
            slider.set_value(
                slider.default if slider is not panel.glare else 0, silent=True
            )
        for name, value in NEUTRAL_SLIDERS:
            getattr(panel, name).set_value(value, silent=True)
        panel.denoise.set_value(0, silent=True)
        for box in (panel.awb_check, panel.enhance_check, panel.stabilize_check):
            box.setChecked(False)
        panel.mode_combo.setCurrentText(NORMAL_VIEW)
        state.glare = 0.0
        state.denoise = 0.0
        self.ctx.prefs.remember(
            **state.grade.to_dict(),
            enhance=False,
            stabilize=False,
            glare=0.0,
            denoise=0.0,
            view_mode=NORMAL_VIEW,
        )
        self.ctx.toast("Image settings reset")
