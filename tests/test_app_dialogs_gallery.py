"""Tests for tower_borescope.app.dialogs.gallery: listing sandbox captures with sidecar
metadata, opening, revealing, choosing a reference and deleting."""

from __future__ import annotations

import os
import time

import cv2
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton

from tower_borescope.app.dialogs import gallery
from tower_borescope.app.dialogs.gallery import (
    THUMB_SIZE,
    GalleryWindow,
    describe_capture,
    thumbnail,
)
from tower_borescope.capture import ffmpeg
from tower_borescope.capture.recorder import Recorder, RecorderOptions
from tower_borescope.capture.storage import sidecar_path, write_sidecar
from tower_borescope.config import data_paths

VIDEO_WIDTH = 320
VIDEO_HEIGHT = 240
VIDEO_BGR = (40, 160, 90)
VIDEO_FRAMES = 5
COLOR_TOLERANCE = 12

needs_ffmpeg = pytest.mark.skipif(
    ffmpeg.find_ffmpeg() is None, reason="ffmpeg is not installed"
)


@pytest.fixture
def captures():
    paths = data_paths()
    paths.pictures.mkdir(parents=True)
    paths.movies.mkdir(parents=True)
    older = paths.pictures / "scope_20260101_120000.png"
    newer = paths.pictures / "scope_20260102_120000_stack.png"
    for index, path in enumerate((older, newer)):
        cv2.imwrite(str(path), np.full((48, 64, 3), 40 * (index + 1), np.uint8))
    write_sidecar(older, {"kind": "snapshot", "camera": "1280x720", "enhance": False})
    write_sidecar(newer, {"kind": "stack", "mm_per_px": 0.05, "contrast": 1.0})
    stamp = time.time()
    os.utime(older, (stamp - 60, stamp - 60))
    return paths, older, newer


def button_named(window, text):
    return next(b for b in window.findChildren(QPushButton) if b.text() == text)


def test_lists_captures_newest_first_without_sidecars(qapp, captures):
    paths, older, newer = captures
    window = GalleryWindow([paths.pictures, paths.movies])
    assert window.list.count() == 2
    assert window.windowTitle() == "Captures  (2)"
    first = window.list.item(0)
    assert first.text() == newer.name
    assert first.data(Qt.ItemDataRole.UserRole) == str(newer)
    assert all(
        b.focusPolicy() == Qt.FocusPolicy.NoFocus
        for b in window.findChildren(QPushButton)
    )


def test_selection_shows_metadata(qapp, captures):
    paths, older, newer = captures
    window = GalleryWindow([paths.pictures])
    assert window.info.text() == "Select a capture."
    window.list.setCurrentRow(0)
    text = window.info.text()
    assert newer.name in text
    assert "64 x 48" in text
    assert "kind: stack" in text
    assert "0.0500 mm/px (calibrated)" in text
    assert "contrast" not in text
    window.list.setCurrentRow(1)
    assert "camera: 1280x720" in window.info.text()
    assert "enhance" not in window.info.text()


def test_describe_capture_reports_size(captures):
    _, older, _ = captures
    assert " KB" in describe_capture(older)


def test_delete_asks_and_removes_the_sidecar(qapp, captures, monkeypatch):
    paths, older, newer = captures
    window = GalleryWindow([paths.pictures])
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: answers.pop(0))
    window.list.setCurrentRow(0)
    button_named(window, "Delete...").click()
    assert newer.exists()
    window.list.setCurrentRow(0)
    button_named(window, "Delete...").click()
    assert not newer.exists()
    assert not sidecar_path(newer).exists()
    assert window.list.count() == 1


def test_open_reveal_and_reference(qapp, captures, monkeypatch):
    paths, _, newer = captures
    opened, revealed, chosen = [], [], []
    monkeypatch.setattr(gallery.QDesktopServices, "openUrl", opened.append)
    monkeypatch.setattr(gallery.subprocess, "Popen", revealed.append)
    window = GalleryWindow([paths.pictures])
    window.use_as_reference.connect(chosen.append)
    button_named(window, "Open").click()
    assert opened == []
    window.list.setCurrentRow(0)
    button_named(window, "Open").click()
    button_named(window, "Show in Finder").click()
    button_named(window, "Use as compare reference").click()
    assert opened[0].toLocalFile() == str(newer)
    assert revealed == [["open", "-R", str(newer)]]
    assert chosen == [str(newer)]
    window.list.itemDoubleClicked.emit(window.list.item(0))
    assert len(opened) == 2


def test_refresh_picks_up_new_captures(qapp, captures):
    paths, _, _ = captures
    window = GalleryWindow([paths.pictures])
    cv2.imwrite(str(paths.pictures / "scope_20260103_120000.png"), np.zeros((8, 8, 3)))
    button_named(window, "Refresh").click()
    assert window.list.count() == 3


def test_unreadable_capture_gets_a_placeholder_thumbnail(qapp, tmp_path):
    broken = tmp_path / "scope_broken.mp4"
    broken.write_bytes(b"not a video")
    assert gallery._video_pixmap(broken, THUMB_SIZE).isNull()
    assert not thumbnail(broken).isNull()
    assert not thumbnail(tmp_path / "missing.png").isNull()


def test_video_without_ffmpeg_gets_a_placeholder_thumbnail(qapp, tmp_path, monkeypatch):
    clip = tmp_path / "scope_clip.mov"
    clip.write_bytes(b"")
    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: None)
    assert gallery._video_pixmap(clip, THUMB_SIZE).isNull()
    assert not thumbnail(clip).isNull()


def _record_solid_video(path, raw):
    frame = np.full((VIDEO_HEIGHT, VIDEO_WIDTH, 3), VIDEO_BGR, np.uint8)
    jpeg = cv2.imencode(".jpg", frame)[1].tobytes()
    video = Recorder(RecorderOptions(path, raw=raw, size=(VIDEO_WIDTH, VIDEO_HEIGHT)))
    for _ in range(VIDEO_FRAMES):
        video.write(jpeg, frame)
    return video.close()


@needs_ffmpeg
@pytest.mark.parametrize(
    ("name", "raw"), [("scope_processed.mp4", False), ("scope_raw.mov", True)]
)
def test_video_thumbnail_is_the_first_frame_in_a_red_frame(qapp, name, raw):
    path = data_paths().movies / name
    recorded = _record_solid_video(path, raw)
    if not recorded and not raw:
        pytest.skip("this ffmpeg cannot encode H.264 with VideoToolbox")
    assert recorded
    image = gallery._video_pixmap(path, THUMB_SIZE).toImage()
    assert (image.width(), image.height()) == (THUMB_SIZE.width(), THUMB_SIZE.height())
    border = image.pixelColor(0, 0)
    assert (border.blue(), border.green(), border.red()) == gallery.VIDEO_FRAME_COLOR
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    channels = (center.blue(), center.green(), center.red())
    for channel, expected in zip(channels, VIDEO_BGR, strict=True):
        assert abs(channel - expected) <= COLOR_TOLERANCE
    assert not thumbnail(path).isNull()
