"""Shared state handed to window controllers: pipeline, view, settings and folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow

from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.app.view.video_view import VideoView
from tower_borescope.config import DataPaths, SettingsStore

ORGANIZATION: Final = "tower_borescope"
MISSING_FILE_TEXT: Final = "File no longer exists"


class Preferences:
    """The settings dictionary, saved through the store on every change.

    Attributes:
        store: Settings file.
        values: Current settings.
    """

    def __init__(self, store: SettingsStore) -> None:
        self.store = store
        self.values: dict[str, Any] = store.load()

    def remember(self, **changes: Any) -> None:
        """Update settings and save them.

        Args:
            **changes: Settings keys and their new values.
        """
        self.values.update(changes)
        self.store.save(self.values)


@dataclass(frozen=True, slots=True)
class WindowContext:
    """What the controllers share.

    Attributes:
        window: The main window, used as the parent of dialogs.
        pipeline: Frame processing thread.
        view: Video view.
        prefs: Saved settings.
        paths: Capture and report folders.
    """

    window: QMainWindow
    pipeline: Pipeline
    view: VideoView
    prefs: Preferences
    paths: DataPaths

    def toast(self, text: str) -> None:
        """Show a short message over the video."""
        self.view.toast(text)

    def capture_folders(self) -> list[Path]:
        """The pictures and movies folders."""
        return [self.paths.pictures, self.paths.movies]

    def open_path(self, path: Path) -> None:
        """Open a file, or a folder after creating it, in its default application.

        Args:
            path: A capture file, or a folder when it has no extension.
        """
        if not path.suffix:
            path.mkdir(parents=True, exist_ok=True)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.toast(MISSING_FILE_TEXT)
