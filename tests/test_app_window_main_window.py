"""Tests for tower_borescope.app.window.main_window with the FakeReader: streaming,
filters, annotated snapshots, freeze and compare, stills, recording with pre-roll,
time-lapse, resolution switching, the gallery, geometry and Esc."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from conftest import wait_until
from fakes import FakeReader
from tower_borescope.app.window.ai_panel import AiPanel
from tower_borescope.app.window.camera_panel import CameraPanel
from tower_borescope.app.window.capture_panel import CapturePanel
from tower_borescope.app.window.image_panel import ImagePanel
from tower_borescope.app.window.main_window import MainWindow
from tower_borescope.app.window.recent_panel import RecentPanel
from tower_borescope.app.window.tools_panel import CompareGroup, MeasureGroup
from tower_borescope.app.window.view_panel import OrientationGroup, ShareGroup
from tower_borescope.capture.ffmpeg import find_ffmpeg
from tower_borescope.config import APP_NAME, SettingsStore, data_paths
from tower_borescope.measure.shapes import Annotation, Measurement

MIN_PROCESSED_FPS = 15.0
needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="needs ffmpeg")


def pause(seconds):
    wait_until(lambda: False, seconds)


def make_window(tmp_path):
    return MainWindow(
        store=SettingsStore(tmp_path / "settings.json"), source_factory=FakeReader
    )


def test_streams_with_meters_and_statistics(window):
    view = window.view
    assert window.windowTitle() == APP_NAME
    assert view.image is not None
    assert wait_until(lambda: view.info is not None and view.info.hist is not None)
    assert view.info.focus is not None
    stats = window.camera.panel.stats_label
    assert wait_until(lambda: stats.text().startswith("1280x720"))
    assert window.camera.status_left.text() == "Streaming"


def test_tabs_menus_and_qt_bindings(window):
    tabs = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert tabs == ["Capture", "AI", "Image", "Tools", "View"]
    menus = [action.text() for action in window.menuBar().actions()]
    assert menus == ["File", "Camera", "Image", "Tools", "View", "AI", "Help"]
    assert MainWindow.closeEvent is MainWindow._close_event
    assert MainWindow.keyPressEvent is MainWindow._key_press_event
    assert window.sidebar.width() == 330


def test_panels_are_composed(window):
    assert isinstance(window.camera.panel, CameraPanel)
    assert isinstance(window.capture.panel, CapturePanel)
    assert isinstance(window.ai.panel, AiPanel)
    assert isinstance(window.image.panel, ImagePanel)
    assert isinstance(window.compare.group, CompareGroup)
    assert isinstance(window.measure.group, MeasureGroup)
    assert isinstance(window.view_controls.orientation, OrientationGroup)
    assert isinstance(window.share.group, ShareGroup)
    assert isinstance(window.capture.feedback.recent, RecentPanel)


@pytest.mark.timing
def test_every_filter_keeps_the_frame_rate(window):
    image = window.image.panel
    image.enhance_check.setChecked(True)
    image.awb_check.setChecked(True)
    image.stabilize_check.setChecked(True)
    image.denoise.set_value(60)
    image.glare.set_value(50)
    image.mode_combo.setCurrentText("Outline")
    pause(1.0)
    frames = []
    window.pipeline.frame_ready.connect(frames.append)
    pause(3.0)
    window.pipeline.frame_ready.disconnect(frames.append)
    assert len(frames) / 3.0 >= MIN_PROCESSED_FPS
    fps = float(window.camera.panel.stats_label.text().split()[1])
    assert fps >= 18.5
    assert window.pipeline.state.denoise == 0.6
    image.mode_combo.setCurrentText("Normal")


def test_snapshot_saves_annotated_copy_and_sidecar(window):
    window.image.panel.enhance_check.setChecked(True)
    view = window.view
    view.mm_per_px = 0.05
    measurement = Measurement("distance", [(100.0, 100.0), (500.0, 100.0)])
    view.overlays.finish_item(measurement)
    view.overlays.finish_item(Annotation("arrow", [(200.0, 300.0), (400.0, 380.0)]))
    view.overlays.finish_item(Annotation("text", [(600.0, 500.0)], "crack here"))
    assert measurement.label(0.05) == "20.00 mm"
    window.capture.snapshot()
    pictures = data_paths().pictures
    assert wait_until(lambda: len(list(pictures.glob("scope_*.json"))) == 2)
    plain = next(pictures.glob("scope_*[0-9].png"))
    assert next(pictures.glob("scope_*_annotated.png")).is_file()
    meta = json.loads(plain.with_suffix(".json").read_text())
    assert (meta["kind"], meta["camera"], meta["enhance"]) == (
        "snapshot",
        "1280x720",
        True,
    )
    view.overlays.undo()
    assert (len(view.overlays.annotations), len(view.overlays.measurements)) == (1, 1)


def test_freeze_holds_the_frame_and_reference_loads_split(window, tmp_path):
    view = window.view
    window.freeze.toggle_freeze()
    frozen = view.image
    pause(0.5)
    assert view.frozen and view.image is frozen
    window.freeze.toggle_freeze()
    assert not view.frozen
    reference = tmp_path / "reference.png"
    cv2.imwrite(str(reference), np.full((72, 128, 3), 90, np.uint8))
    window.compare.set_reference(str(reference))
    assert view.compare_image is not None and view.compare_mode == "split"
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Tools"
    window.compare.group.compare_combo.setCurrentIndex(2)
    assert view.compare_mode == "overlay"
    window.compare.group.compare_combo.setCurrentIndex(0)
    assert view.compare_mode == "off"


def test_burst_and_stacked_still(window):
    pictures = data_paths().pictures
    window.capture.panel.burst_btn.click()
    assert wait_until(lambda: any(pictures.glob("burst_*/burst_10.png")))
    window.capture.panel.stack_btn.click()
    assert wait_until(lambda: any(pictures.glob("scope_*_stack.png")), 20.0)
    stack_btn = window.capture.panel.stack_btn
    assert wait_until(lambda: stack_btn.text() == "Stacked still")
    assert stack_btn.isEnabled()


def video_frames(path):
    capture = cv2.VideoCapture(str(path))
    frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    capture.release()
    return int(frames)


@needs_ffmpeg
def test_recording_includes_the_preroll(window):
    frames = []
    window.pipeline.frame_ready.connect(frames.append)
    pause(3.0)
    before_press = len(frames)
    window.capture.panel.preroll_check.setChecked(True)
    window.capture.toggle_recording()
    assert wait_until(lambda: window.pipeline.recording)
    # The menu text follows the queued recording_changed signal, not the pipeline flag.
    record = window.menu_actions.record
    assert wait_until(lambda: record.text() == "Stop Recording")
    pause(2.0)
    window.capture.toggle_recording()
    pressed = len(frames) - before_press
    window.pipeline.frame_ready.disconnect(frames.append)
    movies = data_paths().movies
    assert wait_until(lambda: any(movies.glob("scope_*.json")), 20.0)
    video = next(movies.glob("scope_*.mp4"))
    # The pre-roll adds the frames seen before the press. Frame counts depend on the
    # machine's speed (a slow runner processes fewer of the paced fake frames), so the
    # check compares counts from the same run instead of assuming real-time rates.
    assert before_press >= 10 and pressed >= 10
    assert video_frames(video) >= pressed + before_press // 2
    # The sidecar lands before the queued recording_changed signal reaches the window.
    record_btn = window.capture.panel.record_btn
    assert wait_until(lambda: record_btn.text() == "Record")


@needs_ffmpeg
def test_timelapse_is_assembled_into_a_video(window):
    panel = window.capture.panel
    panel.timelapse_spin.setValue(1)
    window.capture.toggle_timelapse()
    assert wait_until(lambda: panel.timelapse_btn.text().startswith("Stop"))
    pause(4.2)
    window.capture.toggle_timelapse()
    movies = data_paths().movies
    assert wait_until(lambda: any(movies.glob("timelapse_*.mp4")), 20.0)
    assert panel.timelapse_btn.text() == "Start time-lapse"


def test_resolution_switching(window):
    view = window.view

    def dims():
        return tuple(sorted((view.image.width(), view.image.height())))

    window.camera.set_resolution("480p")
    assert wait_until(lambda: dims() == (480, 640))
    checked = window.menu_actions.resolutions.checkedAction()
    assert checked.text() == "640 x 480  (wider view)"
    assert window.ctx.prefs.values["mode"] == "480p"
    window.camera.set_resolution("720p")
    assert wait_until(lambda: dims() == (720, 1280))


def test_gallery_lists_captures_and_reloads(window):
    pictures = data_paths().pictures
    pictures.mkdir(parents=True, exist_ok=True)
    for index in range(3):
        cv2.imwrite(
            str(pictures / f"scope_2026010{index}_120000.png"), np.zeros((9, 16, 3))
        )
    window.show_gallery()
    assert window.gallery.list.count() == 3
    cv2.imwrite(str(pictures / "scope_20260109_120000.png"), np.zeros((9, 16, 3)))
    window.refresh_gallery()
    assert window.gallery.list.count() == 4
    window.gallery.close()
    window.show_gallery()
    assert window.gallery.isVisible()
    window.gallery.close()


def test_geometry_is_saved_and_restored(qapp, qt_sandbox):
    first = make_window(qt_sandbox)
    first.show()
    # Restoring clamps a window to its screen, and the offscreen platform used in CI has
    # an 800 x 600 screen, so the requested size stays inside the available area.
    area = first.screen().availableGeometry()
    target = (min(1000, area.width() - 100), min(650, area.height() - 100))
    first.resize(*target)
    qapp.processEvents()
    saved = (first.width(), first.height())
    first.close()
    second = make_window(qt_sandbox)
    try:
        assert (second.width(), second.height()) == saved
    finally:
        second.close()


def test_escape_cancels_the_tool_then_returns_to_live(window):
    window.measure.set_tool("distance")
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.view.tool is None
    window.freeze.set_frozen(True)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window.view.frozen
