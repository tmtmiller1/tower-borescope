"""Layout helpers for the sidebar: group boxes, rows, columns, buttons and checkboxes.

Every button and checkbox refuses keyboard focus. A focused push button would take
Space for itself (clicking Analyze again, for example) and a focused checkbox would
toggle, so Space would never reach the freeze shortcut.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

SPACING: Final = 6
SMALL_LABEL: Final = "small"
MUTED_LABEL: Final = "muted"

type Slot = Callable[..., object]


def group(title: str, *widgets: QWidget) -> QGroupBox:
    """A titled group box stacking ``widgets`` vertically.

    Args:
        title: Group title, shown in capitals by convention.
        *widgets: Contents from top to bottom.

    Returns:
        The group box.
    """
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setSpacing(SPACING)
    for widget in widgets:
        layout.addWidget(widget)
    return box


def row(*widgets: QWidget) -> QWidget:
    """A borderless container laying ``widgets`` out left to right."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACING)
    for widget in widgets:
        layout.addWidget(widget)
    return container


def column(*widgets: QWidget) -> QWidget:
    """A borderless container stacking ``widgets`` with stretch below them."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACING)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return container


def scrolled(widget: QWidget) -> QScrollArea:
    """A vertical scroll area around ``widget`` that never scrolls sideways."""
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return area


def checkbox(text: str, checked: bool, slot: Slot, tip: str | None = None) -> QCheckBox:
    """A checkbox that refuses keyboard focus.

    Args:
        text: Label.
        checked: Initial state, set before ``slot`` is connected.
        slot: Called with the new state on every toggle.
        tip: Tooltip, or None.

    Returns:
        The checkbox.
    """
    box = QCheckBox(text)
    box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    box.setChecked(checked)
    box.toggled.connect(slot)
    if tip:
        box.setToolTip(tip)
    return box


def button(
    text: str,
    slot: Slot,
    tip: str | None = None,
    checkable: bool = False,
    name: str | None = None,
) -> QPushButton:
    """A push button that refuses keyboard focus.

    Args:
        text: Label.
        slot: Called on every click.
        tip: Tooltip, or None.
        checkable: Whether the button toggles.
        name: Object name for the style sheet (``"primary"`` or ``"record"``), or None.

    Returns:
        The button.
    """
    push = QPushButton(text)
    push.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    push.clicked.connect(slot)
    push.setCheckable(checkable)
    if tip:
        push.setToolTip(tip)
    if name:
        push.setObjectName(name)
    return push


def small_label(text: str = "", wrap: bool = True) -> QLabel:
    """A small grey label for hints and status lines.

    Args:
        text: Initial text.
        wrap: Whether long text wraps.

    Returns:
        The label.
    """
    label = QLabel(text)
    label.setObjectName(SMALL_LABEL)
    label.setWordWrap(wrap)
    return label
