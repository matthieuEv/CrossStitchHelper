"""Détection automatique du type A (export logiciel de charting, cahier des
charges §4.3, §4.4 et §8.1-8.3).

Un PDF type A embarque une police de symboles personnalisée où **un glyphe =
un symbole = une couleur**, plus une légende texte qui fait autorité sur le
code DMC et le nom de couleur (§8.5 : le texte de la légende n'est jamais
remplacé par un rapprochement colorimétrique quand il est disponible).

Rien ici n'est codé en dur pour la fixture `cafe-brasserie-charting-export` :
la police de symboles est repérée par sa régularité géométrique (beaucoup de
glyphes d'une même police qui pavent une grille régulière, distincte de
toutes les autres polices de la page), pas par son nom de sous-ensemble PDF
(`AAAAAC+CROSSSTICH6` ici, arbitraire d'un export à l'autre). Un exporteur
type A différent, avec un autre nom de police et une autre mise en page de
légende, devrait toujours produire un résultat exploitable — éventuellement
avec une confiance plus basse et des avertissements, jamais un résultat
silencieusement faux (règle impérative du `pdf-extraction-specialist`).

Module pur : aucune dépendance FastAPI/SQLAlchemy. Le point d'entrée
`detect_type_a` ne lève jamais d'exception pour un PDF qui ne ressemble pas
à un export type A — il renvoie `None`, laissant la suite du pipeline
d'import (types B/C/D/E, Lots 5 à 7) ou le repli manuel (Lot 2) prendre le
relais.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
from pdfplumber.page import Page

from app.dmc_catalog import nearest_dmc_among
from app.dmc_colors import FALLBACK_HEX, dmc_hex
from app.grid_lines import is_grid_ruling, line_length

# `app.schemas` ne dépend que de Pydantic — l'importer ici ne rompt pas la
# pureté du module (aucune dépendance FastAPI/SQLAlchemy, voir docstring).
from app.schemas import BackstitchSegment, DetectionWarning, FrenchKnot

# pdfplumber représente chaque caractère/rectangle positionné comme un
# dictionnaire hétérogène (`T_obj = Dict[str, Any]` côté bibliothèque) — pas
# de TypedDict public à réutiliser ici.
Char = dict[str, Any]

# Couleur normalisée d'un petit rectangle de fond (RVB ou niveau de gris
# étendu en triplet, arrondi) — `None` quand aucun rectangle n'a pu être
# associé au glyphe. Voir `_rect_color_under_char` pour le détail : ce
# fichier de référence dessine, sous chaque glyphe de symbole, un petit
# rectangle rempli de la couleur DMC réelle (à la fois sur la légende et sur
# les pages de grille) — un même glyphe est parfois réutilisé pour deux
# couleurs différentes (observé : le glyphe du point plein DMC 640 est aussi
# celui du demi-point DMC 3756 dans ce fichier), alors que la couleur de
# fond, elle, reste fiable. La clé de rapprochement grille <-> légende est
# donc le couple (glyphe, couleur de fond), jamais le glyphe seul.
Color = tuple[float, ...]
CellKey = tuple[str, Color | None]

# Nombre minimal de glyphes d'une police pour envisager qu'elle pave une
# grille régulière de symboles (en dessous, ce n'est probablement que du
# texte courant ou une légende clairsemée).
_MIN_GRID_CHARS = 30
# Nombre minimal de colonnes/lignes distinctes occupées pour parler de
# « grille » plutôt que d'un simple alignement de quelques caractères.
_MIN_GRID_SPAN = 5
# Densité minimale de remplissage (glyphes observés / cases du quadrillage
# couvert) en dessous de laquelle le pavage est jugé trop clairsemé pour
# être une grille de points de croix plutôt qu'un texte de paragraphe (qui,
# à faible tolérance, peut sembler « tiler » avec un pas assez régulier lui
# aussi — mais toujours en remplissant beaucoup moins de son rectangle
# englobant : ~0.05-0.2 observé sur du texte courant contre ~0.9-1.0 sur une
# vraie grille de symboles, qui remplit quasiment toutes les combinaisons
# colonne/ligne de son pavage).
_MIN_GRID_DENSITY = 0.4

_DECLARED_DIMENSIONS_RE = re.compile(r"(\d+)\s*w\s*[Xx]\s*(\d+)\s*h\s*Stitches")
_FABRIC_COUNT_RE = re.compile(r"Fabric:[^\n,]*?(\d+)")
_SECTION_HEADER_RE = re.compile(r"^Floss Used for (.+?)\s*:")
_SECTION_HEADER_PREFIX = "Floss Used for "
_LEGEND_ROW_RE = re.compile(r"^(\S)\s*\d+\s*DMC\s+([A-Za-z0-9]+)\s+(.+)$")
# Les sections « Back Stitches » et « French Knots » n'ont pas de glyphe de
# symbole : leur colonne « Symbol » est un **échantillon vectoriel** (un
# trait, un point) tracé dans la couleur exacte utilisée sur les pages de
# grille — mesuré sur `cafe-brasserie-charting-export`, page 10. Leurs
# lignes de texte commencent donc directement par le nombre de brins.
_SAMPLE_LEGEND_ROW_RE = re.compile(r"^\d+\s+DMC\s+([A-Za-z0-9]+)\s+(.+)$")

# Catégories de points, dans l'ordre où l'exporteur les imprime. Les clés
# sont les intitulés de section normalisés (minuscules, espaces compactés) :
# un exporteur qui écrirait « Backstitch » plutôt que « Back Stitches » est
# reconnu de la même façon, et un intitulé inconnu est simplement ignoré
# (jamais une exception, jamais une section rangée au hasard).
FULL = "full"
HALF = "half"
QUARTER = "quarter"
BACKSTITCH = "backstitch"
FRENCH_KNOT = "french_knot"

_SECTION_ALIASES: dict[str, str] = {
    "full stitches": FULL,
    "full stitch": FULL,
    "half stitches": HALF,
    "half stitch": HALF,
    "quarter stitches": QUARTER,
    "quarter stitch": QUARTER,
    "back stitches": BACKSTITCH,
    "back stitch": BACKSTITCH,
    "backstitches": BACKSTITCH,
    "backstitch": BACKSTITCH,
    "french knots": FRENCH_KNOT,
    "french knot": FRENCH_KNOT,
}

# Catégories dont les lignes de légende portent un échantillon vectoriel
# plutôt qu'un glyphe de police.
_SAMPLE_SECTIONS = frozenset({BACKSTITCH, FRENCH_KNOT})

# Tolérance, en fraction de case, pour considérer qu'une extrémité de tracé
# tombe sur le réseau demi-case (coin de case ou milieu de case). Mesuré sur
# la fixture de référence : 5 172 extrémités sur 5 172 tombent à moins de
# 0.02 case d'un multiple de 0.5 — la tolérance ci-dessous est donc large
# sans être permissive.
_SNAP_TOLERANCE = 0.08

# Fraction de l'emprise de la grille de la page qu'un trait axe-aligné doit
# couvrir pour être une réglure plutôt qu'un point arrière. Une réglure
# traverse la grille de bord à bord ; un point arrière, même long et
# parfaitement droit le long d'une frontière de case, reste local.
# Volontairement exigeant : une première version filtrait à 12 cases et
# supprimait de vrais points arrière rectilignes de la fixture de référence
# (mesuré : -13 % sur DMC 310, -24 % sur DMC 938 par rapport aux longueurs
# annoncées par la légende).
_RULING_MIN_SPAN_RATIO = 0.8

# Taille maximale (en cases) de la petite forme pleine d'un nœud. Mesuré :
# les nœuds de la fixture font 0.885 case, les flèches de repère de page
# (marges, hors motif) exactement 1.0 case — ce seuil les sépare, en plus du
# filtre de couleur qui reste le signal principal.
_KNOT_MAX_CELLS = 0.95

# Distance Lab au-delà de laquelle un rapprochement de couleur de repli
# (aucun échantillon vectoriel dans la légende) est jugé trop douteux pour
# rattacher un tracé à un code DMC déclaré.
_FALLBACK_MAX_LAB_DISTANCE = 30.0

# Au-delà de ce nombre de tracés, une page n'est pas une page de légende :
# voir `_sample_colors_for_row`.
_MAX_LEGEND_PAGE_OBJECTS = 500


@dataclass
class SymbolGlyphLocation:
    """Position d'une occurrence du glyphe de symbole sur la page PDF
    source — jamais le glyphe lui-même (police privée, illisible hors de ce
    fichier), mais assez pour qu'un appelant en dehors de ce module pur
    (`app/imports_engine.py`, qui a déjà PyMuPDF) en découpe un aperçu
    raster fidèle depuis la page rendue. C'est ça, et non le glyphe brut ou
    une clé synthétique, qui permet de retrouver le vrai symbole tel
    qu'imprimé dans le PDF — quel que soit le fichier, sans dépendre d'une
    liste de symboles connus à l'avance (des symboles différents d'un
    export à l'autre)."""

    page_number: int
    """1-based, comme `pdfplumber.page.Page.page_number`."""

    bbox: tuple[float, float, float, float]
    """`(x0, top, x1, bottom)`, mêmes unités et origine (haut-gauche) que
    les rectangles `pdfplumber`."""


