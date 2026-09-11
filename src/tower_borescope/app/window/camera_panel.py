"""Camera group above the tabs: resolution choice and the stream statistics line."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

from tower_borescope.app.widgets.layout import group, small_label
from tower_borescope.device.constants import MODES

RES_LABELS: Final = {name: mode.label for name, mode in MODES.items()}
CONNECTING_TEXT: Final = "Connecting..."


class CameraPanel:
    """Resolution combo box and statistics label in the CAMERA group.

    Attributes:
        res_combo: Resolution choice; item data holds the mode name.
        stats_label: Frame size, frame rate and dropped frames, or the reader status.
        box: The CAMERA group box.
    """

    def __init__(self, on_resolution: Callable[[str], None], mode: str) -> None:
        self._on_resolution = on_resolution
        self.res_combo = QComboBox()
        self.res_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, label in RES_LABELS.items():
            self.res_combo.addItem(label, key)
        self.show_mode(mode)
        self.res_combo.currentIndexChanged.connect(self._chosen)
        self.stats_label = small_label(CONNECTING_TEXT, wrap=False)
        self.box = group("CAMERA", self.res_combo, self.stats_label)

    def _chosen(self, index: int) -> None:
        """Report the chosen resolution."""
        self._on_resolution(str(self.res_combo.itemData(index)))

    def show_mode(self, mode: str) -> None:
        """Select ``mode`` in the combo box without reporting a choice."""
        self.res_combo.blockSignals(True)
        self.res_combo.setCurrentIndex(list(RES_LABELS).index(mode))
        self.res_combo.blockSignals(False)
