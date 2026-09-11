"""Tests for tower_borescope.imaging.denoise: noise reduction, motion and timing."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import numpy as np

from synthetic import shifted, textured_frame
from tower_borescope.imaging.denoise import TemporalDenoise


def _noisy(base, rng):
    noise = rng.normal(0, 8, base.shape)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_temporal_denoise_reduces_noise_and_follows_motion():
    base = textured_frame()
    rng = np.random.default_rng(2)
    denoiser = TemporalDenoise(0.8)
    noisy = [_noisy(base, rng) for _ in range(20)]
    for frame in noisy:
        output = denoiser.apply(frame)
    error_in = np.abs(noisy[-1].astype(np.int16) - base).mean()
    error_out = np.abs(output.astype(np.int16) - base).mean()
    assert error_out < error_in * 0.6
    moved = shifted(base, 80.0, 0.0)
    lag = np.abs(denoiser.apply(moved).astype(np.int16) - moved).mean()
    assert lag < error_in * 2


def test_first_frame_passes_through_and_reset_restarts():
    frame = textured_frame(160, 120)
    denoiser = TemporalDenoise()
    assert denoiser.strength == 0.7
    assert denoiser.apply(frame) is frame
    assert denoiser.apply(frame).shape == frame.shape
    denoiser.reset()
    assert denoiser.apply(frame) is frame


def test_temporal_denoise_fits_the_frame_budget():
    base = textured_frame()
    rng = np.random.default_rng(3)
    frames = [_noisy(base, rng) for _ in range(6)]
    denoiser = TemporalDenoise()
    denoiser.apply(frames[0])
    samples = []
    for frame in frames * 3:
        start = perf_counter()
        denoiser.apply(frame)
        samples.append((perf_counter() - start) * 1000)
    assert median(samples) < 50
