"""Drawing of the video frame, compare modes, grid, AI boxes and meters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.view.ai_boxes import AiBox
from tower_borescope.app.view.badges import draw_badge, paint_hud, shade
from tower_borescope.app.view.geometry import split_position
from tower_borescope.app.view.overlay_painter import paint_overlays

if TYPE_CHECKING:
    from tower_borescope.app.view.video_view import VideoView

BACKGROUND = "#0f1012"
COMPARE_SPLIT = "split"
COMPARE_OVERLAY = "overlay"
SMOOTH_ZOOM_LIMIT = 2.5
DIVIDER_COLOR = "white"
DIVIDER_WIDTH = 2.0
COMPARE_BADGE_INSET = 12.0
GRID_COLOR = QColor(255, 220, 0, 140)
CROSSHAIR_COLOR = QColor(255, 60, 60, 220)
CROSSHAIR_ARM = 18.0
GRID_DIVISIONS = 3
SEVERITY_COLORS: Mapping[str, str] = MappingProxyType(
    {"high": "#ff5a3c", "medium": "#f0b429", "low": "#4c8dff", "info": "#9aa0a6"}
)
DEFAULT_SEVERITY = "info"
BOX_EDGE_ALPHA = 110
BOX_FILL_ALPHA = 28
BOX_RADIUS = 4.0
BRACKET_ARM = 18.0
BRACKET_WIDTH = 3.0
BOX_LABEL_ABOVE = 30.0
BOX_LABEL_ROOM = 34.0
BOX_LABEL_BELOW = 4.0
FOCUS_GOOD = 0.85
FOCUS_FAIR = 0.5
FOCUS_GOOD_COLOR = "#38c172"
FOCUS_FAIR_COLOR = "#f0b429"
FOCUS_POOR_COLOR = "#e3342f"
CLIPPED_WARNING = 0.02
CLIPPED_WARNING_COLOR = "#ff5a3c"
CLIPPED_NORMAL_COLOR = "#9aa0a6"
METER_TRACK_COLOR = "#3a3d44"
HISTOGRAM_BAR_COLOR = QColor(230, 230, 230, 200)
METER_FONT_SIZE = 10
METER_MARGIN = 16.0
PANEL_PAD = 6.0
PANEL_RADIUS = 6.0
FOCUS_BAR = QRectF(0.0, 0.0, 160.0, 10.0)
FOCUS_FROM_BOTTOM = 92.0
HISTOGRAM_SIZE = QRectF(0.0, 0.0, 128.0, 44.0)
HISTOGRAM_TOP_RECORDING = 50.0


def focus_color(focus: float) -> str:
    """Focus bar color: green above 0.85, amber above 0.5, red otherwise."""
    if focus > FOCUS_GOOD:
        return FOCUS_GOOD_COLOR
    if focus > FOCUS_FAIR:
        return FOCUS_FAIR_COLOR
    return FOCUS_POOR_COLOR


def clipped_text(clipped: float) -> str:
    """Histogram caption such as ``clipped 1.5%``."""
    return f"clipped {clipped * 100:.1f}%"


def paint_view(view: VideoView, painter: QPainter) -> None:
    """Paint the whole widget and record where the FROZEN badge went.

    Args:
        view: Widget being painted; its ``live_badge_rect`` is updated.
        painter: Active painter on ``view``.
    """
    painter.fillRect(view.rect(), QColor(BACKGROUND))
    mapper = view.mapper()
    image = view.image
    if mapper is not None and image is not None:
        _paint_image(view, painter, mapper.rect, image)
        if view.grid:
            paint_grid(painter, mapper.rect)
        paint_overlays(view, painter, mapper)
        if view.ai_boxes:
            paint_ai_boxes(painter, mapper.rect, view.ai_boxes)
        if view.info is not None and view.show_meters:
            paint_meters(view, painter, view.info)
    view.live_badge_rect = paint_hud(view, painter)


def paint_grid(painter: QPainter, rect: QRectF) -> None:
    """Rule-of-thirds grid with a centre crosshair.

    Args:
        painter: Active painter.
        rect: Drawn image rectangle.
    """
    painter.setPen(QPen(GRID_COLOR, 1))
    for step in range(1, GRID_DIVISIONS):
        x = rect.left() + rect.width() * step / GRID_DIVISIONS
        y = rect.top() + rect.height() * step / GRID_DIVISIONS
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
    centre = rect.center()
    painter.setPen(QPen(CROSSHAIR_COLOR, 2))
    arm = CROSSHAIR_ARM
    painter.drawLine(centre - QPointF(arm, 0), centre + QPointF(arm, 0))
    painter.drawLine(centre - QPointF(0, arm), centre + QPointF(0, arm))


def paint_ai_boxes(painter: QPainter, rect: QRectF, boxes: Sequence[AiBox]) -> None:
    """Issue boxes with corner brackets and numbered labels.

    Args:
        painter: Active painter.
        rect: Drawn image rectangle.
        boxes: Boxes in image fractions, numbered from 1 in order.
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for number, box in enumerate(boxes, 1):
        _paint_ai_box(painter, rect, number, box)


