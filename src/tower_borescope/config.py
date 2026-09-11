"""Runtime configuration: environment files, data locations and the settings store.

Values that differ between machines (service endpoints, native library locations
and data folders) come from environment variables with the ``TOWER_BORESCOPE_``
prefix. The process environment is read first, then ``.env`` files, so a
development checkout and the installed application share one mechanism.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

APP_NAME = "Tower Borescope"
ENV_PREFIX = "TOWER_BORESCOPE_"
ENV_FILE_NAME = ".env"
SETTINGS_FILE_NAME = "settings.json"
CAPTURE_FOLDER_NAME = "Scope"
REPORT_FOLDER_NAME = "Scope Reports"
BUNDLE_ATTRIBUTE = "_MEIPASS"
LEGACY_SETTINGS_FILES: tuple[Path, ...] = (
    Path("Library") / "Application Support" / "Scope" / SETTINGS_FILE_NAME,
    Path("scope-camera") / SETTINGS_FILE_NAME,
)


def support_dir() -> Path:
    """Folder holding the settings file and the installed ``.env`` file."""
    return Path.home() / "Library" / "Application Support" / APP_NAME


def bundle_dir() -> Path | None:
    """Folder of the files packed into the application bundle.

    PyInstaller records the folder in ``sys._MEIPASS`` when the application runs from
    a bundle.

    Returns:
        The folder, or None when running from a source checkout.
    """
    location = getattr(sys, BUNDLE_ATTRIBUTE, None)
    return Path(location) if isinstance(location, str) else None


def bundled_file(*parts: str) -> Path | None:
    """A file packed into the application bundle.

    Args:
        *parts: Path segments below the bundle folder, such as ``"bin", "ffmpeg"``.

    Returns:
        The file, or None when it is absent or the application is not bundled.
    """
    root = bundle_dir()
    if root is None:
        return None
    candidate = root.joinpath(*parts)
    return candidate if candidate.is_file() else None


def env_value(name: str) -> str | None:
    """Return ``TOWER_BORESCOPE_<name>``, or None when it is unset or blank."""
    value = os.environ.get(f"{ENV_PREFIX}{name}", "").strip()
    return value or None


def load_environment(*extra_files: Path) -> list[Path]:
    """Load ``.env`` files without overriding variables that are already set.

    The installed file in :func:`support_dir` is read first, then each path in
    ``extra_files``; a development checkout passes its own ``.env``.

    Args:
        *extra_files: Additional ``.env`` files to read.

    Returns:
        The files that existed and were loaded.
    """
    loaded: list[Path] = []
    for candidate in (support_dir() / ENV_FILE_NAME, *extra_files):
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            loaded.append(candidate)
    return loaded


def install_env_template(template: Path) -> Path | None:
    """Copy ``template`` to the installed ``.env`` location when none exists.

    Args:
        template: The ``.env.example`` file shipped with the application.

    Returns:
        The destination when a copy was made, otherwise None.
    """
    destination = support_dir() / ENV_FILE_NAME
    if destination.exists() or not template.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, destination)
    return destination


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Locations of the settings file and the capture and report folders.

    Attributes:
        settings: JSON settings file.
        pictures: Folder for snapshots and stills.
        movies: Folder for recordings and time-lapses.
        reports: Folder for AI inspection reports.
    """

    settings: Path
    pictures: Path
    movies: Path
    reports: Path


def _path_from_env(name: str, default: Path) -> Path:
    """Path from ``TOWER_BORESCOPE_<name>``, falling back to ``default``."""
    value = env_value(name)
    return Path(value).expanduser() if value else default


def data_paths() -> DataPaths:
    """Resolve data locations from the environment at call time.

    Resolution happens on every call rather than at import, so tests and the
    camera reader process observe environment changes made after import.
    """
    home = Path.home()
    return DataPaths(
        settings=_path_from_env("SETTINGS", support_dir() / SETTINGS_FILE_NAME),
        pictures=_path_from_env("PICTURES_DIR", home / "Pictures" / CAPTURE_FOLDER_NAME),
        movies=_path_from_env("MOVIES_DIR", home / "Movies" / CAPTURE_FOLDER_NAME),
        reports=_path_from_env("REPORTS_DIR", home / "Documents" / REPORT_FOLDER_NAME),
    )


class SettingsStore:
    """JSON settings file that reads earlier locations once, until first saved.

    Attributes:
        path: File the settings are read from and saved to.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_paths().settings
        self._reads_legacy = path is None and env_value("SETTINGS") is None

    def _source(self) -> Path | None:
        """The current settings file, else the most recent legacy location."""
        if self.path.is_file():
            return self.path
        if not self._reads_legacy:
            return None
        for relative in LEGACY_SETTINGS_FILES:
            legacy = Path.home() / relative
            if legacy.is_file():
                return legacy
        return None

    def load(self) -> dict[str, Any]:
        """Return the settings, or an empty dictionary when no file is readable."""
        source = self._source()
        if source is None:
            return {}
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, settings: dict[str, Any]) -> bool:
        """Write ``settings`` as indented JSON.

        Args:
            settings: Complete settings dictionary.

        Returns:
            True when the file was written.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError:
            return False
        return True