@dataclass
class TypeAPaletteEntry:
    code: str
    """Code DMC tel qu'imprimé dans la légende, p. ex. ``"310"`` ou ``"B5200"``."""

    name: str
    """Nom de la couleur tel qu'imprimé dans la légende."""

    symbol_key: str
    """Clé courte et imprimable pour l'UI — jamais le glyphe brut de la
    police privée du PDF (illisible et non portable hors de ce fichier)."""

    rgb_hex: str
    """Couleur d'affichage approximative — depuis `dmc_hex`, ou
    `FALLBACK_HEX` si le code est absent de la table locale."""

    symbol_glyph: SymbolGlyphLocation | None = None
    """Absente pour un symbole non rapproché d'une ligne de légende (repli
    sur `symbol_key` côté rendu) — voir `SymbolGlyphLocation`."""

    categories: tuple[str, ...] = ()
    """Sections de légende où ce fil apparaît, parmi `FULL`, `HALF`,
    `QUARTER`, `BACKSTITCH`, `FRENCH_KNOT` (Lot 9). Un même fil est souvent
    déclaré dans plusieurs sections (p. ex. DMC 742 en points entiers, en
    points arrière *et* en nœuds sur la fixture de référence) : il reste
    alors **une seule entrée de palette**, jamais une par section — la
    palette est une liste de fils, pas une liste de lignes de légende."""

    count_full: int = 0
    """Cases de `TypeAResult.cells` portant cette entrée (points entiers)."""

    count_half: int = 0
    """Idem pour `TypeAResult.cells_half`."""

    count_quarter: int = 0
    """Idem pour `TypeAResult.cells_quarter`."""

    count_french_knots: int = 0
    """Nœuds de `TypeAResult.french_knots` portant cette entrée."""

    backstitch_length_cells: float = 0.0
    """Longueur cumulée des segments de `TypeAResult.backstitch` de cette
    entrée, **en cases** (unité de grille) et non en centimètres : la
    conversion dépend du compte de toile, exposé séparément par
    `TypeAResult.fabric_count` (longueur en cm = `backstitch_length_cells *
    2.54 / fabric_count`). Aucune longueur physique n'est inventée ici quand
    le compte de toile n'est pas déclaré par le PDF."""


@dataclass
class TypeAResult:
    columns: int
    rows: int
    cells: list[int]
    """Longueur `columns * rows`, ligne par ligne, (0,0) en haut à gauche en
    premier. 0 = case vide, n = index 1-based dans `palette`."""
    palette: list[TypeAPaletteEntry]
    confidence: float
    warnings: list[DetectionWarning] = field(default_factory=list)
    """Jamais un texte déjà composé en français : un code de message et ses
    paramètres, traduits côté client (`import.warning.<code>`, audit des
    traductions du Lot 8)."""

    cells_half: list[int] = field(default_factory=list)
    """Points 1/2, même forme et même espace d'index de palette que `cells`
    (Lot 9). Liste **vide** — et non une grille de zéros — quand le motif
    n'a aucun point 1/2, ce qui correspond à `Grid.layer_half = NULL`."""

    cells_quarter: list[int] = field(default_factory=list)
    """Points 1/4, même convention que `cells_half`."""

    backstitch: list[BackstitchSegment] = field(default_factory=list)
    """Segments de point arrière en coordonnées de **coins de case** de la
    grille assemblée (0-based, (0,0) = coin haut-gauche de la case (0,0)),
    voir `app/schemas.py::BackstitchSegment`. `palette_index` est 1-based,
    comme les valeurs de `cells`."""

    french_knots: list[FrenchKnot] = field(default_factory=list)
    """Nœuds en coordonnées de **centre de case** ((0.5, 0.5) = centre de la
    case (0,0)), voir `app/schemas.py::FrenchKnot`. `palette_index` est
    1-based, comme les valeurs de `cells`."""

    fabric_count: int | None = None
    """Compte de toile déclaré en clair par le PDF (« Fabric: Aida 16 »),
    utile pour convertir `backstitch_length_cells` en centimètres et pour
    pré-remplir `Pattern.fabric_count`. `None` si le PDF ne le déclare pas —
    jamais une valeur par défaut inventée."""


@dataclass
class _GridPage:
    """Une page de grille détectée, avec sa police de symboles locale."""

    index: int
    all_chars: list[Char]
    symbol_chars: list[Char]
    rects: list[Char]
    rect_index: dict[tuple[int, int], list[Char]]
    pitch_x: float
    pitch_y: float


@dataclass
class _LegendRow:
    section: str
    symbol_char: str | None
    """`None` pour une section à échantillon vectoriel (points arrière,
    nœuds) : ces lignes n'ont pas de glyphe de police."""
    code: str
    name: str
    swatch_color: Color | None
    glyph: SymbolGlyphLocation | None
    sample_colors: tuple[Color, ...] = ()
    """Couleurs des tracés d'échantillon imprimés en regard de la ligne
    (voir `_SAMPLE_LEGEND_ROW_RE`) — c'est la clé de rapprochement
    couleur -> code DMC des points arrière et des nœuds, mesurée dans le
    fichier lui-même plutôt que devinée par distance colorimétrique."""


@dataclass(frozen=True)
class _CornerLattice:
    """Réseau des **coins de case** d'une page de grille, en coordonnées
    absolues de la grille assemblée.

    Dérivé des réglures imprimées (qui tombent, elles, exactement sur les
    frontières de case) plutôt que de l'ajustement linéaire sur les numéros
    d'axe (`_fit_axes`), qui est ancré sur le coin haut-gauche des *glyphes*
    et porte donc un décalage systématique de quelques dixièmes de case —
    mesuré à ~0.27 case sur la fixture de référence, soit assez pour arrondir
    une extrémité de point arrière dans la mauvaise case. `_fit_axes` reste
    utilisé, mais seulement pour ancrer le réseau sur la numérotation
    absolue (décalage entier de pages, aucun sous-multiple en jeu)."""

    origin_x: float
    pitch_x: float
    offset_col: int
    origin_top: float
    pitch_y: float
    offset_row: int
    span_x: float
    """Largeur, en points PDF, de la zone de grille de la page — sert à
    reconnaître une réglure à sa longueur (voir `_RULING_MIN_SPAN_RATIO`)."""
    span_y: float

    def col(self, x: float) -> float:
        return (x - self.origin_x) / self.pitch_x + self.offset_col

    def row(self, top: float) -> float:
        return (top - self.origin_top) / self.pitch_y + self.offset_row


