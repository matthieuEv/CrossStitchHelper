"""Tests de `app/grid_lines.py` — la distinction réglure / trait de motif,
partagée par les moteurs type A (points arrière, Lot 9) et type B/C
(tracés de symbole, Lot 5).

Le piège que ces tests verrouillent : un point arrière conventionnel part
d'un **coin de case**, exactement comme une réglure. L'alignement sur une
frontière ne suffit donc jamais à les séparer — il faut aussi la longueur et
l'orientation.
"""

from __future__ import annotations

from app.grid_lines import boundary_offset, is_axis_aligned, is_grid_ruling, line_length

# Une grille d'origine (10, 20) au pas de 8 points.
GEOMETRY = {"origin_x": 10.0, "origin_top": 20.0, "pitch_x": 8.0, "pitch_y": 8.0}


def test_full_height_ruling_on_a_boundary_is_a_ruling() -> None:
    assert is_grid_ruling(18.0, 20.0, 18.0, 420.0, **GEOMETRY, min_length=100.0)


def test_short_backstitch_on_the_same_boundary_is_not_a_ruling() -> None:
    """Même abscisse, même alignement parfait sur la frontière de case : seule
    la longueur les sépare."""
    assert not is_grid_ruling(18.0, 20.0, 18.0, 44.0, **GEOMETRY, min_length=100.0)


def test_diagonal_backstitch_is_never_a_ruling() -> None:
    """Une réglure est toujours strictement horizontale ou verticale — une
    diagonale, même longue et partant d'un coin de case, ne l'est jamais."""
    assert not is_grid_ruling(18.0, 20.0, 418.0, 420.0, **GEOMETRY, min_length=100.0)


def test_stroke_inside_a_cell_is_not_a_ruling() -> None:
    assert not is_grid_ruling(22.0, 20.0, 22.0, 420.0, **GEOMETRY, min_length=100.0)


def test_without_min_length_behaviour_is_the_lot_5_one() -> None:
    """Sans critère de longueur (appel type B/C), tout trait axe-aligné posé
    sur une frontière reste une réglure, aussi court soit-il — c'est le
    comportement d'origine, que la généralisation ne doit pas changer."""
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
