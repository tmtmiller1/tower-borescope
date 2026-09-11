"""QR codes for the phone monitor address."""

from __future__ import annotations

from typing import cast

import qrcode
import qrcode.constants

QR_BORDER = 1


def qr_matrix(text: str) -> list[list[bool]]:
    """Encode text as a QR code module grid.

    The code uses medium error correction, the smallest version that fits, and a
    one-module quiet border.

    Args:
        text: Content to encode, typically the server address.

    Returns:
        Square grid of rows; True marks a dark module.
    """
    code = qrcode.QRCode(
        border=QR_BORDER, error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    code.add_data(text)
    code.make(fit=True)
    # qrcode ships no type information; get_matrix returns rows of booleans.
    matrix = cast(list[list[bool]], code.get_matrix())
    return [[bool(cell) for cell in row] for row in matrix]
