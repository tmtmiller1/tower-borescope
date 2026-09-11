"""Recent captures strip below the tabs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem

from tower_borescope.app.dialogs.gallery import thumbnail
from tower_borescope.app.widgets.layout import group
from tower_borescope.capture.storage import list_captures

ICON_SIZE: Final = QSize(96, 54)
THUMB_SIZE: Final = QSize(192, 108)
STRIP_HEIGHT: Final = 128
LOAD_LIMIT: Final = 12
KEEP_LIMIT: Final = 24


class RecentPanel:
    """Thumbnails of the latest captures; a double click opens one.

    Attributes:
        list: Thumbnail strip; item data holds the capture path.
        box: The RECENT CAPTURES group box.
    """

    def __init__(self, on_open: Callable[[Path], None]) -> None:
        self._on_open = on_open
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(ICON_SIZE)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setSpacing(4)
        self.list.setFixedHeight(STRIP_HEIGHT)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setToolTip("Double-click to open. Gallery... for everything.")
        self.list.itemDoubleClicked.connect(self._double_clicked)
        self.box = group("RECENT CAPTURES", self.list)

    def _double_clicked(self, item: QListWidgetItem) -> None:
        """Open the capture that was double-clicked."""
        self._on_open(Path(str(item.data(Qt.ItemDataRole.UserRole))))

    def load(self, folders: Sequence[Path]) -> None:
        """Show the newest captures from ``folders``."""
        for path in list_captures(folders, limit=LOAD_LIMIT):
            self.add(path)

    def add(self, path: Path, front: bool = False) -> None:
        """Add a capture at the end, or at the front for a new capture.

        Args:
            path: Capture file.
            front: Insert before the existing thumbnails.
        """
        item = QListWidgetItem(thumbnail(path, THUMB_SIZE), "")
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setToolTip(path.name)
        if front:
            self.list.insertItem(0, item)
        else:
            self.list.addItem(item)
        while self.list.count() > KEEP_LIMIT:
            self.list.takeItem(self.list.count() - 1)

    def paths(self) -> list[Path]:
        """Capture paths in display order."""
        items = (self.list.item(index) for index in range(self.list.count()))
        return [Path(str(item.data(Qt.ItemDataRole.UserRole))) for item in items]