def paint_meters(view: VideoView, painter: QPainter, info: FrameInfo) -> None:
    """Focus bar in the bottom-left corner and histogram in the top-right corner.

    Args:
        view: Widget being painted.
        painter: Active painter on ``view``.
        info: Readings of the latest frame.
    """
    if info.focus is not None:
        _paint_focus(view, painter, info.focus)
    if info.hist is not None:
        _paint_histogram(view, painter, info.hist, info.clipped)


def _paint_image(view: VideoView, painter: QPainter, rect: QRectF, image: QImage) -> None:
    """The frame, split against or blended with the reference image."""
    smooth = view.zoom < SMOOTH_ZOOM_LIMIT
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
    compare = view.compare_image
    if view.compare_mode == COMPARE_SPLIT and compare is not None:
        _paint_split(view, painter, rect, image, compare)
        return
    painter.drawImage(rect, image)
    if view.compare_mode == COMPARE_OVERLAY and compare is not None:
        painter.setOpacity(view.compare_opacity)
        painter.drawImage(rect, compare)
        painter.setOpacity(1.0)


def _paint_split(
    view: VideoView, painter: QPainter, rect: QRectF, image: QImage, compare: QImage
) -> None:
    """Live frame left of the divider, reference image right of it."""
    divider = split_position(rect, view.split)
    painter.save()
    painter.setClipRect(
        QRectF(rect.left(), rect.top(), divider - rect.left(), rect.height())
    )
    painter.drawImage(rect, image)
    painter.restore()
    painter.save()
    painter.setClipRect(
        QRectF(divider, rect.top(), rect.right() - divider, rect.height())
    )
    painter.drawImage(rect, compare)
    painter.restore()
    painter.setPen(QPen(QColor(DIVIDER_COLOR), DIVIDER_WIDTH))
    painter.drawLine(QPointF(divider, rect.top()), QPointF(divider, rect.bottom()))
    top = rect.top() + COMPARE_BADGE_INSET
    live_label = "FROZEN" if view.frozen else "LIVE"
    draw_badge(
        painter, live_label, QPointF(rect.left() + COMPARE_BADGE_INSET, top), shade()
    )
    draw_badge(painter, "REFERENCE", QPointF(divider + COMPARE_BADGE_INSET, top), shade())


def _with_alpha(color: QColor, alpha: int) -> QColor:
    """Copy of ``color`` with a different alpha."""
    faded = QColor(color)
    faded.setAlpha(alpha)
    return faded


