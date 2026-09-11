"""Dialog showing the phone monitor address as a QR code."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QDialog, QWidget

from tower_borescope.app.style import BACKGROUND, MUTED_TEXT, QR_DARK, QR_LIGHT, TEXT
from tower_borescope.remote.qr import qr_matrix

TITLE: Final = "Phone monitor"
WIDTH: Final = 360
HEIGHT: Final = 440
CODE_ORIGIN: Final = 30.0
CODE_SIZE: Final = 300.0
QUIET_ZONE: Final = 8.0
CELL_OVERLAP: Final = 0.5
URL_TOP: Final = 345.0
URL_HEIGHT: Final = 30.0
URL_FONT_SIZE: Final = 14
HINT_RECT: Final = (20.0, 380.0, 320.0, 50.0)
HINT_FONT_SIZE: Final = 11
HINT: Final = (
    "Scan with the phone's camera, or type the address in a browser on the same Wi-Fi."
)


class QrDialog(QDialog):
    """Fixed-size dialog painting a QR code, the address and a short instruction.

    Attributes:
        url: Address encoded in the code.
        matrix: QR modules, True for dark.
    """

    def __init__(self, url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.url = url
        self.matrix = qr_matrix(url)
        self.setFixedSize(WIDTH, HEIGHT)

    def _paint_code(self, painter: QPainter) -> None:
        """Draw the light quiet zone and the dark modules."""
        quiet = QRectF(
            CODE_ORIGIN - QUIET_ZONE,
            CODE_ORIGIN - QUIET_ZONE,
            CODE_SIZE + 2 * QUIET_ZONE,
            CODE_SIZE + 2 * QUIET_ZONE,
        )
        painter.fillRect(quiet, QColor(QR_LIGHT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(QR_DARK))
        cell = CODE_SIZE / max(len(self.matrix), 1)
        for y, modules in enumerate(self.matrix):
            for x, dark in enumerate(modules):
                if dark:
                    painter.drawRect(
                        QRectF(
                            CODE_ORIGIN + x * cell,
                            CODE_ORIGIN + y * cell,
                            cell + CELL_OVERLAP,
                            cell + CELL_OVERLAP,
                        )
                    )

    def _paint_text(self, painter: QPainter) -> None:
        """Draw the address and the scanning hint below the code."""
        family = self.font().family()
        painter.setPen(QColor(TEXT))
        painter.setFont(QFont(family, URL_FONT_SIZE, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(0.0, URL_TOP, float(WIDTH), URL_HEIGHT),
            Qt.AlignmentFlag.AlignCenter,
            self.url,
        )
        painter.setPen(QColor(MUTED_TEXT))
        painter.setFont(QFont(family, HINT_FONT_SIZE))
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        painter.drawText(QRectF(*HINT_RECT), int(flags.value), HINT)

    def _paint_event(self, _event: QPaintEvent) -> None:
        """Paint the dialog background, code and text."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(BACKGROUND))
        self._paint_code(painter)
        self._paint_text(painter)
        painter.end()

    paintEvent = _paint_event
