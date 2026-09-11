"""PyInstaller entry point for the Tower Borescope application bundle.

The camera reader runs in a spawned process. ``multiprocessing.freeze_support`` lets
the frozen executable act as that child process when multiprocessing re-launches it.
"""

from __future__ import annotations

import multiprocessing
import sys

from tower_borescope.app.main import run_app


def main() -> int:
    """Start the application with the process arguments.

    Returns:
        The Qt event loop exit status.
    """
    multiprocessing.freeze_support()
    return run_app(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
