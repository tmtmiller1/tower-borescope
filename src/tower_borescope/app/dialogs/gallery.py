"""Capture gallery: browse every capture with its metadata, open, reveal or delete it,
or pick one as the compare reference."""

from __future__ import annotations

import contextlib
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

import cv2
from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tower_borescope.app.style import CONTROL
from tower_borescope.capture.ffmpeg import first_frame
from tower_borescope.capture.storage import (
    VIDEO_EXTENSIONS,
    list_captures,
    read_sidecar,
    sidecar_path,
)

THUMB_SIZE: Final = QSize(220, 124)
VIDEO_FRAME_COLOR: Final = (63, 74, 216)
VIDEO_FRAME_THICKNESS: Final = 6
TITLE: Final = "Captures"
EMPTY_INFO: Final = "Select a capture."
REVEAL_COMMAND: Final = "open"
BYTES_PER_MB: Final = 1e6
BYTES_PER_KB: Final = 1e3
INFO_WIDTH: Final = 260
META_KEYS: Final = (
    "kind",
    "camera",
    "enhance",
    "awb",
    "brightness",
    "contrast",
    "saturation",
    "stabilize",
    "denoise",
    "glare",
    "view_mode",
    "mm_per_px",
)
DEFAULT_VALUES: Final = (None, "", False, 0, 1.0)


def is_video(path: Path) -> bool:
    """True when ``path`` has a video extension."""
    return path.suffix.lower() in VIDEO_EXTENSIONS


def _video_pixmap(path: Path, size: QSize) -> QPixmap:
    """First frame of a video, decoded by ffmpeg, in a red frame marking it as video."""
    frame = first_frame(path, size.width(), size.height())
    if frame is None:
        return QPixmap()
    corner = (size.width() - 1, size.height() - 1)
    cv2.rectangle(frame, (0, 0), corner, VIDEO_FRAME_COLOR, VIDEO_FRAME_THICKNESS)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image.copy())


def thumbnail(path: Path, size: QSize = THUMB_SIZE) -> QIcon:
    """Icon for a capture: the image itself, or a video's first frame.

    Args:
        path: Capture file.
        size: Thumbnail bounds.

    Returns:
        The icon; a plain grey tile when the file cannot be read.
    """
    pixmap = _video_pixmap(path, size) if is_video(path) else QPixmap(str(path))
    if pixmap.isNull():
        pixmap = QPixmap(size)
        pixmap.fill(QColor(CONTROL))
    scaled = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QIcon(scaled)


def _file_size_text(size: int) -> str:
    """Size in megabytes above one megabyte, otherwise in kilobytes."""
    if size > BYTES_PER_MB:
        return f"{size / BYTES_PER_MB:.1f} MB"
    return f"{size / BYTES_PER_KB:.0f} KB"


def _meta_lines(path: Path) -> list[str]:
    """Sidecar values that differ from their defaults, one line each."""
    meta = read_sidecar(path)
    lines: list[str] = []
    for key in META_KEYS:
        value = meta.get(key)
        if key not in meta or value in DEFAULT_VALUES:
            continue
        if key == "mm_per_px" and isinstance(value, int | float):
            lines.append(f"{key}: {value:.4f} mm/px (calibrated)")
        else:
            lines.append(f"{key}: {value}")
    return lines


def describe_capture(path: Path) -> str:
    """Rich text with a capture's name, time, size, dimensions and settings.

    Args:
        path: Capture file.

    Returns:
        Lines joined with ``<br>``.
    """
    stat = path.stat()
    lines = [
        f"<b>{path.name}</b>",
        datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        _file_size_text(stat.st_size),
    ]
    if not is_video(path):
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            lines.append(f"{pixmap.width()} x {pixmap.height()}")
    lines.extend(_meta_lines(path))
    return "<br>".join(lines)


