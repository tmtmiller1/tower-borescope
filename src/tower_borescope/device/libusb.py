"""Loading the pyusb libusb 1.0 backend.

The library is located from ``TOWER_BORESCOPE_LIBUSB_PATH`` when it is set, then from
the copy packed into the application bundle, then from the dynamic library search
path, then through the pyusb default lookup. Each source is tried in turn so a stale
configured path still falls back to an installed library.
"""

from __future__ import annotations

import ctypes.util
import logging
from collections.abc import Callable
from typing import Any, Final

import usb.backend.libusb1

from tower_borescope.config import bundled_file, env_value
from tower_borescope.errors import BorescopeError

LIBRARY_NAME: Final = "usb-1.0"
BUNDLED_LIBRARY: Final = "libusb-1.0.0.dylib"
PATH_VARIABLE: Final = "LIBUSB_PATH"
INSTALL_HINT: Final = (
    "libusb 1.0 could not be loaded. Install it with 'brew install libusb', or set "
    "TOWER_BORESCOPE_LIBUSB_PATH to the libusb-1.0 library file."
)

_LOGGER = logging.getLogger(__name__)


def _fixed_path(path: str) -> Callable[[str], str]:
    """A pyusb ``find_library`` callable that always answers ``path``."""

    def find(_candidate: str) -> str:
        return path

    return find


def library_candidates() -> list[str | None]:
    """Library locations to try, in order; None stands for the pyusb default lookup.

    Returns:
        The configured path when set, the bundled copy when present, the search-path
        result when found, then None.
    """
    candidates: list[str | None] = []
    configured = env_value(PATH_VARIABLE)
    if configured is not None:
        candidates.append(configured)
    bundled = bundled_file(BUNDLED_LIBRARY)
    if bundled is not None:
        candidates.append(str(bundled))
    found = ctypes.util.find_library(LIBRARY_NAME)
    if found and found not in candidates:
        candidates.append(found)
    candidates.append(None)
    return candidates


def load_backend() -> Any:
    """Return the pyusb libusb 1.0 backend.

    Returns:
        The backend object passed to ``usb.core.find``.

    Raises:
        BorescopeError: When no candidate location yields a working library.
    """
    for candidate in library_candidates():
        if candidate is None:
            backend = usb.backend.libusb1.get_backend()
        else:
            backend = usb.backend.libusb1.get_backend(find_library=_fixed_path(candidate))
        if backend is not None:
            return backend
        _LOGGER.debug("libusb not loaded from %s", candidate or "the default lookup")
    raise BorescopeError(INSTALL_HINT)
