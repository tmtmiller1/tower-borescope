"""Tests for tower_borescope.errors."""

from __future__ import annotations

import pytest

from tower_borescope.errors import BorescopeError, CameraDisconnectedError


def test_camera_disconnected_is_reported_as_a_borescope_error():
    with pytest.raises(BorescopeError, match="unplugged"):
        raise CameraDisconnectedError("scope unplugged")
