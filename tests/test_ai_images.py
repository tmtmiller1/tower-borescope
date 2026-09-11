"""Tests for tower_borescope.ai.images: model image encoding and base64 text."""

from __future__ import annotations

import base64

import numpy as np

from synthetic import SCENE_HEIGHT, SCENE_WIDTH, inspection_scene, textured_frame
from tower_borescope.ai.base import HOSTED_IMAGE_WIDTH, LOCAL_IMAGE_WIDTH
from tower_borescope.ai.images import encode_for_model, to_base64
from tower_borescope.jpeg import jpeg_size


def test_wide_frame_is_downscaled_keeping_aspect():
    data = encode_for_model(textured_frame(1280, 720), LOCAL_IMAGE_WIDTH)
    assert data.startswith(b"\xff\xd8")
    assert jpeg_size(data) == (768, 432)


def test_narrow_frame_is_not_upscaled():
    data = encode_for_model(textured_frame(320, 240), LOCAL_IMAGE_WIDTH)
    assert jpeg_size(data) == (320, 240)


def test_local_backends_get_a_smaller_image():
    frame = textured_frame()
    hosted = encode_for_model(frame, HOSTED_IMAGE_WIDTH)
    assert len(encode_for_model(frame, LOCAL_IMAGE_WIDTH)) < len(hosted) < 400_000


def test_inspection_scene_is_a_deterministic_corroded_pipe():
    scene = inspection_scene()
    assert scene.shape == (SCENE_HEIGHT, SCENE_WIDTH, 3) and scene.dtype == np.uint8
    assert np.array_equal(scene, inspection_scene())
    blue, green, red = (scene[:, :, channel].astype(np.int16) for channel in range(3))
    rust_fraction = np.mean((red > green + 40) & (green > blue))
    assert 0.03 < rust_fraction < 0.4
    assert scene[:40, :40].mean() < 20 and scene[200:280].mean() > 80
    middle = scene[190:315, 160:480]
    assert np.count_nonzero(middle.max(axis=2) < 50) > 100


def test_inspection_scene_scales_for_local_models():
    data = encode_for_model(inspection_scene(1280, 720), LOCAL_IMAGE_WIDTH)
    assert jpeg_size(data) == (768, 432)


def test_base64_round_trip():
    data = b"\xff\xd8\x00binary\xff"
    text = to_base64(data)
    assert isinstance(text, str)
    assert base64.standard_b64decode(text) == data
