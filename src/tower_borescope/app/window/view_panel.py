"""View tab: rotation, mirror, grid, zoom, the phone monitor and the virtual camera."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from PySide6.QtWidgets import QWidget

from tower_borescope.app.widgets.labeled_slider import LabeledSlider, SliderSpec
from tower_borescope.app.widgets.layout import (
    button,
    checkbox,
    column,
    group,
    row,
    small_label,
)

ZOOM_PERCENT: Final = 100
REMOTE_OFF_TEXT: Final = "Off"

type Action = Callable[[], None]
type Toggle = Callable[[bool], None]


def _zoom_text(value: float) -> str:
    """A zoom percentage shown as a factor."""
    return f"{value / ZOOM_PERCENT:.1f}x"


ZOOM_SPEC: Final = SliderSpec("Zoom (view only)", 100, 800, _zoom_text)


@dataclass(frozen=True, slots=True)
class OrientationActions:
    """Handlers for the VIEW group.

    Attributes:
        rotate_left: Rotate a quarter turn counter-clockwise.
        rotate_right: Rotate a quarter turn clockwise.
        set_mirror: Mirror switch.
        set_grid: Grid and crosshair switch.
        set_zoom: Called with the view zoom factor.
    """

    rotate_left: Action
    rotate_right: Action
    set_mirror: Toggle
    set_grid: Toggle
    set_zoom: Callable[[float], None]


class OrientationGroup:
    """Rotation buttons, mirror and grid switches and the view zoom slider.

    Attributes:
        mirror_check: Mirror switch.
        grid_check: Grid and crosshair switch.
        zoom_slider: View zoom slider in percent.
        box: The VIEW group box.
    """

    def __init__(self, actions: OrientationActions, mirror: bool) -> None:
        self.mirror_check = checkbox("Mirror", mirror, actions.set_mirror)
        self.grid_check = checkbox("Grid and crosshair", False, actions.set_grid)
        self.zoom_slider = LabeledSlider(
            ZOOM_SPEC, ZOOM_PERCENT, lambda v: actions.set_zoom(v / ZOOM_PERCENT)
        )
        self.box = group(
            "VIEW",
            row(
                button("Rotate left", actions.rotate_left),
                button("Rotate right", actions.rotate_right),
            ),
            row(self.mirror_check, self.grid_check),
            self.zoom_slider,
        )

    def show_zoom(self, zoom: float) -> None:
        """Move the zoom slider to ``zoom`` without reporting a change."""
        self.zoom_slider.set_value(zoom * ZOOM_PERCENT, silent=True)


class ShareGroup:
    """Phone monitor and virtual camera controls.

    Attributes:
        remote_btn: Checkable phone monitor button.
        remote_label: Phone monitor address or "Off".
        vcam_btn: Checkable virtual camera button.
        box: The SHARE group box.
    """

    def __init__(self, toggle_remote: Action, toggle_vcam: Action) -> None:
        self.remote_btn = button(
            "Phone monitor",
            toggle_remote,
            checkable=True,
            tip="Serve the live view to any phone or browser on the same Wi-Fi.",
        )
        self.remote_label = small_label(REMOTE_OFF_TEXT)
        self.vcam_btn = button(
            "Virtual camera",
            toggle_vcam,
            checkable=True,
            tip="Makes the scope a webcam for Zoom / FaceTime / QuickTime. "
            "Needs OBS installed.",
        )
        self.box = group("SHARE", self.remote_btn, self.remote_label, self.vcam_btn)


def view_tab(orientation: OrientationGroup, share: ShareGroup) -> QWidget:
    """The View tab contents: the VIEW and SHARE groups."""
    return column(orientation.box, share.box)
