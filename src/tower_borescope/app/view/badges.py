"""Rounded text badges, toasts and the heads-up display drawn over the video.

The heads-up display holds the status text, the recording timer, the clickable FROZEN
badge, the zoom factor, the active tool's hint and up to three toasts.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from tower_borescope.app.view.geometry import ZOOM_MIN

if TYPE_CHECKING:
    from tower_borescope.app.view.video_view import VideoView

ACCENT = "#3b6fd6"
RECORD_RED = "#d84a3f"
FROZEN_COLOR = "#b8860b"
STATUS_COLOR = "#f0b429"
TEXT_COLOR = "white"
FROZEN_TEXT = "FROZEN: click or Esc for live"
COMPARE_SPLIT = "split"
SHADE_ALPHA = 150
TOAST_ALPHA = 170
BADGE_FONT_SIZE = 12
TOAST_FONT_SIZE = 13
STATUS_FONT_SIZE = 15
BADGE_PAD_X = 20
BADGE_PAD_Y = 10
BADGE_RADIUS = 6.0
HUD_MARGIN = 16.0
BADGE_GAP = 10.0
ZOOM_BADGE_ADVANCE = 60.0
RECORD_BADGE_OFFSET = 130.0
TOAST_BOTTOM_OFFSET = 48.0
TOAST_SPACING = 34.0
MAX_TOASTS = 3
SECONDS_PER_MINUTE = 60
TOOL_HINTS: Mapping[str, str] = MappingProxyType(
    {
        "distance": "click 2 points",
        "angle": "click 3 points (vertex second)",
        "area": "click corners, double-click to close",
        "calibrate": "click both ends of a known length",
        "arrow": "drag",
        "circle": "drag from centre",
        "text": "click to place",
        "freehand": "drag to draw",
    }
)


def shade(alpha: int = SHADE_ALPHA) -> QColor:
    """Translucent black badge background."""
    return QColor(0, 0, 0, alpha)


def draw_badge(
    painter: QPainter,
    text: str,
    origin: QPointF,
    color: QColor,
    font_size: int = BADGE_FONT_SIZE,
) -> QRectF:
    """Draw white text on a rounded, filled rectangle.

    Args:
        painter: Active painter.
        text: Badge text.
        origin: Top-left corner of the badge.
        color: Fill color.
        font_size: Point size of the text.

    Returns:
        The rectangle the badge covers.
    """
    painter.setFont(QFont(painter.font().family(), font_size, QFont.Weight.DemiBold))
    metrics = painter.fontMetrics()
    width = metrics.horizontalAdvance(text) + BADGE_PAD_X
    height = metrics.height() + BADGE_PAD_Y
    rect = QRectF(origin.x(), origin.y(), width, height)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(rect, BADGE_RADIUS, BADGE_RADIUS)
    painter.setPen(QColor(TEXT_COLOR))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    return rect


def recording_text(elapsed_seconds: float) -> str:
    """Recording badge text such as ``REC  01:05``."""
    minutes, seconds = divmod(int(elapsed_seconds), SECONDS_PER_MINUTE)
    return f"REC  {minutes:02d}:{seconds:02d}"


def tool_hint(tool: str) -> str:
    """Hint badge text for the active tool."""
    return f"{tool}: {TOOL_HINTS.get(tool, '')}   (Esc cancels)"


class Toasts:
    """Short messages that disappear after a few seconds."""

    def __init__(self) -> None:
        self._items: list[tuple[str, float]] = []

    @property
    def pending(self) -> bool:
        """True while any message may still be showing."""
        return bool(self._items)

    def add(self, text: str, seconds: float, now: float) -> None:
        """Show ``text`` for ``seconds``, replacing an identical message.

        Args:
            text: Message.
            seconds: Display time.
            now: Monotonic time.
        """
        self._items = [item for item in self._items if item[0] != text]
        self._items.append((text, now + seconds))

    def visible(self, now: float) -> list[str]:
        """Drop expired messages and return the newest three, oldest first.

        Args:
            now: Monotonic time.

        Returns:
            Message texts to draw.
        """
        self._items = [item for item in self._items if item[1] > now]
        return [text for text, _ in self._items[-MAX_TOASTS:]]


def paint_hud(view: VideoView, painter: QPainter) -> QRectF | None:
    """Draw the status text and every badge over the video.

    Args:
        view: Widget being painted.
        painter: Active painter on ``view``.

    Returns:
        The clickable FROZEN badge rectangle, or None when it is not shown.
    """
    _paint_status(view, painter)
    _paint_recording(view, painter)
    left = HUD_MARGIN
    frozen_rect = None
    if view.frozen and view.compare_mode != COMPARE_SPLIT:
        origin = QPointF(left, HUD_MARGIN)
        frozen_rect = draw_badge(painter, FROZEN_TEXT, origin, QColor(FROZEN_COLOR))
        left += frozen_rect.width() + BADGE_GAP
    if view.zoom > ZOOM_MIN:
        draw_badge(painter, f"{view.zoom:.1f}x", QPointF(left, HUD_MARGIN), shade())
        left += ZOOM_BADGE_ADVANCE
    if view.tool:
        origin = QPointF(left, HUD_MARGIN)
        draw_badge(painter, tool_hint(view.tool), origin, QColor(ACCENT))
    _paint_toasts(view, painter)
    return frozen_rect


def _paint_status(view: VideoView, painter: QPainter) -> None:
    """Centred connection status text."""
    if not view.status:
        return
    painter.setPen(QColor(STATUS_COLOR))
    painter.setFont(QFont(view.font().family(), STATUS_FONT_SIZE))
    painter.drawText(QRectF(view.rect()), Qt.AlignmentFlag.AlignCenter, view.status)


def _paint_recording(view: VideoView, painter: QPainter) -> None:
    """Recording timer badge in the top-right corner."""
    since = view.recording_since
    if since is None:
        return
    origin = QPointF(view.width() - RECORD_BADGE_OFFSET, HUD_MARGIN)
    text = recording_text(time.monotonic() - since)
    draw_badge(painter, text, origin, QColor(RECORD_RED))


def _paint_toasts(view: VideoView, painter: QPainter) -> None:
    """Toasts stacked upward from the bottom-left corner, newest lowest."""
    top = view.height() - TOAST_BOTTOM_OFFSET
    for text in reversed(view.toasts.visible(time.monotonic())):
        origin = QPointF(HUD_MARGIN, top)
        draw_badge(painter, text, origin, shade(TOAST_ALPHA), TOAST_FONT_SIZE)
        top -= TOAST_SPACING
