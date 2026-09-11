"""Tests for tower_borescope.remote.qr: QR module grids."""

from __future__ import annotations

from tower_borescope.remote.qr import QR_BORDER, qr_matrix

ADDRESS = "http://192.168.1.20:8765/?key=Q2x8mVn4Rt7Kp1Ws9Yb3Hd6J"
LONGEST_ADDRESS = "http://192.168.100.200:65535/?key=Q2x8mVn4Rt7Kp1Ws9Yb3Hd6J"
VERSION_4_MODULES = 33


def test_matrix_is_square_boolean_grid():
    matrix = qr_matrix(ADDRESS)
    assert matrix
    assert all(len(row) == len(matrix) for row in matrix)
    cells = [cell for row in matrix for cell in row]
    assert all(isinstance(cell, bool) for cell in cells)
    assert any(cells)
    assert not all(cells)


def test_matrix_has_one_module_border():
    matrix = qr_matrix(ADDRESS)
    assert not any(matrix[0])
    assert not any(matrix[-1])
    assert not any(row[0] for row in matrix)
    assert matrix[1][1]


def test_keyed_address_fits_a_version_4_code():
    assert len(qr_matrix(LONGEST_ADDRESS)) <= VERSION_4_MODULES + 2 * QR_BORDER


def test_longer_text_needs_a_larger_grid():
    assert len(qr_matrix(ADDRESS * 8)) > len(qr_matrix(ADDRESS))
