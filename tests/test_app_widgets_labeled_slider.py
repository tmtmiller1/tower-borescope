"""Tests for tower_borescope.app.widgets.labeled_slider: value scaling, silent updates
and double-click reset."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tower_borescope.app.widgets.labeled_slider import LabeledSlider, SliderSpec


def percent(value):
    return f"{value:.0f}%"


@pytest.fixture
def changes():
    return []


@pytest.fixture
def slider(qapp, changes):
    spec = SliderSpec("Glare reduction", 0, 100, percent)
    return LabeledSlider(spec, 25, on_change=changes.append)


def test_builds_with_title_value_and_unfocusable_slider(slider):
    assert slider.title.text() == "Glare reduction"
    assert slider.value() == 25
    assert slider.value_label.text() == "25%"
    assert slider.slider.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert slider.value_label.objectName() == "muted"


def test_set_value_notifies_unless_silent(slider, changes):
    slider.set_value(60)
    assert changes == [60]
    slider.set_value(10, silent=True)
    assert changes == [60]
    assert slider.value_label.text() == "10%"


def test_scale_converts_positions_to_values(qapp):
    spec = SliderSpec(
        "Zoom (view only)", 100, 800, lambda v: f"{v / 100:.1f}x", scale=1.0
    )
    zoom = LabeledSlider(spec, 250)
    assert zoom.value_label.text() == "2.5x"
    half = LabeledSlider(SliderSpec("Half", 0, 10, str, scale=0.5), 2.0)
    assert half.slider.value() == 4
    assert half.value() == 2.0


def test_values_clamp_to_the_range(slider):
    slider.set_value(500)
    assert slider.value() == 100


def test_double_click_restores_the_default(slider, changes):
    assert LabeledSlider.mouseDoubleClickEvent is LabeledSlider._mouse_double_click_event
    slider.set_value(80)
    QTest.mouseDClick(slider, Qt.MouseButton.LeftButton)
    assert slider.value() == 25
    assert changes[-1] == 25
