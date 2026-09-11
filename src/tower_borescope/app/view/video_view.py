"""The video widget: frames with zoom, pan, freeze, compare, tools, meters and badges."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPainter, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.view import geometry
from tower_borescope.app.view.ai_boxes import AiBox
from tower_borescope.app.view.badges import Toasts
from tower_borescope.app.view.geometry import ImageMapper
from tower_borescope.app.view.overlays import OverlayModel
from tower_borescope.app.view.painter import paint_view
from tower_borescope.app.view.pointer import PointerHandler
from tower_borescope.app.view.tools import ToolController, ToolSignals
from tower_borescope.measure.shapes import OverlaySnapshot

CONNECTING_STATUS = "Connecting to scope..."
COMPARE_OFF = "off"
DEFAULT_SPLIT = 0.5
DEFAULT_OPACITY = 0.5
DEFAULT_TOAST_SECONDS = 3.0
MIN_WIDTH = 320
MIN_HEIGHT = 180
HOUSEKEEPING_MS = 250


class VideoView(QWidget):
    """Shows frames with zoom and pan, freeze, compare, tools, meters, grid and badges.

    Attributes:
        image: Frame on screen, or None before the first frame.
        live_image: Latest frame from the pipeline, shown again when unfrozen.
        frozen: Whether new frames are held back from the screen.
        zoom: Zoom factor from 1 to 8.
        pan: Pan offset in widget pixels while zoomed.
        split: Split-compare divider position as a fraction of the image width.
        grid: Whether the thirds grid is drawn.
        recording_since: Monotonic start time of a recording, or None.
        status: Centred status text; empty while streaming.
        info: Latest frame readings, or None.
        show_meters: Whether the focus bar and histogram are drawn.
        compare_image: Reference image, or None.
        compare_mode: "off", "split" or "overlay".
        compare_opacity: Reference opacity in overlay mode.
        tool: Active tool name, or None to pan.
        overlays: Measurements, annotations and undo history.
        tools: Tool mouse handling.
        toasts: Short messages drawn at the bottom left.
        mm_per_px: Image scale for labels, or None for pixels.
        unit: A key of ``measure.units.UNITS``.
        scale_ok: Focus lock result for the scale: True, False or None.
        ai_boxes: Issue boxes to draw.
        focus_raw: Focus score of the frame on screen.
        live_badge_rect: Clickable FROZEN badge from the last paint, or None.
    """

    zoom_changed = Signal(float)
    tool_finished = Signal()
    calibrate_measured = Signal(float)
    overlay_changed = Signal()
    live_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image: QImage | None = None
        self.live_image: QImage | None = None
        self.frozen = False
        self.zoom = geometry.ZOOM_MIN
        self.pan = QPointF()
        self.split = DEFAULT_SPLIT
        self.grid = False
        self.recording_since: float | None = None
        self.status = CONNECTING_STATUS
        self.info: FrameInfo | None = None
        self.show_meters = True
        self.compare_image: QImage | None = None
        self.compare_mode = COMPARE_OFF
        self.compare_opacity = DEFAULT_OPACITY
        self.tool: str | None = None
        self.mm_per_px: float | None = None
        self.unit = "mm"
        self.scale_ok: bool | None = None
        self.ai_boxes: list[AiBox] = []
        self.focus_raw: float | None = None
        self.live_badge_rect: QRectF | None = None
        self.toasts = Toasts()
        self.overlays = OverlayModel(self._overlay_edited)
        signals = ToolSignals(self.tool_finished.emit, self.calibrate_measured.emit)
        self.tools = ToolController(self.overlays, signals, self)
        self._pointer = PointerHandler(self)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        policy = QSizePolicy.Policy.Expanding
        self.setSizePolicy(policy, policy)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._housekeeping)
        self._tick.start(HOUSEKEEPING_MS)

    def set_frame(self, info: FrameInfo) -> None:
        """Take a new frame; it reaches the screen unless the view is frozen."""
        self.info = info
        self.live_image = info.image
        if not self.frozen:
            self.image = info.image
            self.focus_raw = info.focus_raw
        self.update()

    def set_frozen(self, frozen: bool) -> None:
        """Freeze the frame on screen, or return to the latest live frame."""
        self.frozen = frozen
        if not frozen and self.live_image is not None:
            self.image = self.live_image
        self.update()

    def toast(self, text: str, seconds: float = DEFAULT_TOAST_SECONDS) -> None:
        """Show a short message for ``seconds``."""
        self.toasts.add(text, seconds, time.monotonic())
        self.update()

    def set_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        """Zoom to ``zoom``, clamped to 1 to 8, keeping the image point under ``anchor``.

        Args:
            zoom: Requested zoom factor.
            anchor: Widget position that stays fixed, or None to keep the pan.
        """
        target = geometry.clamp_zoom(zoom)
        image = self.image
        if anchor is not None and image is not None and target != self.zoom:
            after = geometry.image_rect(self.size(), image.size(), target)
            self.pan = geometry.anchored_pan(anchor, self.image_rect(), after)
        self.zoom = target
        if target == geometry.ZOOM_MIN:
            self.pan = QPointF()
        self.zoom_changed.emit(target)
        self.update()

    def set_tool(self, tool: str | None) -> None:
        """Select a tool by name, or None to pan; drops any item in progress."""
        self.tool = tool
        self.overlays.current = None
        cursor = Qt.CursorShape.CrossCursor if tool else Qt.CursorShape.OpenHandCursor
        self.setCursor(cursor)
        self.update()

    def overlay(self) -> OverlaySnapshot:
        """Finished measurements and annotations with the current scale and unit."""
        return self.overlays.snapshot(self.mm_per_px, self.unit)

    def image_rect(self) -> QRectF:
        """Where the image is drawn; the whole widget while there is no image."""
        if self.image is None:
            return QRectF(self.rect())
        return geometry.image_rect(self.size(), self.image.size(), self.zoom, self.pan)

    def mapper(self) -> ImageMapper | None:
        """Coordinate mapping for the image on screen, or None without an image."""
        if self.image is None:
            return None
        return ImageMapper(self.image_rect(), self.image.size())

    def _overlay_edited(self) -> None:
        """Announce an overlay change and repaint."""
        self.overlay_changed.emit()
        self.update()

    def _housekeeping(self) -> None:
        """Repaint while toasts expire or the recording timer runs."""
        if self.toasts.pending or self.recording_since is not None:
            self.update()

    def _paint_event(self, event: QPaintEvent) -> None:
        """Paint the frame, overlays and badges."""
        painter = QPainter(self)
        try:
            paint_view(self, painter)
        finally:
            painter.end()

    def _mouse_press_event(self, event: QMouseEvent) -> None:
        """Forward a button press to the pointer handler."""
        self._pointer.press(event)

    def _mouse_move_event(self, event: QMouseEvent) -> None:
        """Forward pointer movement to the pointer handler."""
        self._pointer.move(event)

    def _mouse_release_event(self, event: QMouseEvent) -> None:
        """Forward a button release to the pointer handler."""
        self._pointer.release(event)

    def _mouse_double_click_event(self, event: QMouseEvent) -> None:
        """Forward a double click to the pointer handler."""
        self._pointer.double_click(event)

    def _wheel_event(self, event: QWheelEvent) -> None:
        """Forward a wheel movement to the pointer handler."""
        self._pointer.wheel(event)

    paintEvent = _paint_event
    mousePressEvent = _mouse_press_event
    mouseMoveEvent = _mouse_move_event
    mouseReleaseEvent = _mouse_release_event
    mouseDoubleClickEvent = _mouse_double_click_event
    wheelEvent = _wheel_event