def _paint_ai_box(painter: QPainter, rect: QRectF, number: int, box: AiBox) -> None:
    """One translucent box with bright corner brackets and a numbered label."""
    color = QColor(SEVERITY_COLORS.get(box.severity, SEVERITY_COLORS[DEFAULT_SEVERITY]))
    frame = QRectF(
        rect.left() + box.x0 * rect.width(),
        rect.top() + box.y0 * rect.height(),
        (box.x1 - box.x0) * rect.width(),
        (box.y1 - box.y0) * rect.height(),
    )
    painter.setPen(QPen(_with_alpha(color, BOX_EDGE_ALPHA), 1.5))
    painter.setBrush(_with_alpha(color, BOX_FILL_ALPHA))
    painter.drawRoundedRect(frame, BOX_RADIUS, BOX_RADIUS)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, BRACKET_WIDTH))
    _paint_brackets(painter, frame)
    room_above = frame.top() > rect.top() + BOX_LABEL_ROOM
    label_top = (
        frame.top() - BOX_LABEL_ABOVE if room_above else frame.bottom() + BOX_LABEL_BELOW
    )
    origin = QPointF(frame.left(), label_top)
    draw_badge(painter, f"{number}  {box.label}", origin, color)


def _paint_brackets(painter: QPainter, frame: QRectF) -> None:
    """Short lines along both edges at each corner of ``frame``."""
    arm = min(BRACKET_ARM, frame.width() / 3, frame.height() / 3)
    for corner_x, sign_x in ((frame.left(), 1), (frame.right(), -1)):
        for corner_y, sign_y in ((frame.top(), 1), (frame.bottom(), -1)):
            corner = QPointF(corner_x, corner_y)
            painter.drawLine(corner, QPointF(corner_x + sign_x * arm, corner_y))
            painter.drawLine(corner, QPointF(corner_x, corner_y + sign_y * arm))


def _paint_focus(view: VideoView, painter: QPainter, focus: float) -> None:
    """Focus bar with its caption."""
    bar = FOCUS_BAR.translated(METER_MARGIN, view.height() - FOCUS_FROM_BOTTOM)
    panel = bar.adjusted(-PANEL_PAD, -22.0, PANEL_PAD, 20.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shade())
    painter.drawRoundedRect(panel, PANEL_RADIUS, PANEL_RADIUS)
    painter.setBrush(QColor(METER_TRACK_COLOR))
    painter.drawRoundedRect(bar, BOX_RADIUS, BOX_RADIUS)
    painter.setBrush(QColor(focus_color(focus)))
    filled = QRectF(bar.left(), bar.top(), bar.width() * focus, bar.height())
    painter.drawRoundedRect(filled, BOX_RADIUS, BOX_RADIUS)
    painter.setPen(QColor(DIVIDER_COLOR))
    painter.setFont(QFont(view.font().family(), METER_FONT_SIZE))
    caption = QRectF(bar.left(), bar.top() - 20.0, bar.width(), 16.0)
    painter.drawText(caption, Qt.AlignmentFlag.AlignLeft, f"FOCUS  {focus * 100:.0f}")


def _paint_histogram(
    view: VideoView, painter: QPainter, hist: NDArray[np.float32], clipped: float
) -> None:
    """Luminance histogram with the clipped-highlight percentage below it."""
    recording = view.recording_since is not None
    top = HISTOGRAM_TOP_RECORDING if recording else METER_MARGIN
    left = view.width() - HISTOGRAM_SIZE.width() - METER_MARGIN
    area = HISTOGRAM_SIZE.translated(left, top)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shade())
    painter.drawRoundedRect(
        area.adjusted(-PANEL_PAD, -PANEL_PAD, PANEL_PAD, 18.0), PANEL_RADIUS, PANEL_RADIUS
    )
    bin_width = area.width() / max(len(hist), 1)
    painter.setBrush(HISTOGRAM_BAR_COLOR)
    for index, value in enumerate(hist):
        bar = float(value) * area.height()
        left_edge = area.left() + index * bin_width
        painter.drawRect(
            QRectF(left_edge, area.bottom() - bar, max(bin_width - 0.5, 1.0), bar)
        )
    warning = clipped > CLIPPED_WARNING
    painter.setPen(QColor(CLIPPED_WARNING_COLOR if warning else CLIPPED_NORMAL_COLOR))
    painter.setFont(QFont(view.font().family(), METER_FONT_SIZE))
    caption = QRectF(area.left(), area.bottom() + 2.0, area.width(), 16.0)
    painter.drawText(caption, Qt.AlignmentFlag.AlignLeft, clipped_text(clipped))
