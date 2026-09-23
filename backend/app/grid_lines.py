"""Primitives géométriques partagées par les moteurs d'extraction
vectoriels : distinguer un trait de **quadrillage imprimé** d'un trait qui
fait réellement partie du motif (tracé de symbole type B/C, point arrière
type A).

Extrait de `app/type_bc.py::_is_grid_ruling` (Lot 5) au Lot 9, quand le
type A a eu besoin de la même distinction pour ses points arrière — la
logique est généralisée ici plutôt que dupliquée, avec deux différences
assumées :

* les coordonnées sont passées explicitement (et non un objet pdfplumber),
  parce que les deux appelants ne lisent pas la même chose : le type B/C
  utilise la bbox (`x0`/`top`/`x1`/`bottom`), le type A les vrais points du
  tracé (`pts`) — indispensable pour lui, car une bbox perd le sens d'une
  diagonale (mesuré sur la fixture `cafe-brasserie-charting-export` : 36
  des 56 diagonales de sa page 1 sont descendantes, et seraient toutes lues
  comme montantes depuis la bbox seule) ;
* `min_length` (facultatif) : un point arrière conventionnel part lui aussi
  d'un coin de case, exactement comme une réglure — l'alignement sur une
  frontière ne suffit donc pas à les séparer. Ce qui les sépare vraiment,
  c'est la **longueur** (une réglure traverse toute la grille, un point
  arrière fait quelques cases) et l'**orientation** (une réglure est
  toujours strictement horizontale ou verticale, jamais diagonale — alors
  qu'un point arrière l'est très souvent). Sans `min_length`, le
  comportement est identique à celui du Lot 5, bit pour bit.
"""

from __future__ import annotations

import math

# Écart en points PDF en dessous duquel un côté est considéré comme nul
# (trait strictement horizontal ou vertical).
_AXIS_TOLERANCE = 0.5


def line_length(x_a: float, y_a: float, x_b: float, y_b: float) -> float:
    return math.hypot(x_b - x_a, y_b - y_a)


def orientation(x_a: float, y_a: float, x_b: float, y_b: float) -> str | None:
    """`"vertical"`, `"horizontal"`, ou `None` pour une diagonale comme pour
    un trait dégénéré réduit à un point."""
    dx = abs(x_b - x_a)
    dy = abs(y_b - y_a)
    if dx < _AXIS_TOLERANCE and dy >= _AXIS_TOLERANCE:
        return "vertical"
    if dy < _AXIS_TOLERANCE and dx >= _AXIS_TOLERANCE:
        return "horizontal"
    return None


def is_axis_aligned(x_a: float, y_a: float, x_b: float, y_b: float) -> bool:
    """Vrai pour un trait strictement horizontal ou vertical (jamais pour
    une diagonale, ni pour un trait dégénéré réduit à un point)."""
    return orientation(x_a, y_a, x_b, y_b) is not None


def boundary_offset(value: float, origin: float, pitch: float) -> float:
    """Distance normalisée (0 à 0.5) entre `value` et la frontière de case
    la plus proche du réseau `origin`/`pitch`."""
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
    """Un trait du quadrillage (réglure mineure ou décimale) est **aligné
    sur les axes**, posé **exactement sur une frontière de case** et, quand
    `min_length` est fourni, assez long pour traverser la grille.

    Jamais appliqué aux courbes : aucun exporteur ne trace un quadrillage
    rectiligne autrement qu'avec des segments.
    """
    axis = orientation(x_a, y_a, x_b, y_b)
    if axis is None:
        return False
    if min_length is not None and line_length(x_a, y_a, x_b, y_b) < min_length:
        return False
    if axis == "vertical":
        return boundary_offset(x_a, origin_x, pitch_x) < tol_ratio
    return boundary_offset(y_a, origin_top, pitch_y) < tol_ratio
