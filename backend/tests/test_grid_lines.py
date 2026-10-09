"""Tests for `app/grid_lines.py` — the grid ruling / pattern stroke
distinction, shared by the type A engine (backstitches, Lot 9) and the
type B/C engine (symbol paths, Lot 5).

The trap these tests lock down: a conventional backstitch starts from a
**cell corner**, exactly like a ruling. Alignment on a boundary is therefore
never enough to tell them apart — length and orientation are needed too.
"""

from __future__ import annotations

from app.grid_lines import boundary_offset, is_axis_aligned, is_grid_ruling, line_length

# A grid with origin (10, 20) and an 8-point pitch.
GEOMETRY = {"origin_x": 10.0, "origin_top": 20.0, "pitch_x": 8.0, "pitch_y": 8.0}


def test_full_height_ruling_on_a_boundary_is_a_ruling() -> None:
    assert is_grid_ruling(18.0, 20.0, 18.0, 420.0, **GEOMETRY, min_length=100.0)


def test_short_backstitch_on_the_same_boundary_is_not_a_ruling() -> None:
    """Same x coordinate, same perfect alignment on the cell boundary: only
    length tells them apart."""
    assert not is_grid_ruling(18.0, 20.0, 18.0, 44.0, **GEOMETRY, min_length=100.0)


def test_diagonal_backstitch_is_never_a_ruling() -> None:
    """A ruling is always strictly horizontal or vertical — a diagonal, even
    a long one starting from a cell corner, never is."""
    assert not is_grid_ruling(18.0, 20.0, 418.0, 420.0, **GEOMETRY, min_length=100.0)


def test_stroke_inside_a_cell_is_not_a_ruling() -> None:
    assert not is_grid_ruling(22.0, 20.0, 22.0, 420.0, **GEOMETRY, min_length=100.0)


def test_without_min_length_behaviour_is_the_lot_5_one() -> None:
    """Without a length criterion (type B/C call), any axis-aligned stroke
    lying on a boundary remains a ruling, however short — this is the
    original behaviour, which the generalisation must not change."""
    assert is_grid_ruling(18.0, 20.0, 18.0, 24.0, **GEOMETRY)


def test_degenerate_point_is_not_a_ruling() -> None:
    assert not is_grid_ruling(18.0, 20.0, 18.1, 20.1, **GEOMETRY)


def test_axis_alignment_and_length_helpers() -> None:
    assert is_axis_aligned(0.0, 0.0, 0.0, 10.0)
    assert is_axis_aligned(0.0, 0.0, 10.0, 0.0)
    assert not is_axis_aligned(0.0, 0.0, 10.0, 10.0)
    assert not is_axis_aligned(0.0, 0.0, 0.1, 0.1)
    assert line_length(0.0, 0.0, 3.0, 4.0) == 5.0


def test_boundary_offset_is_symmetric_around_a_boundary() -> None:
    assert boundary_offset(10.0, 10.0, 8.0) == 0.0
    assert boundary_offset(18.0, 10.0, 8.0) == 0.0
    assert boundary_offset(14.0, 10.0, 8.0) == 0.5
    assert boundary_offset(9.2, 10.0, 8.0) == boundary_offset(10.8, 10.0, 8.0)
