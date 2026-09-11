"""Tests for tower_borescope.capture.storage: naming, sidecars and capture listing."""

from __future__ import annotations

import os
import re

from tower_borescope.capture import storage
from tower_borescope.capture.storage import (
    VIDEO_EXTENSIONS,
    capture_path,
    list_captures,
    read_sidecar,
    sidecar_path,
    timestamp,
    write_sidecar,
)
from tower_borescope.config import data_paths


def _touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"capture")
    os.utime(path, (mtime, mtime))
    return path


def test_timestamp_format():
    assert re.fullmatch(r"\d{8}_\d{6}", timestamp())


def test_capture_path_creates_folder_and_keeps_prefix(monkeypatch):
    monkeypatch.setattr(storage, "timestamp", lambda: "20260910_101112")
    folder = data_paths().pictures
    assert not folder.exists()
    path = capture_path(folder, "_stack", ".png")
    assert folder.is_dir()
    assert path == folder / "scope_20260910_101112_stack.png"


def test_sidecar_path_replaces_extension(tmp_path):
    assert sidecar_path(tmp_path / "scope_1_annotated.png") == (
        tmp_path / "scope_1_annotated.json"
    )
    assert sidecar_path(str(tmp_path / "clip.mp4")) == tmp_path / "clip.json"


def test_sidecar_round_trip(tmp_path):
    capture = tmp_path / "scope_1.png"
    meta = {"kind": "snapshot", "mm_per_px": 0.0125, "measurements": [{"kind": "line"}]}
    written = write_sidecar(capture, meta)
    assert written == tmp_path / "scope_1.json"
    assert read_sidecar(capture) == meta


def test_missing_or_invalid_sidecar_reads_empty(tmp_path):
    assert read_sidecar(tmp_path / "absent.png") == {}
    (tmp_path / "broken.json").write_text("{not json")
    assert read_sidecar(tmp_path / "broken.png") == {}
    (tmp_path / "listed.json").write_text("[1, 2]")
    assert read_sidecar(tmp_path / "listed.png") == {}


def test_list_captures_newest_first_and_filtered(tmp_path):
    pictures = tmp_path / "pictures"
    movies = tmp_path / "movies"
    oldest = _touch(pictures / "scope_a.png", 1_000)
    newest = _touch(movies / "scope_c.mp4", 3_000)
    middle = _touch(pictures / "scope_b.png", 2_000)
    _touch(pictures / "scope_b.json", 4_000)
    _touch(pictures / ".DS_Store", 5_000)
    (movies / "burst").mkdir()
    found = list_captures([pictures, movies, tmp_path / "missing"])
    assert found == [newest, middle, oldest]
    assert list_captures([str(pictures), str(movies)], limit=2) == [newest, middle]
    assert list_captures([pictures], limit=0) == [middle, oldest]


def test_video_extensions_cover_recording_containers():
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mov" in VIDEO_EXTENSIONS
