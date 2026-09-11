"""Tests for tower_borescope.image_types."""

from __future__ import annotations

import typing

import numpy as np

from tower_borescope import image_types


def _dtype_of(alias: typing.Any) -> typing.Any:
    """Scalar type inside ``NDArray[...]``, across numpy's alias representations."""
    last_argument = typing.get_args(alias.__value__)[-1]
    inner = typing.get_args(last_argument)
    return inner[0] if inner else last_argument


def test_aliases_name_numpy_array_types():
    assert _dtype_of(image_types.BgrImage) is np.uint8
    assert _dtype_of(image_types.GrayImage) is np.uint8
    assert _dtype_of(image_types.FloatImage) is np.float32
