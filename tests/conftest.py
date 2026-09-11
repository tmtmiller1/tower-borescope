"""Shared pytest configuration for tower_borescope.

Every test runs with data locations pointed at a temporary folder, so no test reads or
writes real settings, captures or reports. Tests that need the borescope hardware or a
live local model are collected but skipped unless the matching option is given.

Window tests share ``wait_until``, the ``qt_sandbox`` fixture (INI settings under the
test folder, no real microphones) and the ``window`` fixture (a shown ``MainWindow``
streaming from ``FakeReader``). Test modules import the helper with
``from conftest import wait_until``.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from tower_borescope.app.window.main_window import MainWindow
    from tower_borescope.capture.ffmpeg import AudioDevice

CAMERA_OPTION = "--camera"
LIVE_AI_OPTION = "--live-ai"
SANDBOX_VARIABLES = ("PICTURES_DIR", "MOVIES_DIR", "REPORTS_DIR")
APP_EXECUTABLE_SUFFIX = "Tower Borescope.app/Contents/MacOS/Tower Borescope"
WAIT_TIMEOUT = 8.0
POLL_INTERVAL = 0.01


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the hardware and live-model opt-in options."""
    parser.addoption(
        CAMERA_OPTION,
        action="store_true",
        help="Run tests that need the borescope plugged in.",
    )
    parser.addoption(
        LIVE_AI_OPTION,
        action="store_true",
        help="Run tests that send frames to a local vision model.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip marked tests whose opt-in option is absent."""
    for marker, option in (("camera", CAMERA_OPTION), ("live_ai", LIVE_AI_OPTION)):
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=f"needs {option}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def sandbox_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point settings, pictures, movies and reports at a per-test folder."""
    for name in SANDBOX_VARIABLES:
        monkeypatch.setenv(f"TOWER_BORESCOPE_{name}", str(tmp_path / name.lower()))
    monkeypatch.setenv("TOWER_BORESCOPE_SETTINGS", str(tmp_path / "settings.json"))
    yield tmp_path


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    """One QApplication shared by every GUI test in the session."""
    from PySide6.QtWidgets import QApplication

    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def wait_until(condition: Callable[[], object], timeout: float = WAIT_TIMEOUT) -> bool:
    """Pump Qt events until ``condition`` holds or ``timeout`` seconds pass.

    Each pass delivers queued signals with ``processEvents`` and then sleeps briefly,
    which releases the interpreter lock so the pipeline thread keeps producing frames.
    ``QTest.qWait`` holds the lock and starves that thread, so it is not used here.

    Args:
        condition: Checked after every event pass; a truthy result ends the wait.
        timeout: Seconds to keep waiting.

    Returns:
        Whether ``condition`` held before the deadline passed.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if condition():
            return True
        time.sleep(POLL_INTERVAL)
    return bool(condition())


@pytest.fixture
def audio_devices() -> list[AudioDevice]:
    """Microphones the sandboxed window lists; none unless a test overrides this."""
    return []


@pytest.fixture
def qt_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, audio_devices: list[AudioDevice]
) -> Iterator[Path]:
    """Keep QSettings in an INI file under the test folder and list no real microphone.

    The native settings format is restored afterwards.
    """
    from PySide6.QtCore import QSettings

    from tower_borescope.app.window import capture_controller

    monkeypatch.setattr(capture_controller, "list_audio_devices", lambda: audio_devices)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    yield tmp_path
    QSettings.setDefaultFormat(QSettings.Format.NativeFormat)


@pytest.fixture
def window(qapp: QApplication, qt_sandbox: Path) -> Iterator[MainWindow]:
    """A shown ``MainWindow`` streaming from ``FakeReader`` with sandboxed settings.

    Windows closed by earlier tests are deleted first. The fixture yields once the
    pipeline has produced a frame and the view has drawn it: the view is filled by a
    queued signal, so waiting on the pipeline alone leaves it empty now and then. A
    window that never gets that far is closed, so its pipeline thread does not outlive
    the failed setup.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    from fakes import FakeReader
    from tower_borescope.app.window.main_window import MainWindow
    from tower_borescope.config import SettingsStore

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    win = MainWindow(
        store=SettingsStore(qt_sandbox / "settings.json"), source_factory=FakeReader
    )
    win.show()
    ready = wait_until(
        lambda: win.view.image is not None and win.pipeline.last_frame is not None
    )
    if not ready:
        state = (win.pipeline.last_frame is not None, win.view.image is not None)
        win.close()
        pytest.fail(f"no frame within {WAIT_TIMEOUT} s (pipeline, view) = {state}")
    yield win
    win.close()


def _running_app_pids() -> list[int]:
    """PIDs of a running Tower Borescope process, excluding this process's ancestors."""
    listing = subprocess.run(
        ["ps", "-Ao", "pid=,ppid=,command="], capture_output=True, text=True, check=False
    ).stdout
    parents: dict[int, tuple[int, str]] = {}
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            parents[int(fields[0])] = (int(fields[1]), fields[2])
    ancestors: set[int] = set()
    pid = os.getpid()
    while pid in parents and pid not in ancestors:
        ancestors.add(pid)
        pid = parents[pid][0]
    return [
        candidate
        for candidate, (_, command) in parents.items()
        if candidate not in ancestors and _is_app_command(command)
    ]


def _is_app_command(command: str) -> bool:
    """True for the bundled application or the package run as a module."""
    executable = command.split(" ", 1)[0]
    if executable.endswith("MacOS/Tower Borescope") or APP_EXECUTABLE_SUFFIX in command:
        return True
    return "python" in Path(executable).name.lower() and "tower_borescope.app" in command


@pytest.fixture
def borescope_available() -> None:
    """Fail fast when the application already holds the camera or none is attached."""
    running = _running_app_pids()
    if running:
        pytest.fail(f"Quit Tower Borescope first; it holds the camera (pids {running})")
    from tower_borescope.device.camera import device_present

    if not device_present():
        pytest.fail("No supercamera found on USB")
