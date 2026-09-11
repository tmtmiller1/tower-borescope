"""Tests for tower_borescope.remote.qr: QR module grids."""

from __future__ import annotations

from tower_borescope.remote.qr import qr_matrix

ADDRESS = "http://192.168.1.20:8765/"


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


def test_longer_text_needs_a_larger_grid():
    assert len(qr_matrix(ADDRESS * 8)) > len(qr_matrix(ADDRESS))