def open_file(path: Path) -> None:
    """Open a capture in its default application."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def reveal_file(path: Path) -> None:
    """Select a capture in Finder."""
    subprocess.Popen([REVEAL_COMMAND, "-R", str(path)])


class GalleryWindow(QDialog):
    """Grid of capture thumbnails with a details column and actions.

    Attributes:
        use_as_reference: Emitted with the path chosen as the compare reference.
        folders: Folders listed, newest capture first.
        list: Thumbnail grid.
        info: Details of the selected capture.
    """

    use_as_reference = Signal(str)

    def __init__(self, folders: Sequence[Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.folders = list(folders)
        self.setWindowTitle(TITLE)
        self.resize(1100, 720)
        self.list = self._make_list()
        self.info = QLabel(EMPTY_INFO)
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        self.info.setMinimumWidth(INFO_WIDTH)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        side = QVBoxLayout()
        side.addWidget(self.info, 1)
        for push in self._make_buttons():
            side.addWidget(push)
        layout = QHBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addLayout(side)
        self.reload()

    def _make_list(self) -> QListWidget:
        """The icon-mode thumbnail grid."""
        grid = QListWidget()
        grid.setViewMode(QListView.ViewMode.IconMode)
        grid.setIconSize(THUMB_SIZE)
        grid.setResizeMode(QListView.ResizeMode.Adjust)
        grid.setMovement(QListView.Movement.Static)
        grid.setSpacing(8)
        grid.setWordWrap(True)
        grid.itemSelectionChanged.connect(self._selected)
        grid.itemDoubleClicked.connect(self._double_clicked)
        return grid

    def _make_buttons(self) -> list[QPushButton]:
        """Open, reveal, reference, delete and refresh buttons."""
        actions: tuple[tuple[str, Callable[[], None]], ...] = (
            ("Open", lambda: self._with_selected(open_file)),
            ("Show in Finder", lambda: self._with_selected(reveal_file)),
            ("Use as compare reference", lambda: self._with_selected(self._reference)),
            ("Delete...", lambda: self._with_selected(self.delete)),
            ("Refresh", self.reload),
        )
        buttons: list[QPushButton] = []
        for text, slot in actions:
            push = QPushButton(text)
            push.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            push.clicked.connect(slot)
            buttons.append(push)
        return buttons

    def reload(self) -> None:
        """List the captures again and update the title count."""
        self.list.clear()
        for path in list_captures(self.folders):
            item = QListWidgetItem(thumbnail(path), path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setSizeHint(QSize(THUMB_SIZE.width() + 16, THUMB_SIZE.height() + 40))
            self.list.addItem(item)
        self.setWindowTitle(f"{TITLE}  ({self.list.count()})")

    def selected_path(self) -> Path | None:
        """Path of the selected capture, or None."""
        items = self.list.selectedItems()
        return Path(str(items[0].data(Qt.ItemDataRole.UserRole))) if items else None

    def _with_selected(self, action: Callable[[Path], None]) -> None:
        """Run ``action`` on the selected capture, if any."""
        path = self.selected_path()
        if path is not None:
            action(path)

    def _reference(self, path: Path) -> None:
        """Offer a capture as the compare reference."""
        self.use_as_reference.emit(str(path))

    def _double_clicked(self, item: QListWidgetItem) -> None:
        """Open the capture that was double-clicked."""
        open_file(Path(str(item.data(Qt.ItemDataRole.UserRole))))

    def _selected(self) -> None:
        """Show the details of the selected capture."""
        path = self.selected_path()
        if path is None or not path.exists():
            self.info.setText(EMPTY_INFO)
            return
        self.info.setText(describe_capture(path))

    def delete(self, path: Path) -> None:
        """Delete a capture and its sidecar after confirmation, then reload.

        Args:
            path: Capture file.
        """
        answer = QMessageBox.question(self, "Delete capture", f"Delete {path.name}?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        for target in (path, sidecar_path(path)):
            with contextlib.suppress(OSError):
                target.unlink()
        self.reload()