def detect_type_a(pdf_path: Path) -> TypeAResult | None:
    """Renvoie `None` (sans jamais lever) si le PDF ne ressemble pas à un
    export type A — voir le module pour le détail de la détection."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        page_font_groups = [_group_by_font(page.chars) for page in pages]

        symbol_font = _pick_symbol_font(page_font_groups)
        if symbol_font is None:
            return None

        grid_pages = _collect_grid_pages(pages, page_font_groups, symbol_font)
        if not grid_pages:
            return None

        warnings: list[DetectionWarning] = []
        confidence = 1.0

        legend_rows = _parse_legend_rows(pages)
        if not any(row.section == FULL for row in legend_rows):
            warnings.append(DetectionWarning(code="type_a.missing_full_stitches_legend"))
            confidence -= 0.5

        legend = _build_palette(legend_rows)
        palette = legend.palette
        if legend.unknown_codes:
            warnings.append(
                DetectionWarning(
                    code="type_a.unknown_dmc_codes",
                    params={
                        "count": len(legend.unknown_codes),
                        "codes": ", ".join(legend.unknown_codes),
                    },
                )
            )
            confidence -= min(0.1, 0.02 * len(legend.unknown_codes))
        if legend.ambiguous_codes:
            warnings.append(
                DetectionWarning(
                    code="type_a.ambiguous_dmc_codes",
                    params={
                        "count": len(legend.ambiguous_codes),
                        "codes": ", ".join(legend.ambiguous_codes),
                    },
                )
            )
            confidence -= min(0.2, 0.05 * len(legend.ambiguous_codes))

        fits = _fit_all_axes(grid_pages, symbol_font)
        lattices = _build_all_lattices(pages, grid_pages, fits)
        placements, offset_placements, page_warnings, page_penalty = _place_grid_pages(
            grid_pages, legend.key_to_target, fits, lattices
        )
        warnings.extend(page_warnings)
        confidence -= page_penalty

        declared = _find_declared_dimensions(pages)
        columns, rows, dims_warning, dims_penalty = _resolve_dimensions(declared, placements)
        if dims_warning is not None:
            warnings.append(dims_warning)
            confidence -= dims_penalty

        if columns <= 0 or rows <= 0:
            return None

        layers = _fill_cells(columns, rows, placements, offset_placements, legend, palette)
        if layers.warning is not None:
            warnings.append(layers.warning)
        warnings.extend(layers.extra_warnings)
        confidence -= layers.penalty

        specials = _collect_special_stitches(pages, lattices, legend, columns, rows)
        warnings.extend(specials.warnings)
        confidence -= specials.penalty

        confidence = max(0.0, min(1.0, confidence))
        result = TypeAResult(
            columns=columns,
            rows=rows,
            cells=layers.full,
            palette=palette,
            confidence=confidence,
            warnings=warnings,
            cells_half=layers.half,
            cells_quarter=layers.quarter,
            backstitch=specials.backstitch,
            french_knots=specials.french_knots,
            fabric_count=_find_fabric_count(pages),
        )
        _count_palette_usage(result)
        result.warnings.extend(_cross_check_sections(legend, result))
        return result


# --------------------------------------------------------------------------
# Détection de la police de symboles (signal principal : pavage régulier)
# --------------------------------------------------------------------------


def _group_by_font(chars: list[Char]) -> dict[str, list[Char]]:
    groups: dict[str, list[Char]] = {}
    for ch in chars:
        groups.setdefault(str(ch["fontname"]), []).append(ch)
    return groups


def _estimate_pitch(distinct_sorted: list[float]) -> float | None:
    """Pas médian entre positions distinctes voisines, en ignorant les
    micro-écarts (< 1pt) causés par l'accumulation de flottants sur des
    glyphes censés être à la même position (observé en pratique : deux
    positions à 0.2-0.3pt d'écart pour une même colonne/ligne réelle)."""
    if len(distinct_sorted) < 2:
        return None
    diffs = [b - a for a, b in zip(distinct_sorted, distinct_sorted[1:], strict=False)]
    plausible = [d for d in diffs if d > 1.0]
    if not plausible:
        return None
    return statistics.median(plausible)


def _is_grid_like(chars: list[Char]) -> tuple[float, float] | None:
    """`(pitch_x, pitch_y)` si `chars` pavent une grille 2D assez régulière,
    sinon `None`. C'est le signal principal pour repérer la police de
    symboles — jamais un nom de police en dur (voir docstring du module)."""
    if len(chars) < _MIN_GRID_CHARS:
        return None
    xs_distinct = sorted({round(float(c["x0"]), 1) for c in chars})
    tops_distinct = sorted({round(float(c["top"]), 1) for c in chars})
    pitch_x = _estimate_pitch(xs_distinct)
    pitch_y = _estimate_pitch(tops_distinct)
    if pitch_x is None or pitch_y is None:
        return None
    # Une grille de points de croix a des cases à peu près carrées ; un bloc
    # de texte de paragraphe a en général un interligne (pitch vertical)
    # bien plus grand que l'avance de caractère (pitch horizontal) — un
    # écart de pas trop marqué entre les deux axes trahit du texte courant,
    # pas une grille de symboles.
    if not (0.4 <= pitch_x / pitch_y <= 2.5):
        return None
    min_x = min(float(c["x0"]) for c in chars)
    min_top = min(float(c["top"]) for c in chars)
    n_cols = len({round((float(c["x0"]) - min_x) / pitch_x) for c in chars})
    n_rows = len({round((float(c["top"]) - min_top) / pitch_y) for c in chars})
    if n_cols < _MIN_GRID_SPAN or n_rows < _MIN_GRID_SPAN:
        return None
    density = len(chars) / (n_cols * n_rows)
    if density < _MIN_GRID_DENSITY:
        return None
    return pitch_x, pitch_y


def _best_grid_font_on_page(font_groups: dict[str, list[Char]]) -> str | None:
    """Police la plus probable pour être la police de symboles sur *cette*
    page : celle qui pave une grille régulière avec le plus de glyphes."""
    best_font: str | None = None
    best_count = -1
    for fontname, chars in font_groups.items():
        if _is_grid_like(chars) is None:
            continue
        if len(chars) > best_count:
            best_count = len(chars)
            best_font = fontname
    return best_font


def _pick_symbol_font(page_font_groups: list[dict[str, list[Char]]]) -> str | None:
    """Police de symboles globale du PDF : celle qui pave une grille
    régulière sur le plus grand nombre de pages (un export type A répète
    la même police de symboles sur toutes ses pages de grille)."""
    candidates: Counter[str] = Counter()
    for font_groups in page_font_groups:
        best = _best_grid_font_on_page(font_groups)
        if best is not None:
            candidates[best] += 1
    if not candidates:
        return None
    return candidates.most_common(1)[0][0]


def _collect_grid_pages(
    pages: list[Page],
    page_font_groups: list[dict[str, list[Char]]],
    symbol_font: str,
) -> list[_GridPage]:
    grid_pages: list[_GridPage] = []
    for index, (page, font_groups) in enumerate(zip(pages, page_font_groups, strict=True)):
        symbol_chars = font_groups.get(symbol_font)
        if not symbol_chars:
            continue
        metrics = _is_grid_like(symbol_chars)
        if metrics is None:
            continue
        pitch_x, pitch_y = metrics
        rects = list(page.rects)
        grid_pages.append(
            _GridPage(
                index=index,
                all_chars=list(page.chars),
                symbol_chars=symbol_chars,
                rects=rects,
                rect_index=_build_rect_index(rects, pitch_x, pitch_y),
                pitch_x=pitch_x,
                pitch_y=pitch_y,
            )
        )
    return grid_pages


# --------------------------------------------------------------------------
# Couleur de fond associée à un glyphe (désambiguïsation glyphe -> couleur)
# --------------------------------------------------------------------------


def _normalize_color(raw: Any) -> Color:
    """`non_stroking_color` de pdfplumber peut être un scalaire (niveau de
    gris), un triplet RVB ou un quadruplet CMJN selon l'espace colorimétrique
    du PDF — toujours ramené à un tuple arrondi comparable."""
    if isinstance(raw, int | float):
        value = round(float(raw), 4)
        return (value, value, value)
    if isinstance(raw, list | tuple):
        return tuple(round(float(v), 4) for v in raw)
    return ()


def _rect_color_under_char(char: Char, rects: list[Char]) -> Color | None:
    """Couleur de remplissage du plus petit rectangle qui recouvre le centre
    du glyphe `char`. Ce fichier de référence dessine un petit carré de la
    couleur DMC réelle sous chaque glyphe (légende comme grille) — c'est un
    signal plus fiable que le glyphe seul quand un même glyphe est réutilisé
    pour deux couleurs différentes (voir docstring de `CellKey`).

    Balayage complet de `rects` — utilisé seulement pour la légende (une
    poignée d'appels). Les pages de grille utilisent `_rect_color_indexed`
    ci-dessous : un balayage complet par glyphe y serait O(glyphes ×
    rectangles), soit plusieurs centaines de millions d'itérations sur la
    fixture de référence (mesuré au profilage — ~80 % du temps total)."""
    cx = (float(char["x0"]) + float(char["x1"])) / 2
    ctop = (float(char["top"]) + float(char["bottom"])) / 2
    best: Char | None = None
    best_area = float("inf")
    for rect in rects:
        if not rect.get("fill"):
            continue
        x0, x1 = float(rect["x0"]), float(rect["x1"])
        top, bottom = float(rect["top"]), float(rect["bottom"])
        if not (x0 <= cx <= x1 and top <= ctop <= bottom):
            continue
        area = (x1 - x0) * (bottom - top)
        if area < best_area:
            best_area = area
            best = rect
    if best is None:
        return None
    return _normalize_color(best["non_stroking_color"])


def _build_rect_index(
    rects: list[Char], pitch_x: float, pitch_y: float
) -> dict[tuple[int, int], list[Char]]:
    """Regroupe les rectangles remplis par case de grille (même pas que les
    glyphes de symboles) : une case ne contient presque toujours qu'un seul
    petit rectangle de couleur, donc ne chercher que dans le bucket d'un
    glyphe (et ses voisins immédiats, pour le bruit d'arrondi de bord)
    remplace un balayage de tous les rectangles de la page par une poignée
    de candidats."""
    index: dict[tuple[int, int], list[Char]] = {}
    for rect in rects:
        if not rect.get("fill"):
            continue
        cx = (float(rect["x0"]) + float(rect["x1"])) / 2
        cy = (float(rect["top"]) + float(rect["bottom"])) / 2
        key = (round(cx / pitch_x), round(cy / pitch_y))
        index.setdefault(key, []).append(rect)
    return index


def _rect_color_indexed(
    char: Char,
    rect_index: dict[tuple[int, int], list[Char]],
    pitch_x: float,
    pitch_y: float,
) -> Color | None:
    """Équivalent de `_rect_color_under_char`, mais via `rect_index`
    (`_build_rect_index`) plutôt qu'un balayage complet — voir cette
    dernière pour le détail du gain de performance."""
    cx = (float(char["x0"]) + float(char["x1"])) / 2
    ctop = (float(char["top"]) + float(char["bottom"])) / 2
    base_key = (round(cx / pitch_x), round(ctop / pitch_y))
    best: Char | None = None
    best_area = float("inf")
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for rect in rect_index.get((base_key[0] + dx, base_key[1] + dy), ()):
                x0, x1 = float(rect["x0"]), float(rect["x1"])
                top, bottom = float(rect["top"]), float(rect["bottom"])
                if not (x0 <= cx <= x1 and top <= ctop <= bottom):
                    continue
                area = (x1 - x0) * (bottom - top)
                if area < best_area:
                    best_area = area
                    best = rect
    if best is None:
        return None
    return _normalize_color(best["non_stroking_color"])


# --------------------------------------------------------------------------
# Légende texte ("Floss Used for Full Stitches")
# --------------------------------------------------------------------------


def _section_of(text: str) -> str | None:
    """Catégorie de points d'un en-tête « Floss Used for ... : », ou `None`
    si la ligne n'est pas un en-tête de section."""
    match = _SECTION_HEADER_RE.match(text)
    if match is None:
        return None
    label = " ".join(match.group(1).split()).lower()
    return _SECTION_ALIASES.get(label, "")


def _sample_colors_for_row(
    page: Page, top: float, bottom: float, text_x0: float
) -> tuple[Color, ...]:
    """Couleurs des tracés d'échantillon imprimés dans la colonne « Symbol »
    d'une ligne de légende sans glyphe : segments (points arrière) et petites
    formes pleines (nœuds) situés à gauche du texte et à sa hauteur.

    Les deux couleurs d'un même échantillon sont conservées : l'exporteur de
    référence trace chaque point arrière deux fois, une passe sombre puis une
    passe plus claire par-dessus (ombre + brillance), exactement comme sur
    les pages de grille — les deux valeurs doivent donc pouvoir rattacher un
    tracé de grille à ce code."""
    colors: list[Color] = []
    middle = (top + bottom) / 2
    height = max(bottom - top, 1.0)
    candidates = [*page.lines, *page.curves]
    if len(candidates) > _MAX_LEGEND_PAGE_OBJECTS:
        # Une page de légende ne porte qu'une poignée de tracés ; au-delà,
        # c'est une page de grille (des milliers d'objets) où ce balayage
        # par ligne coûterait cher pour rien.
        return ()
    for obj in candidates:
        obj_middle = (float(obj["top"]) + float(obj["bottom"])) / 2
        if abs(obj_middle - middle) > height:
            continue
        if float(obj["x1"]) > text_x0:
            continue
        for key in ("stroking_color", "non_stroking_color"):
            color = _normalize_color(obj.get(key))
            if color and color not in colors:
                colors.append(color)
    return tuple(colors)


def _parse_legend_rows(pages: list[Page]) -> list[_LegendRow]:
    """Toutes les lignes de légende du PDF, chacune étiquetée de sa section
    (« Full Stitches », « Half Stitches », ... — voir `_SECTION_ALIASES`).

    Jusqu'au Lot 8 cette lecture s'arrêtait à la fin de la section des points
    entiers ; le Lot 9 a besoin des suivantes (points 1/2, 1/4, arrière,
    nœuds). Une section d'intitulé inconnu interrompt la section en cours
    sans rien ranger dedans par défaut : mieux vaut ignorer des lignes que
    les attribuer à la mauvaise catégorie."""
    rows: list[_LegendRow] = []
    for page in pages:
        rects = page.rects
        section: str | None = None
        for line in page.extract_text_lines():
            text = str(line["text"])
            if text.startswith(_SECTION_HEADER_PREFIX):
                section = _section_of(text) or None
                continue
            if section is None:
                continue
            if text.startswith("Symbol Strands"):
                continue

            if section in _SAMPLE_SECTIONS:
                sample_match = _SAMPLE_LEGEND_ROW_RE.match(text)
                if sample_match is None:
                    continue
                rows.append(
                    _LegendRow(
                        section=section,
                        symbol_char=None,
                        code=sample_match.group(1),
                        name=sample_match.group(2).strip(),
                        swatch_color=None,
                        glyph=None,
                        sample_colors=_sample_colors_for_row(
                            page,
                            float(line["top"]),
                            float(line["bottom"]),
                            float(line["x0"]),
                        ),
                    )
                )
                continue

            match = _LEGEND_ROW_RE.match(text)
            if match is None:
                continue
            row_chars = line.get("chars") or []
            first_char = row_chars[0] if row_chars else None
            swatch_color = _rect_color_under_char(first_char, rects) if first_char else None
            glyph = (
                SymbolGlyphLocation(
                    page_number=page.page_number,
                    bbox=(
                        float(first_char["x0"]),
                        float(first_char["top"]),
                        float(first_char["x1"]),
                        float(first_char["bottom"]),
                    ),
                )
                if first_char is not None
                else None
            )
            rows.append(
                _LegendRow(
                    section=section,
                    symbol_char=match.group(1),
                    code=match.group(2),
                    name=match.group(3).strip(),
                    swatch_color=swatch_color,
                    glyph=glyph,
                )
            )
    return rows


def _symbol_key(index0: int) -> str:
    """Clé courte façon « colonnes de tableur » (A, B, ..., Z, AA, AB, ...)
    — stable, lisible, et jamais le glyphe brut de la police privée."""
    n = index0
    letters = ""
    while True:
        n, rem = divmod(n, 26)
        letters = chr(65 + rem) + letters
        if n == 0:
            return letters
        n -= 1


@dataclass
class _Legend:
    """Tout ce que la légende texte apprend sur les fils du motif."""

    palette: list[TypeAPaletteEntry]
    key_to_target: dict[CellKey, tuple[int, str]]
    """(glyphe, couleur de fond) -> (index 1-based de palette, catégorie) —
    la catégorie décide de la couche où la case est écrite (`cells`,
    `cells_half` ou `cells_quarter`), jamais le seul glyphe."""
    sample_color_to_index: dict[Color, int]
    """Couleur d'un échantillon vectoriel de légende -> index 1-based de
    palette (points arrière et nœuds)."""
    fractional_glyph_to_target: dict[str, tuple[int, str]]
    """Glyphe **seul** -> (index de palette, catégorie), pour les sections
    de points fractionnés. Sert aux glyphes posés dans un coin de case
    plutôt qu'en son centre : la couleur de fond sous un tel glyphe est
    celle du point qui occupe *déjà* la case, pas la sienne — mesuré sur la
    fixture de référence, où les 4 points 1/4 de DMC 3031 sont dessinés
    par-dessus une case de demi-point DMC 3756. La clé habituelle (glyphe,
    couleur de fond) y désignerait donc le mauvais fil."""
    codes_by_section: dict[str, list[int]]
    """Index 1-based de palette déclarés dans chaque section — sert à
    croiser ce qui est *annoncé* avec ce qui est *extrait* (§7.3)."""
    unknown_codes: list[str]
    ambiguous_codes: list[str]


def _build_palette(legend_rows: list[_LegendRow]) -> _Legend:
    """Une entrée de palette **par fil**, dans l'ordre de la légende.

    Les sections autres que « Full Stitches » réutilisent l'entrée déjà
    créée pour le même code DMC quand il y en a une (cas général : un fil
    brodé en points entiers sert aussi au point arrière) — la palette reste
    donc la liste de fils annoncée par le PDF (« Colours: 34 » sur la
    fixture de référence), pas une liste de lignes de légende. Un code
    répété *dans* la section des points entiers reste, lui, deux entrées
    distinctes : ce sont deux symboles différents, avec deux comptages
    différents (DMC 3776 sur la fixture)."""
    palette: list[TypeAPaletteEntry] = []
    key_to_target: dict[CellKey, tuple[int, str]] = {}
    sample_color_to_index: dict[Color, int] = {}
    fractional: dict[str, tuple[int, str]] = {}
    codes_by_section: dict[str, list[int]] = {}
    index_by_code: dict[str, int] = {}
    unknown_codes: list[str] = []
    ambiguous_codes: list[str] = []

    for row in legend_rows:
        index = index_by_code.get(row.code) if row.section != FULL else None
        if index is None:
            hex_value = dmc_hex(row.code)
            if hex_value is None:
                unknown_codes.append(row.code)
                hex_value = FALLBACK_HEX
            index = len(palette) + 1
            palette.append(
                TypeAPaletteEntry(
                    code=row.code,
                    name=row.name,
                    symbol_key=_symbol_key(index - 1),
                    rgb_hex=hex_value,
                    symbol_glyph=row.glyph,
                )
            )
            index_by_code.setdefault(row.code, index)
        entry = palette[index - 1]
        if row.section not in entry.categories:
            entry.categories = (*entry.categories, row.section)
        codes_by_section.setdefault(row.section, []).append(index)

        for color in row.sample_colors:
            sample_color_to_index.setdefault(color, index)

        if row.symbol_char is None:
            continue
        if row.section == QUARTER or (row.section == HALF and row.symbol_char not in fractional):
            fractional[row.symbol_char] = (index, row.section)
        key: CellKey = (row.symbol_char, row.swatch_color)
        if key in key_to_target:
            # Deux lignes de légende partagent le même glyphe ET la même
            # couleur de fond : on ne peut structurellement pas distinguer
            # leurs cases dans la grille — on garde la première association
            # (comportement conservateur) et on le signale clairement plutôt
            # que d'écraser silencieusement.
            ambiguous_codes.append(row.code)
            continue
        key_to_target[key] = (index, row.section)

    return _Legend(
        palette=palette,
        key_to_target=key_to_target,
        sample_color_to_index=sample_color_to_index,
        fractional_glyph_to_target=fractional,
        codes_by_section=codes_by_section,
        unknown_codes=unknown_codes,
        ambiguous_codes=ambiguous_codes,
    )


# --------------------------------------------------------------------------
# Numéros d'axe (repérage colonne/ligne absolue de chaque page de grille)
# --------------------------------------------------------------------------


def _most_common_font(chars: list[Char]) -> str:
    return Counter(str(c["fontname"]) for c in chars).most_common(1)[0][0]


def _chain_clusters(chars: list[Char], gap_limit: float) -> list[list[Char]]:
    """Regroupe des caractères consécutifs (dans l'ordre d'origine du flux
    PDF) en nombres à plusieurs chiffres, en coupant dès qu'un écart de
    position dépasse `gap_limit`. Fonctionne aussi bien pour un nombre
    horizontal classique que pour un nombre tourné/empilé verticalement
    (observé sur les numéros de ligne de la fixture de référence) — l'ordre
    du flux PDF donne toujours l'ordre de lecture correct, contrairement à
    un tri géométrique naïf par position."""
    clusters: list[list[Char]] = []
    current: list[Char] = []
    for c in chars:
        if current:
            prev = current[-1]
            dx = abs(float(c["x0"]) - float(prev["x0"]))
            dy = abs(float(c["top"]) - float(prev["top"]))
            if max(dx, dy) > gap_limit:
                clusters.append(current)
                current = []
        current.append(c)
    if current:
        clusters.append(current)
    return clusters


def _axis_points(candidates: list[Char], anchor: str) -> list[tuple[float, int]]:
    """Points `(position, valeur)` pour un ajustement linéaire position ->
    numéro d'axe. `anchor` vaut `"x"` pour les numéros de colonne (position
    = plus petit `x0` du groupe de chiffres) ou `"top"` pour les numéros de
    ligne (position = plus petit `top`) — cette convention « bord de départ
    minimal » aligne l'ancre du numéro sur celle des glyphes de la grille
    elle-même (positionnés par leur coin haut-gauche), quel que soit
    l'ordre d'empilement visuel des chiffres."""
    if not candidates:
        return []
    # Ne garder que la police majoritaire de la zone de marge : filtre le
    # bruit d'autres textes (numéro de page, etc.) qui tomberait par hasard
    # dans la même zone géométrique.
    dominant_font = _most_common_font(candidates)
    filtered = [c for c in candidates if c["fontname"] == dominant_font]
    widths = [float(c["x1"]) - float(c["x0"]) for c in filtered]
    heights = [float(c["bottom"]) - float(c["top"]) for c in filtered]
    if not widths or not heights:
        return []
    unit = statistics.median(widths + heights)
    gap_limit = unit * 3.0
    points: list[tuple[float, int]] = []
    for cluster in _chain_clusters(filtered, gap_limit):
        text = "".join(str(c["text"]) for c in cluster)
        if not text.isdigit():
            continue
        if anchor == "x":
            position = min(float(c["x0"]) for c in cluster)
        else:
            position = min(float(c["top"]) for c in cluster)
        points.append((position, int(text)))
    return points


def _fit_axes(grid_page: _GridPage, symbol_font: str) -> tuple[float, float, float, float] | None:
    """`(a_col, b_col, a_row, b_row)` tels que le numéro de colonne absolu
    (1-based) d'un glyphe de symbole à `x0` vaut `round(a_col + b_col*x0)`,
    et de même pour la ligne via `top`. `None` si pas assez de numéros
    d'axe exploitables sur cette page."""
    symbol_chars = grid_page.symbol_chars
    pitch_x, pitch_y = grid_page.pitch_x, grid_page.pitch_y
    min_sym_x = min(float(c["x0"]) for c in symbol_chars)
    max_sym_x = max(float(c["x1"]) for c in symbol_chars)
    min_sym_top = min(float(c["top"]) for c in symbol_chars)
    max_sym_top = max(float(c["bottom"]) for c in symbol_chars)

    digit_chars = [
        c
        for c in grid_page.all_chars
        if c["fontname"] != symbol_font
        and isinstance(c.get("text"), str)
        and str(c["text"]).isdigit()
    ]
    top_region = [
        c
        for c in digit_chars
        if float(c["top"]) < min_sym_top - pitch_y * 0.5
        and min_sym_x - 2 * pitch_x <= float(c["x0"]) <= max_sym_x + 2 * pitch_x
    ]
    left_region = [
        c
        for c in digit_chars
        if float(c["x0"]) < min_sym_x - pitch_x * 0.5
        and min_sym_top - 2 * pitch_y <= float(c["top"]) <= max_sym_top + 2 * pitch_y
    ]

    col_points = _axis_points(top_region, anchor="x")
    row_points = _axis_points(left_region, anchor="top")
    if len(col_points) < 2 or len(row_points) < 2:
        return None

    try:
        b_col, a_col = statistics.linear_regression(
            [p[0] for p in col_points], [p[1] for p in col_points]
        )
        b_row, a_row = statistics.linear_regression(
            [p[0] for p in row_points], [p[1] for p in row_points]
        )
    except statistics.StatisticsError:
        return None
    return a_col, b_col, a_row, b_row


# --------------------------------------------------------------------------
# Placement des glyphes de chaque page dans la grille absolue
# --------------------------------------------------------------------------


def _cell_key(char: Char, grid_page: _GridPage) -> CellKey:
    color = _rect_color_indexed(char, grid_page.rect_index, grid_page.pitch_x, grid_page.pitch_y)
    return (str(char["text"]), color)


def _set_placement(
    placements: dict[tuple[int, int], CellKey],
    position: tuple[int, int],
    key: CellKey,
    key_to_index: dict[CellKey, tuple[int, str]],
) -> None:
    """Écrit `key` à `position`, sauf si une valeur déjà reconnue par la
    légende y est présente et que `key`, elle, ne l'est pas. Nécessaire car
    les pages de grille voisines se chevauchent parfois sur quelques
    colonnes/lignes en bordure, et l'export type A observé y dessine un
    aperçu grisé (couleur d'aperçu, pas la couleur réelle du fil) plutôt
    qu'une simple répétition à l'identique — sans cette préférence, l'ordre
    de traitement des pages pourrait faire gagner l'aperçu grisé sur la
    valeur correcte de la page voisine (constaté sur la fixture de
    référence). Un vrai conflit entre deux valeurs toutes deux reconnues,
    ou toutes deux non reconnues, reste tranché par la dernière page
    traitée, comme demandé."""
    existing = placements.get(position)
    conflict = existing is not None and existing != key
    if conflict and existing in key_to_index and key not in key_to_index:
        return
    placements[position] = key


def _fit_all_axes(
    grid_pages: list[_GridPage], symbol_font: str
) -> dict[int, tuple[float, float, float, float] | None]:
    """Ajustement position -> numéro d'axe de chaque page, calculé une seule
    fois : le placement des glyphes (`_place_grid_pages`) et celui des points
    spéciaux (`_collect_special_stitches`, Lot 9) doivent partager
    exactement le même repère absolu, jamais deux ajustements refaits
    séparément."""
    return {gp.index: _fit_axes(gp, symbol_font) for gp in grid_pages}


def _is_offset_in_cell(char: Char, lattice: _CornerLattice) -> bool:
    """Vrai si le glyphe n'est pas centré dans sa case mais posé dans un de
    ses quadrants — la façon dont cet exporteur dessine un point fractionné
    **par-dessus** une case déjà occupée par un autre point.

    Mesuré sur la fixture de référence : 48 310 glyphes sur 48 314 sont
    exactement au centre de leur case, les 4 autres à (0.25, 0.27) — ce sont
    précisément les 4 points 1/4 annoncés par la légende."""
    col_fraction = lattice.col((float(char["x0"]) + float(char["x1"])) / 2) % 1.0
    row_fraction = lattice.row((float(char["top"]) + float(char["bottom"])) / 2) % 1.0
    return abs(col_fraction - 0.5) > 0.15 or abs(row_fraction - 0.5) > 0.15


def _place_grid_pages(
    grid_pages: list[_GridPage],
    key_to_index: dict[CellKey, tuple[int, str]],
    fits: dict[int, tuple[float, float, float, float] | None],
    lattices: dict[int, _CornerLattice | None],
) -> tuple[
    dict[tuple[int, int], CellKey], dict[tuple[int, int], str], list[DetectionWarning], float
]:
    """Place chaque glyphe de symbole dans des coordonnées absolues
    0-based `(row0, col0) -> (glyphe, couleur de fond)`.

    Deuxième valeur de retour (Lot 9) : les glyphes **décalés dans leur
    case** (voir `_is_offset_in_cell`), tenus à l'écart du placement normal.
    Les mélanger y ferait perdre un point plein ou un demi-point au profit
    du point fractionné dessiné par-dessus — exactement la régression que le
    Lot 9 ne doit jamais introduire."""
    placements: dict[tuple[int, int], CellKey] = {}
    offset_placements: dict[tuple[int, int], str] = {}
    warnings: list[DetectionWarning] = []
    penalty = 0.0
    fallback_col_offset = 0

    for grid_page in grid_pages:
        fit = fits.get(grid_page.index)
        lattice = lattices.get(grid_page.index)
        if fit is None:
            page_number = grid_page.index + 1
            warnings.append(
                DetectionWarning(
                    code="type_a.axis_numbers_missing_on_page",
                    params={"page": page_number},
                )
            )
            penalty += 0.15
            min_x = min(float(c["x0"]) for c in grid_page.symbol_chars)
            min_top = min(float(c["top"]) for c in grid_page.symbol_chars)
            local_cols = {
                round((float(c["x0"]) - min_x) / grid_page.pitch_x) for c in grid_page.symbol_chars
            }
            col_span = max(local_cols) + 1 if local_cols else 0
            for c in grid_page.symbol_chars:
                col0 = fallback_col_offset + round((float(c["x0"]) - min_x) / grid_page.pitch_x)
                row0 = round((float(c["top"]) - min_top) / grid_page.pitch_y)
                cell_key = _cell_key(c, grid_page)
                _set_placement(placements, (row0, col0), cell_key, key_to_index)
            fallback_col_offset += col_span
            continue

        a_col, b_col, a_row, b_row = fit
        for c in grid_page.symbol_chars:
            abs_col = round(a_col + b_col * float(c["x0"]))
            abs_row = round(a_row + b_row * float(c["top"]))
            col0 = abs_col - 1
            row0 = abs_row - 1
            if col0 < 0 or row0 < 0:
                continue
            if lattice is not None and _is_offset_in_cell(c, lattice):
                offset_col = math.floor(lattice.col((float(c["x0"]) + float(c["x1"])) / 2))
                offset_row = math.floor(lattice.row((float(c["top"]) + float(c["bottom"])) / 2))
                if offset_col >= 0 and offset_row >= 0:
                    offset_placements[(offset_row, offset_col)] = str(c["text"])
                continue
            _set_placement(placements, (row0, col0), _cell_key(c, grid_page), key_to_index)

    return placements, offset_placements, warnings, penalty


# --------------------------------------------------------------------------
# Points spéciaux : points arrière et nœuds (Lot 9)
# --------------------------------------------------------------------------


def _line_points(line: Char) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Vraies extrémités `((x, top), (x, top))` d'un segment, lues dans
    `pts` (coordonnées haut-bas, comme `top`) plutôt que dans la bbox.

    Indispensable : la bbox d'un segment perd le sens de sa diagonale — une
    diagonale montante et une diagonale descendante ont exactement la même
    bbox. Mesuré sur la fixture de référence : 36 des 56 diagonales de point
    arrière de sa page 1 sont descendantes et seraient toutes tracées à
    l'envers si on lisait `(x0, top) -> (x1, bottom)`."""
    pts = line.get("pts")
    if not isinstance(pts, list | tuple) or len(pts) != 2:
        return None
    (ax, ay), (bx, by) = pts[0], pts[1]
    return (float(ax), float(ay)), (float(bx), float(by))


def _lattice_axis(positions: list[float]) -> tuple[float, float] | None:
    """`(origine, pas)` du réseau régulier le mieux ajusté sur `positions`
    (les abscisses des réglures verticales, ou les ordonnées des
    horizontales). Régression sur les indices de réseau plutôt que sur le
    rang : une frontière de case sans réglure imprimée (remplacée par la
    réglure décimale, ou masquée par la bordure) ne décale pas tout ce qui
    suit."""
    uniq = sorted({round(p, 2) for p in positions})
    if len(uniq) < 3:
        return None
    diffs = [b - a for a, b in zip(uniq, uniq[1:], strict=False) if b - a > 1.0]
    if len(diffs) < 2:
        return None
    pitch = statistics.median(diffs)
    if pitch <= 0:
        return None
    indices = [round((p - uniq[0]) / pitch) for p in uniq]
    if len(set(indices)) < 3:
        return None
    try:
        slope, intercept = statistics.linear_regression(indices, uniq)
    except statistics.StatisticsError:
        return None
    if slope <= 0:
        return None
    return intercept, slope


def _majority_offset(counts: Counter[int], total: int) -> int | None:
    """Décalage entier majoritaire, seulement s'il fait consensus (au moins
    80 % des glyphes) — sinon le réseau de réglures ne décrit pas la même
    grille que les symboles, et mieux vaut renoncer aux points spéciaux de
    cette page que les placer à côté."""
    if not counts or total <= 0:
        return None
    offset, hits = counts.most_common(1)[0]
    if hits / total < 0.8:
        return None
    return offset


def _build_corner_lattice(
    page: Page,
    grid_page: _GridPage,
    fit: tuple[float, float, float, float],
) -> _CornerLattice | None:
    """Réseau des coins de case de `page`, en coordonnées absolues — voir
    `_CornerLattice` pour la raison de ne pas réutiliser directement
    l'ajustement sur les numéros d'axe."""
    chars = grid_page.symbol_chars
    min_x = min(float(c["x0"]) for c in chars)
    max_x = max(float(c["x1"]) for c in chars)
    min_top = min(float(c["top"]) for c in chars)
    max_top = max(float(c["bottom"]) for c in chars)
    span_x = max_x - min_x
    span_y = max_top - min_top
    if span_x <= 0 or span_y <= 0:
        return None

    verticals: list[float] = []
    horizontals: list[float] = []
    for line in page.lines:
        points = _line_points(line)
        if points is None:
            continue
        (ax, ay), (bx, by) = points
        dx, dy = abs(bx - ax), abs(by - ay)
        if dx < 0.5 and dy >= 0.8 * span_y:
            verticals.append(ax)
        elif dy < 0.5 and dx >= 0.8 * span_x:
            horizontals.append(ay)

    lattice_x = _lattice_axis(verticals)
    lattice_y = _lattice_axis(horizontals)
    if lattice_x is None or lattice_y is None:
        return None
    origin_x, pitch_x = lattice_x
    origin_top, pitch_y = lattice_y

    a_col, b_col, a_row, b_row = fit
    col_offsets: Counter[int] = Counter()
    row_offsets: Counter[int] = Counter()
    for char in chars:
        x0 = float(char["x0"])
        top = float(char["top"])
        col_offsets[round(a_col + b_col * x0) - 1 - math.floor((x0 - origin_x) / pitch_x)] += 1
        row_offsets[round(a_row + b_row * top) - 1 - math.floor((top - origin_top) / pitch_y)] += 1
    offset_col = _majority_offset(col_offsets, len(chars))
    offset_row = _majority_offset(row_offsets, len(chars))
    if offset_col is None or offset_row is None:
        return None

    return _CornerLattice(
        origin_x=origin_x,
        pitch_x=pitch_x,
        offset_col=offset_col,
        origin_top=origin_top,
        pitch_y=pitch_y,
        offset_row=offset_row,
        span_x=span_x,
        span_y=span_y,
    )


def _build_all_lattices(
    pages: list[Page],
    grid_pages: list[_GridPage],
    fits: dict[int, tuple[float, float, float, float] | None],
) -> dict[int, _CornerLattice | None]:
    """Réseau de coins de chaque page de grille, calculé une seule fois et
    partagé par le placement des glyphes et celui des points spéciaux."""
    lattices: dict[int, _CornerLattice | None] = {}
    for grid_page in grid_pages:
        fit = fits.get(grid_page.index)
        lattices[grid_page.index] = (
            _build_corner_lattice(pages[grid_page.index], grid_page, fit)
            if fit is not None
            else None
        )
    return lattices


def _snap_half(value: float) -> tuple[float, bool]:
    """Valeur ramenée au demi-multiple le plus proche (coin de case ou
    milieu de case) et un drapeau disant si elle y tombait vraiment. Un
    exporteur qui poserait ses points arrière ailleurs n'est jamais
    déformé de force : la valeur brute est conservée et signalée."""
    snapped = round(value * 2) / 2
    return (snapped, True) if abs(value - snapped) <= _SNAP_TOLERANCE else (round(value, 3), False)


@dataclass
class _SpecialStitches:
    backstitch: list[BackstitchSegment] = field(default_factory=list)
    french_knots: list[FrenchKnot] = field(default_factory=list)
    warnings: list[DetectionWarning] = field(default_factory=list)
    penalty: float = 0.0


def _color_resolver(
    legend: _Legend, section: str
) -> tuple[dict[Color, int], dict[str, int], bool]:
    """`(couleurs exactes, codes déclarés, repli colorimétrique)` pour une
    section à échantillon.

    Le signal principal est l'**égalité exacte** entre la couleur d'un tracé
    de grille et celle de l'échantillon imprimé dans la légende : c'est une
    correspondance mesurée dans le fichier, pas une ressemblance. Elle est
    indispensable ici — sur la fixture de référence, l'exporteur trace le
    point arrière DMC 310 « Black » en (35, 40, 29) et le DMC 938 en
    (64, 54, 34), deux valeurs qu'un simple plus proche voisin Lab
    attribuerait au mauvais code (vérifié : 938 et 3031 y sont permutés).
    Le rapprochement perceptuel n'est qu'un repli, signalé comme tel."""
    indices = set(legend.codes_by_section.get(section, ()))
    colors = {
        color: index for color, index in legend.sample_color_to_index.items() if index in indices
    }
    codes = {
        legend.palette[index - 1].code: index
        for index in indices
        if legend.palette[index - 1].code
    }
    return colors, codes, not colors and bool(codes)


def _index_for_color(
    color: Color,
    exact: dict[Color, int],
    codes: dict[str, int],
    fallback: bool,
    cache: dict[Color, int | None],
) -> int | None:
    """Index de palette d'un tracé, par couleur exacte puis (seulement si la
    légende n'a aucun échantillon) par plus proche voisin Lab parmi les
    codes déclarés de la section."""
    index = exact.get(color)
    if index is not None:
        return index
    if not fallback or len(color) < 3:
        return None
    if color in cache:
        return cache[color]
    rgb = (color[0], color[1], color[2])
    match = nearest_dmc_among(rgb, codes)
    resolved: int | None = None
    if match is not None and match.distance <= _FALLBACK_MAX_LAB_DISTANCE:
        resolved = codes.get(match.code)
    cache[color] = resolved
    return resolved


def _object_colors(obj: Char) -> tuple[Color, ...]:
    stroking = _normalize_color(obj.get("stroking_color"))
    non_stroking = _normalize_color(obj.get("non_stroking_color"))
    return tuple(color for color in (stroking, non_stroking) if color)


@dataclass(frozen=True)
class _ColorMatcher:
    """Rapprochement couleur d'un tracé -> entrée de palette, pour une
    section à échantillon (voir `_color_resolver`)."""

    exact: dict[Color, int]
    codes: dict[str, int]
    fallback: bool
    cache: dict[Color, int | None]

    def index_of(self, obj: Char) -> int | None:
        for color in _object_colors(obj):
            index = _index_for_color(color, self.exact, self.codes, self.fallback, self.cache)
            if index is not None:
                return index
        return None

    def __bool__(self) -> bool:
        return bool(self.codes)


def _collect_special_stitches(
    pages: list[Page],
    lattices: dict[int, _CornerLattice | None],
    legend: _Legend,
    columns: int,
    rows: int,
) -> _SpecialStitches:
    """Points arrière et nœuds de toutes les pages de grille, ramenés dans
    le repère absolu de la grille assemblée.

    Trois filtres, dans cet ordre (mesures à l'appui, voir le rapport du
    Lot 9) :

    1. **couleur** — seul un tracé dont la couleur est celle d'un échantillon
       de la légende est retenu. C'est ce filtre qui écarte d'un coup les
       réglures, les flèches de repère de page, les annotations manuelles
       laissées dans le PDF (traits bleus système sur deux pages de la
       fixture) et surtout les **copies d'aperçu grisées** que chaque page
       dessine dans sa bande de recouvrement avec la page voisine (mesuré :
       8 teintes délavées supplémentaires, jamais présentes ailleurs que
       par-dessus un tracé déjà compté) ;
    2. **forme** — un trait aligné sur les axes, posé sur une frontière de
       case *et* assez long pour traverser la grille reste une réglure, même
       si sa couleur correspond (cas d'un motif dont le point arrière serait
       noir comme le quadrillage) ; un nœud doit être une petite forme
       pleine plus petite qu'une case ;
    3. **emprise** — tout ce qui tombe hors des limites de la grille
       assemblée est écarté (roadmap Lot 9 §3 : un point arrière décoratif
       de page de garde ne doit jamais être importé comme à broder). Les
       pages de légende ne sont de toute façon jamais parcourues ici.
    """
    result = _SpecialStitches()
    cache: dict[Color, int | None] = {}
    back = _ColorMatcher(*_color_resolver(legend, BACKSTITCH), cache=cache)
    knot = _ColorMatcher(*_color_resolver(legend, FRENCH_KNOT), cache=cache)
    if not back and not knot:
        return result

    segments: dict[tuple[float, float, float, float, int], BackstitchSegment] = {}
    knots: dict[tuple[float, float, int], FrenchKnot] = {}
    skipped_pages: list[int] = []
    off_grid = 0
    unsnapped = 0

    for page_index, lattice in sorted(lattices.items()):
        page = pages[page_index]
        if lattice is None:
            skipped_pages.append(page_index + 1)
            continue

        ruling_min_length = _RULING_MIN_SPAN_RATIO * min(lattice.span_x, lattice.span_y)
        for line in page.lines:
            index = back.index_of(line)
            if index is None:
                continue
            points = _line_points(line)
            if points is None:
                continue
            (ax, ay), (bx, by) = points
            if is_grid_ruling(
                ax,
                ay,
                bx,
                by,
                origin_x=lattice.origin_x,
                origin_top=lattice.origin_top,
                pitch_x=lattice.pitch_x,
                pitch_y=lattice.pitch_y,
                min_length=ruling_min_length,
            ):
                continue
            if line_length(ax, ay, bx, by) < 0.5:
                continue
            x1, ok_x1 = _snap_half(lattice.col(ax))
            y1, ok_y1 = _snap_half(lattice.row(ay))
            x2, ok_x2 = _snap_half(lattice.col(bx))
            y2, ok_y2 = _snap_half(lattice.row(by))
            unsnapped += sum(1 for ok in (ok_x1, ok_y1, ok_x2, ok_y2) if not ok)
            if not _within_grid(x1, y1, columns, rows) or not _within_grid(x2, y2, columns, rows):
                off_grid += 1
                continue
            # Ordre canonique des deux extrémités : le même segment dessiné
            # dans un sens sur une page et dans l'autre sur la page voisine
            # (bande de recouvrement) ne doit compter qu'une fois.
            (ux, uy), (vx, vy) = sorted([(x1, y1), (x2, y2)])
            segments.setdefault(
                (ux, uy, vx, vy, index),
                BackstitchSegment(x1=ux, y1=uy, x2=vx, y2=vy, palette_index=index),
            )

        for curve in page.curves:
            if not curve.get("fill"):
                continue
            width = float(curve["x1"]) - float(curve["x0"])
            height = float(curve["bottom"]) - float(curve["top"])
            if width > _KNOT_MAX_CELLS * lattice.pitch_x:
                continue
            if height > _KNOT_MAX_CELLS * lattice.pitch_y:
                continue
            index = knot.index_of(curve)
            if index is None:
                continue
            x, _ok_x = _snap_half(lattice.col((float(curve["x0"]) + float(curve["x1"])) / 2))
            y, _ok_y = _snap_half(lattice.row((float(curve["top"]) + float(curve["bottom"])) / 2))
            if not _within_grid(x, y, columns, rows):
                off_grid += 1
                continue
            knots.setdefault((x, y, index), FrenchKnot(x=x, y=y, palette_index=index))

    result.backstitch = sorted(
        segments.values(), key=lambda s: (s.y1, s.x1, s.y2, s.x2, s.palette_index)
    )
    result.french_knots = sorted(knots.values(), key=lambda k: (k.y, k.x, k.palette_index))

    if skipped_pages:
        result.warnings.append(
            DetectionWarning(
                code="type_a.special_stitches_page_skipped",
                params={
                    "count": len(skipped_pages),
                    "pages": ", ".join(str(page) for page in skipped_pages),
                },
            )
        )
        result.penalty += min(0.2, 0.05 * len(skipped_pages))
    if back.fallback or knot.fallback:
        result.warnings.append(
            DetectionWarning(
                code="type_a.special_stitches_colour_fallback",
                params={
                    "backstitch": len(result.backstitch),
                    "french_knots": len(result.french_knots),
                },
            )
        )
        result.penalty += 0.1
    if off_grid:
        result.warnings.append(
            DetectionWarning(code="type_a.special_stitches_off_grid", params={"count": off_grid})
        )
    if unsnapped:
        result.warnings.append(
            DetectionWarning(
                code="type_a.backstitch_endpoints_unsnapped", params={"count": unsnapped}
            )
        )
        result.penalty += 0.05

    return result


def _within_grid(x: float, y: float, columns: int, rows: int) -> bool:
    epsilon = 0.01
    return -epsilon <= x <= columns + epsilon and -epsilon <= y <= rows + epsilon


def _cross_check_sections(legend: _Legend, result: TypeAResult) -> list[DetectionWarning]:
    """Croisement entre ce que la légende **annonce** et ce qui a été
    **extrait** (roadmap Lot 9 §4, cahier des charges §7.3) : un fil déclaré
    en point 1/2, 1/4, arrière ou nœud dont rien n'a été retrouvé dans la
    grille est signalé, plutôt que de laisser croire que le motif n'en
    comporte pas.

    Seule la légende des pages de texte sert ici. La page « Usage Summary »
    du fichier de référence, elle, reste **exclusivement** la vérité terrain
    indépendante des tests (`backend/tests/test_type_a.py`) : la consommer
    aussi dans le moteur reviendrait à valider l'extraction avec sa propre
    source et ne prouverait plus rien."""
    warnings: list[DetectionWarning] = []
    found: dict[str, set[int]] = {
        BACKSTITCH: {segment.palette_index for segment in result.backstitch},
        FRENCH_KNOT: {knot.palette_index for knot in result.french_knots},
        HALF: {value for value in result.cells_half if value},
        QUARTER: {value for value in result.cells_quarter if value},
    }
    for section in (HALF, QUARTER, BACKSTITCH, FRENCH_KNOT):
        declared = set(legend.codes_by_section.get(section, ()))
        missing = sorted(declared - found[section])
        if not missing:
            continue
        warnings.append(
            DetectionWarning(
                code=f"type_a.{section}_codes_missing",
                params={
                    "count": len(missing),
                    "codes": ", ".join(legend.palette[index - 1].code for index in missing),
                },
            )
        )
    return warnings


# --------------------------------------------------------------------------
# Dimensions et assemblage final
# --------------------------------------------------------------------------


def _find_declared_dimensions(pages: list[Page]) -> tuple[int, int] | None:
    """Dimensions annoncées en clair par le PDF lui-même (p. ex. `"255w X
    180h Stitches"`) — préférées à l'étendue déduite de la grille assemblée
    quand elles sont disponibles (cahier des charges §7.2 étape 6)."""
    for page in pages:
        match = _DECLARED_DIMENSIONS_RE.search(page.extract_text())
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None


def _find_fabric_count(pages: list[Page]) -> int | None:
    """Compte de toile déclaré en clair (« Fabric: Aida 16, White »), utile
    pour convertir en centimètres une longueur de point arrière mesurée en
    cases. `None` si le PDF ne le déclare pas : aucune valeur par défaut
    n'est inventée (une longueur physique fausse serait pire qu'absente)."""
    for page in pages:
        match = _FABRIC_COUNT_RE.search(page.extract_text())
        if match is None:
            continue
        count = int(match.group(1))
        if 6 <= count <= 40:
            return count
    return None


def _resolve_dimensions(
    declared: tuple[int, int] | None,
    placements: dict[tuple[int, int], CellKey],
) -> tuple[int, int, DetectionWarning | None, float]:
    max_col_seen = max((col0 for _row0, col0 in placements), default=-1) + 1
    max_row_seen = max((row0 for row0, _col0 in placements), default=-1) + 1

    if declared is None:
        return (
            max_col_seen,
            max_row_seen,
            DetectionWarning(code="type_a.dimensions_inferred"),
            0.05,
        )

    columns, rows = declared
    if columns != max_col_seen or rows != max_row_seen:
        warning = DetectionWarning(
            code="type_a.dimensions_mismatch",
            params={
                "declared_columns": columns,
                "declared_rows": rows,
                "seen_columns": max_col_seen,
                "seen_rows": max_row_seen,
            },
        )
        return columns, rows, warning, 0.1
    return columns, rows, None, 0.0


def _unmapped_symbol_key(symbol_char: str, used: set[str]) -> str:
    """Clé stable dérivée du point de code du glyphe (jamais le glyphe brut
    — voir `TypeAPaletteEntry.symbol_key`), avec un suffixe si le même
    glyphe apparaît déjà sous une autre couleur non reconnue."""
    base = f"U+{ord(symbol_char):04X}"
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}-{suffix}" in used:
        suffix += 1
    key = f"{base}-{suffix}"
    used.add(key)
    return key


