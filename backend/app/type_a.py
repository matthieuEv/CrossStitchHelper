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

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
from pdfplumber.page import Page

from app.dmc_colors import FALLBACK_HEX, dmc_hex

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
_FULL_STITCHES_HEADER = "Floss Used for Full Stitches:"
_SECTION_HEADER_PREFIX = "Floss Used for "
_LEGEND_ROW_RE = re.compile(r"^(\S)\s*\d+\s*DMC\s+([A-Za-z0-9]+)\s+(.+)$")


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


@dataclass
class TypeAResult:
    columns: int
    rows: int
    cells: list[int]
    """Longueur `columns * rows`, ligne par ligne, (0,0) en haut à gauche en
    premier. 0 = case vide, n = index 1-based dans `palette`."""
    palette: list[TypeAPaletteEntry]
    confidence: float
    warnings: list[str] = field(default_factory=list)


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
    symbol_char: str
    code: str
    name: str
    swatch_color: Color | None
    glyph: SymbolGlyphLocation | None


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

        warnings: list[str] = []
        confidence = 1.0

        legend_rows = _parse_full_stitches_rows(pages)
        if not legend_rows:
            warnings.append(
                "Aucune section « Floss Used for Full Stitches » trouvée dans la "
                "légende : la palette de couleurs n'a pas pu être reconstruite "
                "automatiquement."
            )
            confidence -= 0.5

        palette, key_to_index, unknown_codes, ambiguous_codes = _build_palette(legend_rows)
        if unknown_codes:
            warnings.append(
                "Code(s) DMC absent(s) de la table de couleurs locale : "
                + ", ".join(unknown_codes)
                + " — couleur d'affichage approximative utilisée (le code et le nom "
                "restent ceux imprimés dans le PDF)."
            )
            confidence -= min(0.1, 0.02 * len(unknown_codes))
        if ambiguous_codes:
            warnings.append(
                "Code(s) DMC dont le symbole et la couleur de repère sont identiques à "
                "une autre ligne de la légende, rendant leurs cases indistinguables : "
                + ", ".join(ambiguous_codes)
                + " — cases attribuées à la première ligne correspondante."
            )
            confidence -= min(0.2, 0.05 * len(ambiguous_codes))

        placements, page_warnings, page_penalty = _place_grid_pages(grid_pages, key_to_index)
        warnings.extend(page_warnings)
        confidence -= page_penalty

        declared = _find_declared_dimensions(pages)
        columns, rows, dims_warning, dims_penalty = _resolve_dimensions(declared, placements)
        if dims_warning:
            warnings.append(dims_warning)
            confidence -= dims_penalty

        if columns <= 0 or rows <= 0:
            return None

        cells, unmapped_warning, unmapped_penalty = _fill_cells(
            columns, rows, placements, key_to_index, palette
        )
        if unmapped_warning:
            warnings.append(unmapped_warning)
            confidence -= unmapped_penalty

        confidence = max(0.0, min(1.0, confidence))
        return TypeAResult(
            columns=columns,
            rows=rows,
            cells=cells,
            palette=palette,
            confidence=confidence,
            warnings=warnings,
        )


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


def _parse_full_stitches_rows(pages: list[Page]) -> list[_LegendRow]:
    rows: list[_LegendRow] = []
    for page in pages:
        rects = page.rects
        in_section = False
        for line in page.extract_text_lines():
            text = str(line["text"])
            if text.startswith(_FULL_STITCHES_HEADER):
                in_section = True
                continue
            if not in_section:
                continue
            if text.startswith(_SECTION_HEADER_PREFIX):
                # Une autre section commence ("Half Stitches", "Quarter
                # Stitches", ...) — hors périmètre du Lot 4.
                break
            if text.startswith("Symbol Strands"):
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


