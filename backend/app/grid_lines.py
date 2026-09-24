"""Geometric primitives shared by the vector extraction engines: telling a
**printed grid line** apart from a stroke that is really part of the pattern
(type B/C symbol path, type A backstitch).

Extracted from `app/type_bc.py::_is_grid_ruling` (Lot 5) in Lot 9, when
type A needed the same distinction for its backstitches — the logic is
generalised here rather than duplicated, with two deliberate differences:

* coordinates are passed explicitly (rather than a pdfplumber object),
  because the two callers do not read the same thing: type B/C uses the bbox
  (`x0`/`top`/`x1`/`bottom`), type A the path's real points (`pts`) —
  essential for it, since a bbox loses a diagonal's direction (measured on
  the `cafe-brasserie-charting-export` fixture: 36 of the 56 diagonals on its
  page 1 are descending, and would all be read as ascending from the bbox
  alone);
* `min_length` (optional): a conventional backstitch also starts from a cell
  corner, exactly like a ruling — alignment on a boundary is therefore not
  enough to tell them apart. What really separates them is **length** (a
  ruling crosses the whole grid, a backstitch spans a few cells) and
  **orientation** (a ruling is always strictly horizontal or vertical, never
  diagonal — whereas a backstitch very often is). Without `min_length`, the
  behaviour is identical to Lot 5's, bit for bit.
"""

from __future__ import annotations

import math

# Gap in PDF points below which a side is considered zero (strictly
# horizontal or vertical stroke).
_AXIS_TOLERANCE = 0.5


def line_length(x_a: float, y_a: float, x_b: float, y_b: float) -> float:
    return math.hypot(x_b - x_a, y_b - y_a)


def orientation(x_a: float, y_a: float, x_b: float, y_b: float) -> str | None:
    """`"vertical"`, `"horizontal"`, or `None` for a diagonal as well as for a
    degenerate stroke reduced to a point."""
    dx = abs(x_b - x_a)
    dy = abs(y_b - y_a)
    if dx < _AXIS_TOLERANCE and dy >= _AXIS_TOLERANCE:
        return "vertical"
    if dy < _AXIS_TOLERANCE and dx >= _AXIS_TOLERANCE:
        return "horizontal"
    return None


def is_axis_aligned(x_a: float, y_a: float, x_b: float, y_b: float) -> bool:
    """True for a strictly horizontal or vertical stroke (never for a
    diagonal, nor for a degenerate stroke reduced to a point)."""
    return orientation(x_a, y_a, x_b, y_b) is not None


def boundary_offset(value: float, origin: float, pitch: float) -> float:
    """Normalised distance (0 to 0.5) between `value` and the nearest cell
    boundary of the `origin`/`pitch` lattice."""
    if pitch <= 0:
        return 0.5
    offset = ((value - origin) / pitch) % 1.0
    return min(offset, 1.0 - offset)


def is_grid_ruling(
    x_a: float,
    y_a: float,
    x_b: float,
    y_b: float,
    *,
    origin_x: float,
    origin_top: float,
    pitch_x: float,
    pitch_y: float,
    tol_ratio: float = 0.15,
    min_length: float | None = None,
) -> bool:
    """A grid line (minor or decimal ruling) is **axis-aligned**, lies
    **exactly on a cell boundary** and, when `min_length` is given, is long
    enough to cross the grid.

    Never applied to curves: no exporter draws a rectilinear grid other than
    with line segments.
    """
    axis = orientation(x_a, y_a, x_b, y_b)
    if axis is None:
        return False
    if min_length is not None and line_length(x_a, y_a, x_b, y_b) < min_length:
        return False
    if axis == "vertical":
        return boundary_offset(x_a, origin_x, pitch_x) < tol_ratio
    return boundary_offset(y_a, origin_top, pitch_y) < tol_ratio