@dataclass
class _Layers:
    """Les trois couches de cases d'un motif type A. `half`/`quarter` sont
    vides quand la légende ne déclare aucun point de cette catégorie —
    jamais une grille de zéros (voir `TypeAResult.cells_half`)."""

    full: list[int]
    half: list[int] = field(default_factory=list)
    quarter: list[int] = field(default_factory=list)
    warning: DetectionWarning | None = None
    extra_warnings: list[DetectionWarning] = field(default_factory=list)
    penalty: float = 0.0


def _fill_cells(
    columns: int,
    rows: int,
    placements: dict[tuple[int, int], CellKey],
    offset_placements: dict[tuple[int, int], str],
    legend: _Legend,
    palette: list[TypeAPaletteEntry],
) -> _Layers:
    """Répartit les glyphes placés dans la couche de leur **catégorie**.

    Un symbole donné n'appartient qu'à une seule section de légende (points
    entiers, 1/2 ou 1/4) : c'est cette section, et non une devinette sur la
    forme du glyphe, qui décide de la couche. Un symbole non rapproché de la
    légende reste traité comme avant le Lot 9 — entrée « Symbole non
    reconnu » explicite dans la couche des points entiers, jamais une case
    vide silencieuse."""
    key_to_target = legend.key_to_target
    layers = {
        FULL: [0] * (columns * rows),
        HALF: [0] * (columns * rows),
        QUARTER: [0] * (columns * rows),
    }
    used: dict[str, int] = {FULL: 0, HALF: 0, QUARTER: 0}
    unmapped_index: dict[CellKey, int] = {}
    used_symbol_keys = {entry.symbol_key for entry in palette}
    affected_cells = 0
    total_placed = 0
    unmatched_offsets = 0

    for (row0, col0), glyph in offset_placements.items():
        if row0 >= rows or col0 >= columns:
            continue
        target = legend.fractional_glyph_to_target.get(glyph)
        if target is None:
            # Glyphe décalé que la légende ne rattache à aucune section
            # fractionnée : on préfère le signaler et l'ignorer plutôt que
            # de l'écrire dans la couche des points entiers, où il
            # fausserait un comptage déjà correct.
            unmatched_offsets += 1
            continue
        index, category = target
        if category in layers:
            layers[category][row0 * columns + col0] = index
            used[category] += 1

    for (row0, col0), key in placements.items():
        if row0 >= rows or col0 >= columns:
            continue
        total_placed += 1
        target = key_to_target.get(key)
        if target is None:
            if key not in unmapped_index:
                symbol_char = key[0]
                palette.append(
                    TypeAPaletteEntry(
                        code="",
                        name="Symbole non reconnu",
                        symbol_key=_unmapped_symbol_key(symbol_char, used_symbol_keys),
                        rgb_hex=FALLBACK_HEX,
                    )
                )
                unmapped_index[key] = len(palette)
            target = (unmapped_index[key], FULL)
            affected_cells += 1
        index, category = target
        if category not in layers:
            # Section de légende sans couche de cases (points arrière,
            # nœuds) : un glyphe ne devrait jamais y être rattaché, mais on
            # préfère l'ignorer que l'écrire dans la mauvaise couche.
            continue
        layers[category][row0 * columns + col0] = index
        used[category] += 1

    result = _Layers(
        full=layers[FULL],
        half=layers[HALF] if used[HALF] else [],
        quarter=layers[QUARTER] if used[QUARTER] else [],
    )
    if unmapped_index:
        result.warning = DetectionWarning(
            code="type_a.unmapped_symbols",
            params={"count": len(unmapped_index), "cells": affected_cells},
        )
        fraction = affected_cells / total_placed if total_placed else 0.0
        result.penalty = min(0.4, fraction)
    if unmatched_offsets:
        result.extra_warnings.append(
            DetectionWarning(
                code="type_a.fractional_glyphs_unmatched",
                params={"count": unmatched_offsets},
            )
        )
        result.penalty += 0.05
    return result


