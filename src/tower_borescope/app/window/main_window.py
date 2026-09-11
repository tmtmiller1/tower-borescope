"""The main window: video view, sidebar tabs, menus and status bar.

``MainWindow`` composes the panels and controllers of this package, connects the
pipeline and view signals to them and persists the window geometry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tower_borescope.app.dialogs.gallery import GalleryWindow
from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.app.style import DIVIDER_STYLE
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.app.widgets.layout import scrolled
from tower_borescope.app.window.ai_controller import AiController
from tower_borescope.app.window.camera_controller import CameraController
from tower_borescope.app.window.camera_panel import RES_LABELS
from tower_borescope.app.window.capture_controller import CaptureController, CaptureLinks
from tower_borescope.app.window.compare_controller import CompareController
from tower_borescope.app.window.context import ORGANIZATION, Preferences, WindowContext
from tower_borescope.app.window.freeze_controller import FreezeController
from tower_borescope.app.window.image_controller import ImageController
from tower_borescope.app.window.measure_controller import MeasureController
from tower_borescope.app.window.menus import build_menus
from tower_borescope.app.window.share_controller import ShareController
from tower_borescope.app.window.tools_panel import tools_tab
from tower_borescope.app.window.view_controller import ViewController
from tower_borescope.app.window.view_panel import view_tab
from tower_borescope.config import APP_NAME, SettingsStore, data_paths
from tower_borescope.device.reader import FrameSource, Reader

__all__ = ["ORGANIZATION", "MainWindow", "geometry_settings"]

GEOMETRY_KEY: Final = "geometry"
DEFAULT_SIZE: Final = (1440, 900)
SIDEBAR_WIDTH: Final = 330
SIDEBAR_MARGINS: Final = (10, 4, 10, 8)
STATUS_MARGINS: Final = (10, 0, 10, 0)
CLOSE_WAIT_MS: Final = 8000


def geometry_settings() -> QSettings:
    """The per-user settings holding the window geometry, in the default format."""
    return QSettings(
        QSettings.defaultFormat(), QSettings.Scope.UserScope, ORGANIZATION, APP_NAME
    )


def _fill_sidebar(sidebar: QWidget, widgets: tuple[QWidget, QWidget, QWidget]) -> None:
    """Stack the camera group, the stretching tabs and the recent captures strip."""
    layout = QVBoxLayout(sidebar)
    layout.setContentsMargins(*SIDEBAR_MARGINS)
    layout.setSpacing(6)
    top, middle, bottom = widgets
    layout.addWidget(top)
    layout.addWidget(middle, 1)
    layout.addWidget(bottom)
    sidebar.setFixedWidth(SIDEBAR_WIDTH)


def _central_widget(view: QWidget, sidebar: QWidget) -> QWidget:
    """The video beside the sidebar, separated by a thin divider."""
    central = QWidget()
    layout = QHBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(view, 1)
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.VLine)
    divider.setStyleSheet(DIVIDER_STYLE)
    layout.addWidget(divider)
    layout.addWidget(sidebar)
    return central


class MainWindow(QMainWindow):
    """Video on the left, controls on the right, menus and a status bar.

    Attributes:
        pipeline: Frame processing thread, started by the constructor.
        view: Video view.
        ctx: State shared with the controllers.
        sidebar: Controls column.
        tabs: Capture, AI, Image, Tools and View tabs.
        gallery: Gallery dialog once opened, or None.
        menu_actions: Menu items that follow the window state.
    """

    def __init__(
        self,
        store: SettingsStore | None = None,
        source_factory: Callable[[str], FrameSource] = Reader,
    ) -> None:
        super().__init__()
        # A closed window is deleted, so its application-wide shortcuts stop matching.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(APP_NAME)
        prefs = Preferences(store if store is not None else SettingsStore())
        paths = data_paths()
        self.pipeline = Pipeline(prefs.values, source_factory, paths)
        self.view = VideoView()
        self.ctx = WindowContext(self, self.pipeline, self.view, prefs, paths)
        self.sidebar = QWidget()
        self.tabs = QTabWidget()
        self.gallery: GalleryWindow | None = None
        self._build_controllers()
        self.menu_actions = build_menus(self)
        self._link_menu_actions()
        self._build_layout()
        self._connect_signals()
        self._restore_geometry()
        self.capture.feedback.recent.load(self.ctx.capture_folders())
        self.measure.update_calibration_label()
        self.pipeline.start()

    def _build_controllers(self) -> None:
        """Create the controllers in dependency order."""
        ctx = self.ctx
        self.freeze = FreezeController(ctx)
        self.camera = CameraController(ctx, self._mode_changed)
        self.ai = AiController(ctx, self.freeze, self.show_tab)
        self.measure = MeasureController(ctx, self.ai, self.freeze, self.show_tab)
        self.image = ImageController(ctx)
        self.compare = CompareController(
            ctx, self.freeze.toggle_freeze, self.show_gallery, self.show_tab
        )
        links = CaptureLinks(
            show_gallery=self.show_gallery,
            refresh_gallery=self.refresh_gallery,
            burn_in=self.measure.burn_in,
            camera_combo=self.camera.panel.res_combo,
        )
        self.capture = CaptureController(ctx, links)
        self.share = ShareController(
            ctx, self.capture.snapshot, self.capture.toggle_recording
        )
        self.view_controls = ViewController(ctx, self.sidebar)

    def _link_menu_actions(self) -> None:
        """Let the controllers keep the checkable menu items in step."""
        menu = self.menu_actions
        self.freeze.add_indicator(menu.freeze)
        self.freeze.add_indicator(self.compare.group.freeze_btn)
        self.capture.feedback.record_action = menu.record
        self.image.menu_actions.update(
            enhance=menu.enhance,
            awb=menu.awb,
            stabilize=menu.stabilize,
            meters=menu.meters,
        )
        self.view_controls.menu_actions.update(
            mirror=menu.mirror,
            grid=menu.grid,
            sidebar=menu.sidebar,
            fullscreen=menu.fullscreen,
        )

    def _build_layout(self) -> None:
        """Place the tabs in the sidebar beside the video, and fill the status bar."""
        pages = (
            ("Capture", self.capture.panel.widget),
            ("AI", self.ai.panel.widget),
            ("Image", self.image.panel.widget),
            (
                "Tools",
                tools_tab(self.compare.group, self.measure.group, self.image.meters),
            ),
            ("View", view_tab(self.view_controls.orientation, self.share.group)),
        )
        for name, page in pages:
            self.tabs.addTab(scrolled(page), name)
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        column = (self.camera.panel.box, self.tabs, self.capture.feedback.recent.box)
        _fill_sidebar(self.sidebar, column)
        self.setCentralWidget(_central_widget(self.view, self.sidebar))
        status = self.statusBar()
        status.addWidget(self.camera.status_left, 1)
        status.addPermanentWidget(self.camera.status_right)
        status.setContentsMargins(*STATUS_MARGINS)

    def _connect_signals(self) -> None:
        """Route pipeline signals (queued from its thread) and view signals."""
        pipeline, view = self.pipeline, self.view
        feedback = self.capture.feedback
        pipeline.frame_ready.connect(view.set_frame)
        pipeline.stats.connect(self.camera.on_stats)
        pipeline.size_changed.connect(self.camera.on_size_changed)
        pipeline.stack_progress.connect(feedback.on_stack_progress)
        pipeline.captured.connect(feedback.on_captured)
        pipeline.recording_changed.connect(feedback.on_recording_changed)
        pipeline.timelapse_changed.connect(feedback.on_timelapse_changed)
        pipeline.notice.connect(view.toast)
        pipeline.button.connect(self.capture.on_scope_button)
        pipeline.vcam_changed.connect(self.share.on_vcam_changed)
        view.zoom_changed.connect(self.view_controls.orientation.show_zoom)
        view.tool_finished.connect(self.measure.finish_tool)
        view.calibrate_measured.connect(self.measure.calibrate_finish)
        view.live_requested.connect(self.back_to_live)

    def _restore_geometry(self) -> None:
        """Restore the saved window geometry, or use the default size."""
        geometry = geometry_settings().value(GEOMETRY_KEY)
        if isinstance(geometry, QByteArray) and self.restoreGeometry(geometry):
            return
        self.resize(*DEFAULT_SIZE)

    def _mode_changed(self, key: str) -> None:
        """Follow a resolution change in the menu and the measurement scale."""
        for action in self.menu_actions.resolutions.actions():
            action.setChecked(action.text() == RES_LABELS[key])
        self.measure.mode_changed(key)

    def show_tab(self, name: str) -> None:
        """Bring the sidebar tab titled ``name`` to the front."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.setCurrentIndex(index)

    def show_gallery(self) -> None:
        """Open the capture gallery, or refresh and raise it."""
        if self.gallery is None:
            self.gallery = GalleryWindow(self.ctx.capture_folders(), self)
            self.gallery.use_as_reference.connect(self.compare.set_reference)
        else:
            self.gallery.reload()
        self.gallery.show()
        self.gallery.raise_()

    def refresh_gallery(self) -> None:
        """Reload the gallery when it is open."""
        if self.gallery is not None and self.gallery.isVisible():
            self.gallery.reload()

    def back_to_live(self) -> None:
        """Clear the AI boxes and return to the live camera."""
        self.freeze.back_to_live()

    def escape(self) -> None:
        """Cancel the tool, else return to live, else leave full screen."""
        if self.view.tool:
            self.measure.set_tool(None)
        elif self.view.frozen or self.view.ai_boxes:
            self.back_to_live()
        elif self.isFullScreen():
            self.view_controls.toggle_fullscreen()

    def _key_press_event(self, event: QKeyEvent) -> None:
        """Handle Esc when a focused text field kept the shortcut from firing."""
        if event.key() == Qt.Key.Key_Escape:
            self.escape()
            event.accept()
            return
        super().keyPressEvent(event)

    def _close_event(self, event: QCloseEvent) -> None:
        """Save the geometry, stop sharing and AI work, and stop the pipeline."""
        geometry_settings().setValue(GEOMETRY_KEY, self.saveGeometry())
        self.camera.status_left.setText("Closing...")
        self.share.stop_remote()
        self.ai.runner.wait()
        self.pipeline.stop()
        self.pipeline.wait(CLOSE_WAIT_MS)
        event.accept()

    keyPressEvent = _key_press_event
    closeEvent = _close_event
