"""Tests for tower_borescope.device.libusb: library path selection and errors."""

from __future__ import annotations

import ctypes.util
import sys

import pytest
import usb.backend.libusb1

from tower_borescope.device import libusb
from tower_borescope.errors import BorescopeError

CONFIGURED = "configured/libusb-1.0.dylib"
SEARCHED = "libusb-1.0.0.dylib"


class FakeGetBackend:
    """Records each lookup and loads only the locations listed as working."""

    def __init__(self, working):
        self.working = set(working)
        self.tried = []

    def __call__(self, find_library=None):
        location = None if find_library is None else find_library("usb-1.0")
        self.tried.append(location)
        return f"backend:{location}" if location in self.working else None


def _install(monkeypatch, fake, searched=None):
    monkeypatch.setattr(usb.backend.libusb1, "get_backend", fake)
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: searched)


def test_configured_path_is_used_first(monkeypatch):
    monkeypatch.setenv("TOWER_BORESCOPE_LIBUSB_PATH", CONFIGURED)
    fake = FakeGetBackend({CONFIGURED})
    _install(monkeypatch, fake, searched=SEARCHED)
    assert libusb.load_backend() == f"backend:{CONFIGURED}"
    assert fake.tried == [CONFIGURED]


def test_library_search_path_is_used_without_configuration(monkeypatch):
    monkeypatch.delenv("TOWER_BORESCOPE_LIBUSB_PATH", raising=False)
    fake = FakeGetBackend({SEARCHED})
    _install(monkeypatch, fake, searched=SEARCHED)
    assert libusb.load_backend() == f"backend:{SEARCHED}"
    assert libusb.library_candidates() == [SEARCHED, None]


def test_bundled_library_follows_configuration(tmp_path, monkeypatch):
    bundled = tmp_path / libusb.BUNDLED_LIBRARY
    bundled.write_bytes(b"")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("TOWER_BORESCOPE_LIBUSB_PATH", CONFIGURED)
    _install(monkeypatch, FakeGetBackend(set()), searched=SEARCHED)
    assert libusb.library_candidates() == [CONFIGURED, str(bundled), SEARCHED, None]
    bundled.unlink()
    assert libusb.library_candidates() == [CONFIGURED, SEARCHED, None]


def test_default_lookup_is_the_last_resort(monkeypatch):
    monkeypatch.setenv("TOWER_BORESCOPE_LIBUSB_PATH", CONFIGURED)
    fake = FakeGetBackend({None})
    _install(monkeypatch, fake, searched=SEARCHED)
    assert libusb.load_backend() == "backend:None"
    assert fake.tried == [CONFIGURED, SEARCHED, None]


def test_blank_configuration_is_ignored(monkeypatch):
    monkeypatch.setenv("TOWER_BORESCOPE_LIBUSB_PATH", "  ")
    _install(monkeypatch, FakeGetBackend(set()), searched=None)
    assert libusb.library_candidates() == [None]


def test_missing_library_raises_with_install_hint(monkeypatch):
    monkeypatch.delenv("TOWER_BORESCOPE_LIBUSB_PATH", raising=False)
    _install(monkeypatch, FakeGetBackend(set()), searched=None)
    with pytest.raises(BorescopeError, match="brew install libusb"):
        libusb.load_backend()
