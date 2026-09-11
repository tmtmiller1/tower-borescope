"""Menu bar: File, Camera, Image, Tools, View, AI and Help, with their shortcuts.

Every action uses an application-wide shortcut context, so keys work while a sidebar
control has focus.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QWidget

from tower_borescope.app.widgets.labeled_slider import LabeledSlider
from tower_borescope.app.window.camera_panel import RES_LABELS

if TYPE_CHECKING:
    from tower_borescope.app.window.main_window import MainWindow

type Slot = Callable[[], object]
type Shortcut = str | QKeySequence.StandardKey | None

ZOOM_STEP: Final = 1.25
BRIGHTNESS_STEP: Final = 8
PERCENT_STEP: Final = 10
SHORTCUTS_TITLE: Final = "Keyboard Shortcuts"
SHORTCUTS_TEXT: Final = (
    "Capture:   S snapshot   P stacked still   B burst   V record   Shift+T time-lapse\n"
    "Camera:    1 to 5 resolution\n"
    "Image:     E enhance   W white balance   Shift+S stabilize   , . brightness   "
    "< > contrast   ; ' saturation\n"
    "Tools:     Space freeze   M distance   Shift+M angle   Ctrl+M area   A arrow   "
    "O circle   T text   D draw\n"
    "           Esc cancel tool   Cmd+Z undo   Ctrl+K calibrate\n"
    "View:      R / Shift+R rotate   F mirror   G grid   I meters   + - 0 zoom   "
    "Ctrl+\\ controls   Ctrl+Cmd+F full screen\n"
    "AI:        Ctrl+Shift+A analyze view   Ctrl+L ask   Ctrl+Shift+R add to report\n"
    "Mouse:     wheel zoom   drag pan   double-click reset zoom   "
    "drag the divider in split compare\n\n"
    "Scope button: press = snapshot, hold = start/stop recording."
)


@dataclass(slots=True)
class MenuActions:
    """Menu items whose check state or text follows the window state.

    Attributes:
        record: File > Start Recording, renamed while recording.
        resolutions: Camera resolution items, one checked.
        enhance: Image > Enhance.
        awb: Image > Auto White Balance.
        stabilize: Image > Stabilize.
        freeze: Tools > Freeze.
        mirror: View > Mirror.
        grid: View > Grid and Crosshair.
        meters: View > Focus Meter and Histogram.
        sidebar: View > Show Controls.
        fullscreen: View > Full Screen.
    """

    record: QAction
    resolutions: QActionGroup
    enhance: QAction
    awb: QAction
    stabilize: QAction
    freeze: QAction
    mirror: QAction
    grid: QAction
    meters: QAction
    sidebar: QAction
    fullscreen: QAction


class MenuBuilder:
    """Creates actions owned by the window with application-wide shortcuts.

    Attributes:
        owner: The window that owns every action.
    """

    def __init__(self, owner: QMainWindow) -> None:
        self.owner = owner

    def add(self, menu: QMenu, text: str, shortcut: Shortcut, slot: Slot) -> QAction:
        """Add a plain action.

        Args:
            menu: Destination menu.
            text: Item text.
            shortcut: Key sequence text, a standard key, or None.
            slot: Called when the item is triggered.

        Returns:
            The action.
        """
        action = QAction(text, self.owner)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def toggle(
        self,
        menu: QMenu,
        text: str,
        shortcut: Shortcut,
        slot: Slot,
        checked: bool = False,
    ) -> QAction:
        """Add a checkable action with an initial state."""
        action = self.add(menu, text, shortcut, slot)
        action.setCheckable(True)
        action.setChecked(checked)
        return action


def nudge(slider: LabeledSlider, step: float) -> Slot:
    """A handler that moves ``slider`` by ``step``."""

    def move() -> None:
        slider.set_value(slider.value() + step)

    return move


def show_shortcuts(parent: QWidget) -> None:
    """Show the keyboard shortcut summary."""
    QMessageBox.information(parent, SHORTCUTS_TITLE, SHORTCUTS_TEXT)


def _file_menu(window: MainWindow, build: MenuBuilder) -> QAction:
    """File menu; returns the recording item."""
    menu = window.menuBar().addMenu("File")
    capture = window.capture
    build.add(menu, "Snapshot", "S", capture.snapshot)
    build.add(menu, "Stacked Still", "P", window.pipeline.stack)
    build.add(menu, "Burst", "B", window.pipeline.burst)
    record = build.add(menu, "Start Recording", "V", capture.toggle_recording)
    build.add(menu, "Start/Stop Time-lapse", "Shift+T", capture.toggle_timelapse)
    menu.addSeparator()
    build.add(menu, "Gallery...", "Ctrl+G", window.show_gallery)
    build.add(menu, "Open Pictures Folder", "Ctrl+Shift+P", capture.open_pictures)
    build.add(menu, "Open Movies Folder", "Ctrl+Shift+M", capture.open_movies)
    menu.addSeparator()
    build.add(menu, "Quit", QKeySequence.StandardKey.Quit, window.close)
    return record


def _camera_menu(window: MainWindow, build: MenuBuilder) -> QActionGroup:
    """Camera menu with one checkable item per resolution."""
    menu = window.menuBar().addMenu("Camera")
    choices = QActionGroup(window)
    current = window.pipeline.state.mode
    for number, (key, label) in enumerate(RES_LABELS.items(), 1):
        slot = _resolution_slot(window, key)
        action = build.toggle(menu, label, str(number), slot, checked=key == current)
        choices.addAction(action)
    return choices


def _resolution_slot(window: MainWindow, key: str) -> Slot:
    """A handler that switches to resolution ``key``."""

    def choose() -> None:
        window.camera.set_resolution(key)

    return choose


def _image_menu(window: MainWindow, build: MenuBuilder) -> tuple[QAction, ...]:
    """Image menu; returns the enhance, white balance and stabilize items."""
    menu = window.menuBar().addMenu("Image")
    panel = window.image.panel
    state = window.pipeline.state
    enhance = build.toggle(
        menu, "Enhance", "E", panel.enhance_check.toggle, checked=state.enhanced
    )
    awb = build.toggle(
        menu, "Auto White Balance", "W", panel.awb_check.toggle, checked=state.grade.awb
    )
    stabilize = build.toggle(
        menu,
        "Stabilize",
        "Shift+S",
        panel.stabilize_check.toggle,
        checked=state.stabilize,
    )
    menu.addSeparator()
    steps = (
        ("Brighter", ".", panel.brightness, BRIGHTNESS_STEP),
        ("Darker", ",", panel.brightness, -BRIGHTNESS_STEP),
        ("More Contrast", ">", panel.contrast, PERCENT_STEP),
        ("Less Contrast", "<", panel.contrast, -PERCENT_STEP),
        ("More Saturation", "'", panel.saturation, PERCENT_STEP),
        ("Less Saturation", ";", panel.saturation, -PERCENT_STEP),
    )
    for text, key, slider, step in steps:
        build.add(menu, text, key, nudge(slider, step))
    menu.addSeparator()
    build.add(menu, "Reset Image Settings", "Shift+C", window.image.reset)
    return enhance, awb, stabilize


def _tool_slot(window: MainWindow, tool: str) -> Slot:
    """A handler that picks ``tool``."""

    def pick() -> None:
        window.measure.set_tool(tool)

    return pick


def _tools_menu(window: MainWindow, build: MenuBuilder) -> QAction:
    """Tools menu; returns the freeze item."""
    menu = window.menuBar().addMenu("Tools")
    freeze = build.toggle(menu, "Freeze", "Space", window.freeze.toggle_freeze)
    menu.addSeparator()
    tools = (
        ("Measure Distance", "M", "distance"),
        ("Measure Angle", "Shift+M", "angle"),
        ("Measure Area", "Ctrl+M", "area"),
        ("Arrow", "A", "arrow"),
        ("Circle", "O", "circle"),
        ("Text", "T", "text"),
        ("Draw", "D", "freehand"),
    )
    for text, key, tool in tools:
        build.add(menu, text, key, _tool_slot(window, tool))
    build.add(menu, "Cancel Tool", "Esc", window.escape).setVisible(False)
    menu.addSeparator()
    overlays = window.view.overlays
    build.add(menu, "Undo", QKeySequence.StandardKey.Undo, overlays.undo)
    build.add(
        menu, "Clear Measurements and Annotations", "Ctrl+Backspace", overlays.clear
    )
    build.add(menu, "Calibrate Scale...", "Ctrl+K", window.measure.calibrate_start)
    return freeze


def _zoom_slot(window: MainWindow, factor: float) -> Slot:
    """A handler that multiplies the view zoom by ``factor``; 0 resets it."""

    def zoom() -> None:
        view = window.view
        view.set_zoom(view.zoom * factor if factor else 1.0)

    return zoom


def _view_menu(window: MainWindow, build: MenuBuilder) -> tuple[QAction, ...]:
    """View menu; returns the mirror, grid, meters, controls and full screen items."""
    menu = window.menuBar().addMenu("View")
    controls = window.view_controls
    build.add(menu, "Rotate Clockwise", "R", controls.rotate_right)
    build.add(menu, "Rotate Counter-clockwise", "Shift+R", controls.rotate_left)
    state = window.pipeline.state
    mirror_check = controls.orientation.mirror_check
    mirror = build.toggle(menu, "Mirror", "F", mirror_check.toggle, checked=state.mirror)
    grid_check = controls.orientation.grid_check
    grid = build.toggle(menu, "Grid and Crosshair", "G", grid_check.toggle)
    meters_check = window.image.meters.meters_check
    meters = build.toggle(
        menu, "Focus Meter and Histogram", "I", meters_check.toggle, checked=state.meters
    )
    menu.addSeparator()
    build.add(menu, "Zoom In", "+", _zoom_slot(window, ZOOM_STEP))
    build.add(menu, "Zoom In", "=", _zoom_slot(window, ZOOM_STEP)).setVisible(False)
    build.add(menu, "Zoom Out", "-", _zoom_slot(window, 1 / ZOOM_STEP))
    build.add(menu, "Reset Zoom", "0", _zoom_slot(window, 0.0))
    menu.addSeparator()
    sidebar = build.toggle(
        menu, "Show Controls", "Ctrl+\\", controls.toggle_sidebar, checked=True
    )
    fullscreen = build.toggle(
        menu, "Full Screen", "Ctrl+Meta+F", controls.toggle_fullscreen
    )
    return mirror, grid, meters, sidebar, fullscreen


def _ai_menu(window: MainWindow, build: MenuBuilder) -> None:
    """AI menu."""
    menu = window.menuBar().addMenu("AI")
    ai = window.ai
    build.add(menu, "Analyze What's in View", "Ctrl+Shift+A", ai.analyze)
    build.add(menu, "Ask a Follow-up...", "Ctrl+L", ai.focus_question)
    build.add(
        menu, "Estimate Scale from View", "Ctrl+Shift+K", window.measure.scale.estimate
    )
    build.add(menu, "Add View to Report", "Ctrl+Shift+R", ai.report.add_view)
    build.add(menu, "Write Inspection Report...", None, ai.report.write)
    menu.addSeparator()
    build.add(menu, "AI Settings...", None, ai.open_settings)


def build_menus(window: MainWindow) -> MenuActions:
    """Create every menu of ``window``.

    Args:
        window: The main window with its controllers built.

    Returns:
        The items whose state follows the window.
    """
    build = MenuBuilder(window)
    record = _file_menu(window, build)
    resolutions = _camera_menu(window, build)
    enhance, awb, stabilize = _image_menu(window, build)
    freeze = _tools_menu(window, build)
    mirror, grid, meters, sidebar, fullscreen = _view_menu(window, build)
    _ai_menu(window, build)
    help_menu = window.menuBar().addMenu("Help")
    build.add(help_menu, SHORTCUTS_TITLE, "?", lambda: show_shortcuts(window))
    return MenuActions(
        record=record,
        resolutions=resolutions,
        enhance=enhance,
        awb=awb,
        stabilize=stabilize,
        freeze=freeze,
        mirror=mirror,
        grid=grid,
        meters=meters,
        sidebar=sidebar,
        fullscreen=fullscreen,
    )
