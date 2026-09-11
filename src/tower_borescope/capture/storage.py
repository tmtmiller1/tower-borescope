"""Capture file naming, JSON metadata sidecars and capture listing."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov", ".mkv", ".avi")
CAPTURE_PREFIX = "scope_"
SIDECAR_EXTENSION = ".json"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
SIDECAR_INDENT = 1


def timestamp() -> str:
    """Local time formatted as ``YYYYmmdd_HHMMSS`` for capture file names."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def capture_path(folder: str | Path, suffix: str, extension: str) -> Path:
    """Build a new capture path in ``folder``, creating the folder.

    The ``scope_`` prefix matches the files already in the capture folders, so new
    captures sort alongside them.

    Args:
        folder: Destination folder.
        suffix: Text after the timestamp, such as ``"_stack"``, or empty.
        extension: File extension including the dot, such as ``".png"``.

    Returns:
        ``folder / "scope_<timestamp><suffix><extension>"``.
    """
    directory = Path(folder)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{CAPTURE_PREFIX}{timestamp()}{suffix}{extension}"


def sidecar_path(path: str | Path) -> Path:
    """Metadata file for a capture: the same name with a ``.json`` extension."""
    return Path(path).with_suffix(SIDECAR_EXTENSION)


def write_sidecar(path: str | Path, meta: Mapping[str, Any]) -> Path:
    """Write capture metadata next to the capture.

    Args:
        path: The capture file.
        meta: JSON-serializable metadata.

    Returns:
        The sidecar file written.

    Raises:
        OSError: When the sidecar cannot be written.
    """
    destination = sidecar_path(path)
    destination.write_text(
        json.dumps(dict(meta), indent=SIDECAR_INDENT), encoding="utf-8"
    )
    return destination


def read_sidecar(path: str | Path) -> dict[str, Any]:
    """Read capture metadata.

    Args:
        path: The capture file.

    Returns:
        The metadata, or an empty dictionary when the sidecar is missing, unreadable or
        not a JSON object.
    """
    try:
        data = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_capture_name(name: str) -> bool:
    """True for names that are neither hidden files nor sidecars."""
    return not name.startswith(".") and not name.endswith(SIDECAR_EXTENSION)


def _modified_captures(folder: Path) -> list[tuple[float, Path]]:
    """``(modification time, path)`` for each capture file directly in ``folder``."""
    entries: list[tuple[float, Path]] = []
    if not folder.is_dir():
        return entries
    for entry in folder.iterdir():
        if not _is_capture_name(entry.name):
            continue
        try:
            if entry.is_file():
                entries.append((entry.stat().st_mtime, entry))
        except OSError:
            continue
    return entries


def list_captures(folders: Iterable[str | Path], limit: int | None = None) -> list[Path]:
    """List capture files across folders, newest first.

    Directories, hidden files and ``.json`` sidecars are left out.

    Args:
        folders: Folders to scan; missing folders are skipped.
        limit: Maximum number of files; None or 0 returns every file.

    Returns:
        Capture paths ordered by modification time, most recent first.
    """
    entries: list[tuple[float, Path]] = []
    for folder in folders:
        entries.extend(_modified_captures(Path(folder)))
    entries.sort(key=lambda entry: entry[0], reverse=True)
    paths = [path for _, path in entries]
    return paths[:limit] if limit else paths