def _build_palette(
    legend_rows: list[_LegendRow],
) -> tuple[list[TypeAPaletteEntry], dict[CellKey, int], list[str], list[str]]:
    palette: list[TypeAPaletteEntry] = []
    key_to_index: dict[CellKey, int] = {}
    unknown_codes: list[str] = []
    ambiguous_codes: list[str] = []
    for row in legend_rows:
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
        key: CellKey = (row.symbol_char, row.swatch_color)
        if key in key_to_index:
            # Deux lignes de légende partagent le même glyphe ET la même
            # couleur de fond : on ne peut structurellement pas distinguer
            # leurs cases dans la grille — on garde la première association
            # (comportement conservateur) et on le signale clairement plutôt
            # que d'écraser silencieusement.
            ambiguous_codes.append(row.code)
            continue
        key_to_index[key] = index
    return palette, key_to_index, unknown_codes, ambiguous_codes


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
    key_to_index: dict[CellKey, int],
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


def _place_grid_pages(
    grid_pages: list[_GridPage],
    key_to_index: dict[CellKey, int],
) -> tuple[dict[tuple[int, int], CellKey], list[str], float]:
    """Place chaque glyphe de symbole dans des coordonnées absolues
    0-based `(row0, col0) -> (glyphe, couleur de fond)`."""
    placements: dict[tuple[int, int], CellKey] = {}
    warnings: list[str] = []
    penalty = 0.0
    fallback_col_offset = 0
    # Nécessaire pour déterminer une police de symboles au singulier avant
    # les boucles ci-dessous — déjà garanti par l'appelant (grid_pages non
    # vide), mais on le redérive localement pour rester autonome.
    symbol_font = _most_common_font(
        [c for gp in grid_pages for c in gp.symbol_chars]
    )

    for grid_page in grid_pages:
        fit = _fit_axes(grid_page, symbol_font)
        if fit is None:
            page_number = grid_page.index + 1
            warnings.append(
                f"Page {page_number} : numéros d'axe introuvables, positionnement "
                "approximatif par ordre de lecture plutôt qu'abandon de la page."
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
            _set_placement(placements, (row0, col0), _cell_key(c, grid_page), key_to_index)

    return placements, warnings, penalty


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


def _resolve_dimensions(
    declared: tuple[int, int] | None,
    placements: dict[tuple[int, int], CellKey],
) -> tuple[int, int, str | None, float]:
    max_col_seen = max((col0 for _row0, col0 in placements), default=-1) + 1
    max_row_seen = max((row0 for row0, _col0 in placements), default=-1) + 1

    if declared is None:
        warning = (
            "Dimensions non annoncées explicitement dans le PDF : déduites de "
            "l'étendue de la grille assemblée."
        )
        return max_col_seen, max_row_seen, warning, 0.05

    columns, rows = declared
    if columns != max_col_seen or rows != max_row_seen:
        warning = (
            f"Les dimensions annoncées par le PDF ({columns}×{rows}) ne correspondent "
            f"pas exactement à l'étendue reconstruite ({max_col_seen}×{max_row_seen}) "
            "— dimensions annoncées conservées."
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


def _fill_cells(
    columns: int,
    rows: int,
    placements: dict[tuple[int, int], CellKey],
    key_to_index: dict[CellKey, int],
    palette: list[TypeAPaletteEntry],
) -> tuple[list[int], str | None, float]:
    cells = [0] * (columns * rows)
    unmapped_index: dict[CellKey, int] = {}
    used_symbol_keys = {entry.symbol_key for entry in palette}
    affected_cells = 0
    total_placed = 0

    for (row0, col0), key in placements.items():
        if row0 >= rows or col0 >= columns:
            continue
        total_placed += 1
        index = key_to_index.get(key)
        if index is None:
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
            index = unmapped_index[key]
            affected_cells += 1
        cells[row0 * columns + col0] = index

    if not unmapped_index:
        return cells, None, 0.0

    warning = (
        f"{len(unmapped_index)} symbole(s)/couleur(s) sans correspondance dans la "
        f"légende ({affected_cells} case(s) concernée(s)) — ajouté(s) à la palette "
        "comme « Symbole non reconnu »."
    )
    fraction = affected_cells / total_placed if total_placed else 0.0
    penalty = min(0.4, fraction)
    return cells, warning, penalty