def _count_palette_usage(result: TypeAResult) -> None:
    """Reporte sur chaque entrée de palette ce qui la référence réellement
    dans la grille assemblée — comptages par catégorie et longueur cumulée
    de point arrière. Calculé ici, une seule fois, plutôt que laissé à
    l'appelant : c'est la même donnée que celle qu'un tableau de légende
    imprimé affiche, et elle ne doit exister qu'à un seul endroit."""
    for entry in result.palette:
        entry.count_full = 0
        entry.count_half = 0
        entry.count_quarter = 0
        entry.count_french_knots = 0
        entry.backstitch_length_cells = 0.0

    def tally(cells: list[int], attribute: str) -> None:
        for index, count in Counter(cells).items():
            if index <= 0 or index > len(result.palette):
                continue
            entry = result.palette[index - 1]
            setattr(entry, attribute, getattr(entry, attribute) + count)

    tally(result.cells, "count_full")
    tally(result.cells_half, "count_half")
    tally(result.cells_quarter, "count_quarter")
    for knot in result.french_knots:
        if 0 < knot.palette_index <= len(result.palette):
            result.palette[knot.palette_index - 1].count_french_knots += 1
    for segment in result.backstitch:
        if 0 < segment.palette_index <= len(result.palette):
            entry = result.palette[segment.palette_index - 1]
            entry.backstitch_length_cells += math.hypot(
                segment.x2 - segment.x1, segment.y2 - segment.y1
            )
