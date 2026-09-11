"""Application start-up: environment files, the Qt application and the main window.

``run_app`` loads ``.env`` files, installs the configuration template on first launch,
builds the styled ``QApplication`` with the drawn icon and shows the main window. The
``--test-shot PATH`` option saves a picture of the window a few seconds after start-up
and quits, which is how the bundle and the tests confirm the window renders.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from tower_borescope.app.icon import draw_icon
from tower_borescope.app.style import STYLE_SHEET
from tower_borescope.app.window.main_window import ORGANIZATION, MainWindow
from tower_borescope.config import (
    APP_NAME,
    ENV_FILE_NAME,
    bundle_dir,
    install_env_template,
    load_environment,
)
from tower_borescope.device.reader import Reader

TEST_SHOT_OPTION: Final = "--test-shot"
TEST_SHOT_DELAY_MS = 6000
ENV_TEMPLATE_NAME: Final = ".env.example"
QT_STYLE: Final = "Fusion"
WINDOW_ICON_SIZE: Final = 256
BYTES_PER_PIXEL: Final = 4
EXIT_SHOT_FAILED: Final = 1
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]


def repository_env_file() -> Path | None:
    """The development checkout's ``.env``, when it exists."""
    candidate = REPOSITORY_ROOT / ENV_FILE_NAME
    return candidate if candidate.is_file() else None


def env_template() -> Path | None:
    """The ``.env.example`` bundled with the application, else the repository copy."""
    bundle = bundle_dir()
    roots = ([bundle] if bundle is not None else []) + [REPOSITORY_ROOT]
    for root in roots:
        candidate = root / ENV_TEMPLATE_NAME
        if candidate.is_file():
            return candidate
    return None


def shot_path_from(argv: Sequence[str]) -> Path | None:
    """The path after ``--test-shot`` in ``argv``, or None when absent or incomplete."""
    arguments = list(argv)
    if TEST_SHOT_OPTION not in arguments:
        return None
    index = arguments.index(TEST_SHOT_OPTION) + 1
    return Path(arguments[index]) if index < len(arguments) else None


def window_icon() -> QIcon:
    """The drawn lens icon as a Qt icon."""
    pixels = draw_icon(WINDOW_ICON_SIZE)
    height, width = pixels.shape[:2]
    # On little-endian machines ARGB32 stores blue, green, red, alpha: OpenCV's order.
    image = QImage(
        pixels.data, width, height, BYTES_PER_PIXEL * width, QImage.Format.Format_ARGB32
    )
    return QIcon(QPixmap.fromImage(image.copy()))


def build_application(argv: Sequence[str]) -> QApplication:
    """Create or reuse the ``QApplication`` and apply the name, style and icon.

    Args:
        argv: Process arguments including the program name.

    Returns:
        The configured application.
    """
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(list(argv))
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORGANIZATION)
    app.setStyle(QT_STYLE)
    app.setStyleSheet(STYLE_SHEET)
    app.setWindowIcon(window_icon())
    return app


def _prepare_environment() -> None:
    """Load ``.env`` files and install the template on first launch."""
    extra = repository_env_file()
    load_environment(*([extra] if extra is not None else []))
    template = env_template()
    if template is not None:
        install_env_template(template)


def _schedule_test_shot(app: QApplication, window: MainWindow, path: Path) -> None:
    """Save a picture of ``window`` after the start-up delay, then quit."""

    def shoot() -> None:
        saved = window.grab().save(str(path))
        if not saved:
            print(f"Could not save the test shot to {path}", file=sys.stderr)
        window.close()
        app.exit(0 if saved else EXIT_SHOT_FAILED)

    QTimer.singleShot(TEST_SHOT_DELAY_MS, shoot)


def run_app(argv: Sequence[str]) -> int:
    """Start the application and run the Qt event loop.

    Args:
        argv: Process arguments including the program name; ``--test-shot PATH``
            saves a window picture after start-up and quits.

    Returns:
        The event loop exit status.
    """
    _prepare_environment()
    app = build_application(argv)
    window = MainWindow(source_factory=Reader)
    window.show()
    shot = shot_path_from(argv)
    if shot is not None:
        _schedule_test_shot(app, window, shot)
    return app.exec()
