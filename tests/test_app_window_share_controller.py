"""Tests for tower_borescope.app.window.share_controller and view_controller: the phone
monitor over local HTTP, the virtual camera, rotation, mirror, grid, zoom and the
sidebar."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

import pytest

from conftest import wait_until
from tower_borescope.app.pipeline import outputs
from tower_borescope.app.pipeline.outputs import VCAM_MISSING_TEXT
from tower_borescope.app.pipeline.thread import Pipeline
from tower_borescope.app.window import share_controller
from tower_borescope.app.window.view_controller import ROTATE_BLOCKED_TOAST
from tower_borescope.config import data_paths
from tower_borescope.measure.shapes import Annotation

JPEG_MAGIC = b"\xff\xd8"


def local_url(win, path=""):
    remote = win.pipeline.remote
    return f"http://127.0.0.1:{remote.port}/{path}?key={remote.access_key}"


def read_stream(url):
    with urllib.request.urlopen(url, timeout=3) as stream:
        return stream.read(4000)


def test_phone_monitor_serves_the_page_and_the_stream(window):
    window.share.toggle_remote()
    page = urllib.request.urlopen(local_url(window), timeout=3).read()
    assert b"/stream" in page
    head = read_stream(local_url(window, "stream"))
    assert b"image/jpeg" in head and JPEG_MAGIC in head
    window.share.stop_remote()


def test_phone_monitor_shows_a_qr_code_and_stops(window):
    window.share.toggle_remote()
    remote = window.pipeline.remote
    assert remote is not None
    assert window.share.qr is not None and window.share.qr.isVisible()
    label = window.share.group.remote_label.text()
    assert label.startswith("On: http://")
    assert label.endswith(f"/?key={remote.access_key}")
    assert window.share.qr.url.endswith(f"/?key={remote.access_key}")
    window.share.toggle_remote()
    assert window.pipeline.remote is None and window.share.qr is None
    assert window.share.group.remote_label.text() == "Off"


def test_phone_snapshot_button_saves_a_snapshot(window):
    window.share.toggle_remote()
    request = urllib.request.Request(local_url(window, "snapshot"), method="POST")
    urllib.request.urlopen(request, timeout=3).read()
    pictures = data_paths().pictures
    assert wait_until(lambda: any(pictures.glob("scope_*[0-9].png")))
    window.share.stop_remote()
    assert not window.share.group.remote_btn.isChecked()


def test_phone_monitor_refuses_requests_without_the_key(qapp, window):
    presses = []
    window.share._requests["snapshot"] = lambda: presses.append(1)
    window.share.toggle_remote()
    bare = f"http://127.0.0.1:{window.pipeline.remote.port}/snapshot"
    request = urllib.request.Request(bare, method="POST")
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request, timeout=3)
    assert refused.value.code == 403
    refused.value.close()
    qapp.processEvents()
    assert presses == []
    window.share.stop_remote()


def test_phone_record_button_requests_a_toggle(qapp, window):
    toggles = []
    window.share._requests["record"] = lambda: toggles.append(1)
    assert window.share._phone_record() is True
    assert wait_until(lambda: toggles == [1])
    window.share.remote_request.emit("unknown")
    qapp.processEvents()
    assert toggles == [1]


def test_phone_monitor_start_failure_is_reported(window, monkeypatch):
    class BusyServer:
        def __init__(self, on_snapshot, on_record):
            self.url = "http://127.0.0.1:1/"

        def start(self):
            raise OSError("address in use")

    monkeypatch.setattr(share_controller, "RemoteServer", BusyServer)
    window.share.toggle_remote()
    assert window.pipeline.remote is None
    assert not window.share.group.remote_btn.isChecked()
    toasts = window.view.toasts.visible(time.monotonic())
    assert "Could not start the phone monitor: address in use" in toasts


def test_virtual_camera_starts_or_refuses_gracefully(window):
    window.share.toggle_vcam()
    wait_until(lambda: False, 2.0)
    state = window.pipeline.state
    if state.want_vcam:
        window.share.toggle_vcam()
        assert wait_until(lambda: not state.want_vcam)
    else:
        assert not window.share.group.vcam_btn.isChecked()


@pytest.fixture
def window_without_pyvirtualcam(monkeypatch, request):
    """The window fixture built while pyvirtualcam appears not to be installed."""
    monkeypatch.setattr(outputs, "find_spec", lambda name: None)
    return request.getfixturevalue("window")


def test_virtual_camera_is_disabled_without_pyvirtualcam(window_without_pyvirtualcam):
    group = window_without_pyvirtualcam.share.group
    assert not group.vcam_btn.isEnabled() and not group.vcam_btn.isChecked()
    assert group.vcam_btn.toolTip() == VCAM_MISSING_TEXT
    assert not group.vcam_label.isHidden()
    assert group.vcam_label.text() == VCAM_MISSING_TEXT


def test_virtual_camera_is_offered_with_pyvirtualcam(window):
    group = window.share.group
    assert group.vcam_btn.isEnabled() and group.vcam_label.isHidden()


def test_rotation_mirror_grid_and_zoom(window):
    controls = window.view_controls
    controls.rotate_right()
    assert window.pipeline.state.rotation == 1
    controls.rotate_left()
    assert window.ctx.prefs.values["rotation"] == 0
    window.view.overlays.finish_item(Annotation("text", [(1.0, 1.0)], "x"))
    controls.orientation.mirror_check.setChecked(True)
    assert window.pipeline.state.mirror and window.menu_actions.mirror.isChecked()
    assert window.view.overlays.annotations == []
    controls.orientation.grid_check.setChecked(True)
    assert window.view.grid and window.menu_actions.grid.isChecked()
    controls.orientation.zoom_slider.set_value(200)
    assert window.view.zoom == 2.0


def test_view_zoom_moves_the_slider(window):
    window.view.set_zoom(3.0)
    assert window.view_controls.orientation.zoom_slider.value_label.text() == "3.0x"


def test_rotation_is_refused_while_recording_processed_video(window, monkeypatch):
    monkeypatch.setattr(Pipeline, "recording", property(lambda self: True))
    window.view_controls.rotate_right()
    assert window.pipeline.state.rotation == 0
    assert ROTATE_BLOCKED_TOAST in window.view.toasts.visible(time.monotonic())


def test_sidebar_toggle_follows_the_menu(window):
    window.view_controls.toggle_sidebar()
    assert window.sidebar.isHidden()
    assert not window.menu_actions.sidebar.isChecked()
    window.view_controls.toggle_sidebar()
    assert not window.sidebar.isHidden()
    assert window.menu_actions.sidebar.isChecked()
