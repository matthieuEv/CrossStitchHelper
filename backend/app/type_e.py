"""Détection automatique du type E (catalogue fermé d'images bitmap
réutilisées, couleur + symbole déjà combinés dans chaque image — cahier des
charges §4.3, §4.4, Lot 7).

Contrairement aux types A (police de symboles, `app/type_a.py`) et B/C
(rectangles + tracés vectoriels, `app/type_bc.py`), une page de grille type E
n'a **ni texte positionné, ni rectangle de couleur, ni tracé vectoriel** : la
grille entière est composée de petites images bitmap réutilisées des
centaines ou milliers de fois. Identifier la case revient donc à un problème
de *classification d'image sur un petit catalogue fermé*, jamais une lecture
directe de couleur ou de glyphe.

**Mesures faites sur l'unique fixture de ce type
(`river-and-mountains-laserarts/RiverAndMountains-CS.pdf`, 18 pages, éditeur
LaserArtsDesigns) avant d'écrire une seule ligne de ce module** — voir aussi
`fixtures/README.md` :

- Les pages de grille réelles (2 à 16 dans ce fichier) forment un mosaïque de
  5 pages en largeur x 3 pages en hauteur. Chacune place des images d'une
  seule taille homogène (64x64 px), occupant 100 % de ses placements
  (`dominant_frac`) — jamais un mélange de tailles.
- La page 1 (prévisualisation photoréaliste) mélange DEUX tailles d'image
  (48x48 et 64x64 px) pour un rendu par empâtement de texture : sa taille
  dominante ne couvre que **69,8 %** de ses 40 084 placements, très en
  dessous de `_MIN_DOMINANT_SIZE_FRACTION` — c'est ce qui l'exclut, jamais sa
  position de "page 1" supposée a priori (cf. `CLAUDE.md` : ne jamais
  supposer une structure fixe sans la mesurer).
- La page 18 (carte d'assemblage des 15 pages de grille, jamais une page de
  travail) place des images bien plus grandes (207x294 pt) et **non
  carrées** (ratio largeur/hauteur ≈ 0,70) — exclue par
  `_MAX_ASPECT_DEVIATION`, très en dessous du seuil mesuré ici.
- La page de légende (17 dans ce fichier) réutilise les mêmes images 64x64
  que les pages de grille (mêmes symboles, en aperçu) : ni la taille
  d'image, ni le taux de réutilisation ne suffisent à l'exclure. C'est
  l'absence de texte d'axe (voir `_fit_axes` ci-dessous) qui l'exclut : ses
  images sont alignées en une seule colonne verticale (une ligne de légende
  par couleur), jamais pavées sur un quadrillage à deux axes numérotés.
- **Nombre réel d'images distinctes utilisées par les pages de grille : 20,
  pas ~531 ni ~41.** Mesuré en cumulant les `digest` distincts (empreinte de
  contenu déjà calculée par PyMuPDF, `page.get_image_info(xrefs=True)`) sur
  les pages de grille strictement (2 à 16) : la convergence se stabilise dès
  la page 5, aucune nouvelle image sur les pages suivantes. Un chiffre plus
  élevé (531, ou 41 en cumulant par erreur avec les images de la page 1 de
  prévisualisation, dont le catalogue est totalement disjoint : 21 images
  distinctes, zéro chevauchement avec les 20 des pages de grille) provenait
  d'une confusion entre nombre de *placements* sur une seule page (531 est
  le nombre de placements de la page 2, pas un nombre d'images distinctes)
  et nombre d'images réellement distinctes. Voir `docs/cahier-des-charges.md`
  §4.3 et `fixtures/README.md`, corrigés en conséquence.
- Ces 20 images correspondent **exactement** aux 20 couleurs DMC de la
  légende (page 17) — une image par couleur, jamais deux variantes par
  couleur comme on aurait pu le supposer avant de les avoir rendues et
  regardées (`doc.extract_image` + Pillow) : chaque image combine déjà un
  aplat de fond uni (la couleur du fil) et un petit symbole dessiné par
  dessus en couleur contrastante (blanc sur fond sombre, noir sur fond
  clair) — confirmé visuellement sur une planche de contact des 20 images.
- **Rapprocher la couleur de fond de chaque image vers le code DMC le plus
  proche (même restreint aux 20 codes de la légende) est peu fiable sur ce
  fichier : 12 des 20 images sur 20 sont mal identifiées par ce seul signal**
  (distances Lab de 5 à plus de 20, et 8 des 20 codes de légende
  n'existaient même pas dans `app/dmc_catalog.py`, catalogue communautaire
  nécessairement partiel, §3.3). La couleur réellement rendue par cet
  éditeur ne correspond visiblement pas exactement aux teintes DMC
  officielles approximées par ce catalogue. **Signal bien plus fiable et
  vérifié exact sur les 20 couleurs (aucune erreur) : le nombre total de
  placements de chaque image dans les pages de grille correspond
  exactement au nombre de points ("Stitches") déclaré par la légende pour
  chaque code DMC** — valeur différente pour chacune des 20 couleurs de ce
  fichier (de 332 à 2935), donc sans ambiguïté ici. Ce module
  utilise donc cette correspondance de comptage comme signal *primaire* de
  rapprochement image -> couleur, la couleur perceptuelle (restreinte aux
  codes de légende, comme le suggère le cahier des charges §8.5) servant de
  repli explicite pour les images qui ne pourraient pas être départagées
  ainsi (comptages en doublon, ou plus d'images que de lignes de légende) —
  toujours signalé comme moins fiable (cases marquées incertaines).

Module pur : aucune dépendance FastAPI/SQLAlchemy. Le point d'entrée
`detect_type_e` ne lève jamais d'exception — il renvoie `None` si le PDF ne
ressemble pas à un export type E (y compris pour un type A/B/C authentique,
cf. tests de non-régression)."""

from __future__ import annotations

import io
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf
from pdfplumber.page import Page
from PIL import Image

from app.dmc_catalog import nearest_dmc_among

# `app.schemas` ne dépend que de Pydantic — l'importer ici ne rompt pas la
# pureté du module (aucune dépendance FastAPI/SQLAlchemy, voir docstring).
from app.schemas import DetectionWarning
from app.type_a import SymbolGlyphLocation

Bbox = tuple[float, float, float, float]

# --------------------------------------------------------------------------
# Seuils — tous mesurés sur la fixture de référence, jamais devinés (voir la
# docstring du module pour le détail des mesures).
# --------------------------------------------------------------------------

# Fraction des placements d'image d'une page qui doivent partager la même
# taille (largeur, hauteur) pour que cette page soit candidate "grille" —
# mesuré : 1.0 sur les pages de grille (2-16), la légende (17) et la carte
# d'assemblage (18) ; seulement 0.698 sur la page de prévisualisation (1),
# qui empâte deux tailles d'image (48x48 et 64x64) pour un rendu
# photoréaliste. Grande marge entre les deux régimes observés.
_MIN_DOMINANT_SIZE_FRACTION = 0.98
# Écart relatif largeur/hauteur toléré pour la taille dominante d'une page —
# une case de grille de point de croix est toujours (quasi) carrée. Mesuré :
# 0.0 sur les pages de grille et la légende (64x64 exact) contre ~0.296 sur
# la carte d'assemblage (207x294 pt) — marge large entre les deux régimes.
_MAX_ASPECT_DEVIATION = 0.15
# Nombre total minimal de placements d'image (toutes pages candidates
# confondues) en dessous duquel ce n'est probablement pas une grille de
# points de croix mais une réutilisation incidente d'un petit nombre
# d'images (logo répété en en-tête, par exemple) — mesuré : 27 984
# placements sur les pages de grille de la fixture de référence, trois
# ordres de grandeur au-dessus.
_MIN_TOTAL_GRID_PLACEMENTS = 100
# Nombre minimal d'images distinctes pour parler de "catalogue" plutôt que
# d'une simple texture de fond répétée une fois. Mesuré : 20 sur la fixture
# de référence.
_MIN_DISTINCT_CATALOG_IMAGES = 2

# Bande de marge gauche (en points PDF) où les numéros d'axe de ligne
# (numéros de rangée, empilés verticalement) sont imprimés — mesuré à
# x0 ∈ {30.0, 32.6} sur toutes les pages de grille de la fixture de
# référence (le numéro d'en-tête de colonne le plus proche du bord gauche
# observé est à x0 = 67.8, largement au-dessus) : cette bande sépare sans
# ambiguïté "numéro de ligne empilé dans la marge gauche" de "numéro de
# colonne aligné avec le quadrillage", sans dépendre de la géométrie des
# images de cette page précise (contrairement à une fenêtre relative à
# l'étendue des images, qui échoue sur une page ne portant qu'une poignée
# de cases peintes — voir le rapport de tâche pour le diagnostic complet).
_LEFT_AXIS_BAND_MAX_X = 50.0
# Une ligne de texte candidate axe est composée uniquement de chiffres et
# d'espaces (« 10 20 30 40 50 », ou un numéro seul « 10 ») — un texte de
# légende ("DMC 168 Pewter very light...") ou de copyright ne matche jamais.
_AXIS_LINE_RE = re.compile(r"^\d+(?:\s+\d+)*$")
# Dimensions annoncées en clair par la légende, p. ex. « 217x206 Stitches »
# (répété une fois par jauge de toile proposée — 10/14/16/18 ct — toujours
# avec les mêmes valeurs, donc la première occurrence suffit).
_DECLARED_DIMENSIONS_RE = re.compile(r"(\d+)x(\d+)\s+Stitches")
# Légende : « DMC <code>\n<nom>\n<brins>\n<n>,<n> Skeins\n<points> » — un code
# alphabétique (ex. BLANC) partage parfois la même ligne que « DMC » sans
# retour à la ligne intermédiaire (observé sur cette fixture précise :
# « DMC BLANC\nWhite\n... » alors que toutes les autres lignes ont
# « DMC\n<code>\n... ») — `\s+` plutôt que `\n` absorbe les deux formes.
_LEGEND_ROW_RE = re.compile(r"DMC\s+(\S+)\n(.+?)\n(\d+)\n[\d.,]+\s*Skeins\n(\d+)")

# Au-delà de cette distance Lab, un rapprochement de repli par couleur
# (voir docstring du module) est jugé trop douteux pour être appliqué sans
# réserve supplémentaire — même barème que `app/type_bc.py`
# (`_UNCERTAIN_COLOR_DISTANCE`), la couleur DMC théorique n'étant de toute
# façon ici qu'un dernier recours, jamais la source première d'identité.
_UNCERTAIN_COLOR_DISTANCE = 12.0


@dataclass
class TypeEPaletteEntry:
    code: str
    """Code DMC tel qu'imprimé dans la légende — vide (`""`) pour une image
    du catalogue qui n'a pas pu être rapprochée d'une ligne de légende
    (« Symbole non reconnu », jamais une case fausse en silence)."""

    name: str
    rgb_hex: str
    """Couleur réellement extraite de l'image du catalogue (pixel dominant
    du fond, voir `_dominant_color`) — jamais la teinte théorique du
    catalogue DMC, dont la docstring du module montre qu'elle ne correspond
    pas fidèlement au rendu réel de cet éditeur (cahier des charges §8.4 :
    la couleur réellement extraite fait toujours foi pour l'affichage)."""

    symbol_key: str
    symbol_glyph: SymbolGlyphLocation | None = None
    match_method: str = "unmatched"
    """« count » (comptage exact, fiable), « color » (repli perceptuel,
    signalé incertain) ou « unmatched » (aucune ligne de légende
    disponible : entrée "Symbole non reconnu")."""


@dataclass
class TypeEResult:
    columns: int
    rows: int
    cells: list[int]
    """Longueur `columns * rows`, ligne par ligne, (0,0) en haut à gauche en
    premier. 0 = case vide, n = index 1-based dans `palette`."""
    palette: list[TypeEPaletteEntry]
    confidence: float
    uncertain_cells: list[int] = field(default_factory=list)
    """Index 0-based dans `cells` des cases dont l'identification est
    incertaine (repli couleur plutôt que comptage, ou image non reconnue) —
    jamais une case fausse laissée sans signalement."""
    warnings: list[DetectionWarning] = field(default_factory=list)
    """Jamais un texte déjà composé en français : un code de message et ses
    paramètres, traduits côté client (`import.warning.<code>`, audit des
    traductions du Lot 8)."""


def detect_type_e(pdf_path: Path) -> TypeEResult | None:
    """Renvoie `None` (sans jamais lever) si le PDF ne ressemble pas à un
    export type E — voir le module pour le détail de la détection."""
    try:
        with pdfplumber.open(pdf_path) as pdf, pymupdf.open(pdf_path) as doc:  # type: ignore[no-untyped-call]
            pages_pl = pdf.pages
            n_pages = min(len(pages_pl), doc.page_count)

            page_infos = [
                _analyze_page(pages_pl[i], doc[i]) for i in range(n_pages)
            ]
            candidates = [info for info in page_infos if _is_candidate_page(info)]
            if not candidates:
                return None

            fitted = [info for info in candidates if info.axis_fit is not None]
            if not fitted:
                return None

            catalog_size = _dominant_catalog_size(fitted)
            total_placements = sum(
                sum(1 for img in info.images if img.size == catalog_size) for info in fitted
            )
            if total_placements < _MIN_TOTAL_GRID_PLACEMENTS:
                return None

            warnings: list[DetectionWarning] = []
            confidence = 1.0

            skipped_pages = [info for info in candidates if info.axis_fit is None]
            if skipped_pages:
                warnings.append(
                    DetectionWarning(
                        code="type_e.pages_without_axis_numbers",
                        params={"count": len(skipped_pages)},
                    )
                )
                confidence -= min(0.3, 0.08 * len(skipped_pages))

            placements, digest_count, digest_sample, collisions = _place_images(
                fitted, catalog_size
            )
            if not placements:
                return None
            if collisions:
                warnings.append(
                    DetectionWarning(
                        code="type_e.overlapping_pages",
                        params={"count": collisions},
                    )
                )
                confidence -= min(0.2, 0.02 * collisions)

            if len(digest_count) < _MIN_DISTINCT_CATALOG_IMAGES:
                return None

            declared = _find_declared_dimensions(pages_pl)
            columns, rows, origin, dims_warning, dims_penalty = _resolve_dimensions(
                declared, placements
            )
            if dims_warning is not None:
                warnings.append(dims_warning)
                confidence -= dims_penalty
            if columns <= 0 or rows <= 0:
                return None

            legend_rows = _parse_legend(doc, n_pages)
            if not legend_rows:
                warnings.append(DetectionWarning(code="type_e.missing_legend"))
                confidence -= 0.5

            catalog = _build_catalog(doc, digest_sample, digest_count)
            palette, digest_to_index, match_warnings, match_penalty = _match_catalog_to_legend(
                catalog, legend_rows
            )
            warnings.extend(match_warnings)
            confidence -= match_penalty

            cells, uncertain_cells = _fill_cells(
                columns, rows, origin, placements, digest_to_index, palette
            )

            fraction_placed = sum(1 for v in cells if v != 0) / (columns * rows)
            if fraction_placed < 0.02:
                # Garde-fou : une "grille" qui ne couvre presque aucune case
                # n'est probablement pas une vraie détection exploitable —
                # mieux vaut refuser proprement que proposer une page quasi
                # vide comme point de départ (cahier des charges §10 :
                # jamais une impasse, mais jamais non plus une proposition
                # trompeuse).
                return None

            confidence = max(0.0, min(1.0, confidence))
            return TypeEResult(
                columns=columns,
                rows=rows,
                cells=cells,
                palette=palette,
                confidence=confidence,
                uncertain_cells=uncertain_cells,
                warnings=warnings,
            )
    except Exception:  # pragma: no cover - filet de sécurité, voir docstring
        return None


# --------------------------------------------------------------------------
# Analyse structurelle par page : identifier les pages de grille candidates
# --------------------------------------------------------------------------


@dataclass
class _ImagePlacement:
    digest: bytes
    size: tuple[int, int]
    bbox: Bbox
    xref: int


@dataclass
class _AxisFit:
    a_col: float
    b_col: float
    a_row: float
    b_row: float


@dataclass
class _PageInfo:
    index: int
    """0-based, index PDF."""
    images: list[_ImagePlacement]
    axis_fit: _AxisFit | None


def _analyze_page(page_pl: Page, page_mu: Any) -> _PageInfo:
    infos = page_mu.get_image_info(xrefs=True)
    images = [
        _ImagePlacement(
            digest=info["digest"],
            size=(info["width"], info["height"]),
            bbox=(
                float(info["bbox"][0]),
                float(info["bbox"][1]),
                float(info["bbox"][2]),
                float(info["bbox"][3]),
            ),
            xref=int(info["xref"]),
        )
        for info in infos
    ]
    axis_fit = _fit_axes(page_pl) if images else None
    return _PageInfo(index=page_pl.page_number - 1, images=images, axis_fit=axis_fit)


def _is_candidate_page(info: _PageInfo) -> bool:
    """Signal structurel seul (indépendant des numéros d'axe, voir
    `_fit_axes`) : une page dont l'écrasante majorité des placements
    d'image partagent la même taille (quasi) carrée — voir les constantes
    en tête de module pour les valeurs mesurées qui justifient les seuils."""
    if not info.images:
        return False
    sizes = Counter(img.size for img in info.images)
    dominant_size, dominant_count = sizes.most_common(1)[0]
    fraction = dominant_count / len(info.images)
    if fraction < _MIN_DOMINANT_SIZE_FRACTION:
        return False
    width, height = dominant_size
    if height == 0:
        return False
    deviation = abs(width - height) / max(width, height)
    return deviation <= _MAX_ASPECT_DEVIATION


def _dominant_catalog_size(fitted: list[_PageInfo]) -> tuple[int, int]:
    """Taille d'image dominante à travers toutes les pages retenues,
    pondérée par le nombre de placements — sert à ignorer une éventuelle
    image isolée d'une autre taille au sein d'une page par ailleurs
    conforme (défense en profondeur, non observée sur la fixture de
    référence mais pas coûteuse à vérifier)."""
    sizes: Counter[tuple[int, int]] = Counter()
    for info in fitted:
        for img in info.images:
            sizes[img.size] += 1
    return sizes.most_common(1)[0][0]


# --------------------------------------------------------------------------
# Numéros d'axe : position absolue de chaque page dans la mosaïque globale
# --------------------------------------------------------------------------


def _cluster_header_numbers(line_chars: list[dict[str, Any]]) -> list[tuple[float, int]]:
    """Une ligne d'en-tête porte plusieurs nombres espacés horizontalement
    (« 10 20 30 40 50 ») : les re-regrouper par grand écart de position
    plutôt que de se fier aux espaces du texte extrait (peu fiable d'un
    exporteur à l'autre, cf. `app/type_a.py::_chain_clusters`)."""
    clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for ch in line_chars:
        if current and float(ch["x0"]) - float(current[-1]["x1"]) > 3.0:
            clusters.append(current)
            current = []
        current.append(ch)
    if current:
        clusters.append(current)
    points: list[tuple[float, int]] = []
    for cluster in clusters:
        text = "".join(str(c["text"]) for c in cluster)
        if text.isdigit():
            points.append((float(cluster[0]["x0"]), int(text)))
    return points


def _fit_axes(page: Page) -> _AxisFit | None:
    """`_AxisFit` tel que le numéro de colonne absolu (1-based) d'un point à
    `x0` vaut `a_col + b_col*x0`, et de même pour la ligne via `top`. `None`
    si moins de 2 numéros d'axe exploitables sur un des deux axes.

    Contrairement à `app/type_a.py::_fit_axes`, la fenêtre de recherche des
    numéros n'est **jamais** dérivée de l'étendue des images de cette page
    précise : une page ne portant qu'une poignée de cases peintes (mesuré :
    une seule sur `RiverAndMountains-CS.pdf` page 6) a une étendue d'image
    bien trop étroite pour cadrer la règle d'axe complète, qui elle est
    toujours imprimée en entier quel que soit le contenu de la page (même
    régle de marge sur toutes les pages de grille de ce fichier). La
    position dans la marge suffit seule à distinguer un numéro de ligne
    (empilé à gauche, `x0 < _LEFT_AXIS_BAND_MAX_X`) d'un numéro de colonne
    (aligné avec le quadrillage, `x0` variable) — voir la constante pour les
    valeurs mesurées qui la justifient."""
    col_points: list[tuple[float, int]] = []
    row_points: list[tuple[float, int]] = []
    for line in page.extract_text_lines():
        text = str(line["text"]).strip()
        if not _AXIS_LINE_RE.match(text):
            continue
        chars = line.get("chars") or []
        if not chars:
            continue
        numbers = text.split()
        x0 = float(chars[0]["x0"])
        top = float(line["top"])
        if len(numbers) >= 2:
            col_points.extend(_cluster_header_numbers(chars))
        elif x0 < _LEFT_AXIS_BAND_MAX_X:
            row_points.append((top, int(numbers[0])))
        else:
            col_points.append((x0, int(numbers[0])))

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
    return _AxisFit(a_col=a_col, b_col=b_col, a_row=a_row, b_row=b_row)


# --------------------------------------------------------------------------
# Placement des images dans la grille absolue
# --------------------------------------------------------------------------


def _place_images(
    fitted: list[_PageInfo], catalog_size: tuple[int, int]
) -> tuple[dict[tuple[int, int], bytes], Counter[bytes], dict[bytes, tuple[int, Bbox]], int]:
    """Place chaque image de taille `catalog_size` dans des coordonnées
    absolues `(row1, col1)` **non normalisées** (l'origine n'est pas
    garantie être 0 — voir `_resolve_dimensions`, qui renormalise sur
    l'étendue réellement observée plutôt que de supposer que la numérotation
    d'axe démarre à 1 au bord du motif brodé)."""
    placements: dict[tuple[int, int], bytes] = {}
    digest_count: Counter[bytes] = Counter()
    digest_sample: dict[bytes, tuple[int, Bbox]] = {}
    collisions = 0

    for info in fitted:
        assert info.axis_fit is not None
        fit = info.axis_fit
        for img in info.images:
            if img.size != catalog_size:
                continue
            cx, cy = img.bbox[0], img.bbox[1]
            col1 = round(fit.a_col + fit.b_col * cx)
            row1 = round(fit.a_row + fit.b_row * cy)
            digest_count[img.digest] += 1
            if img.digest not in digest_sample:
                digest_sample[img.digest] = (info.index + 1, img.bbox)
            key = (row1, col1)
            if key in placements and placements[key] != img.digest:
                collisions += 1
            placements[key] = img.digest

    return placements, digest_count, digest_sample, collisions


def _find_declared_dimensions(pages: list[Page]) -> tuple[int, int] | None:
    """Dimensions annoncées en clair par la légende (p. ex. « 217x206
    Stitches ») — préférées à l'étendue déduite des images placées quand
    elles sont disponibles, comme pour le type A (§7.2 étape 6)."""
    for page in pages:
        match = _DECLARED_DIMENSIONS_RE.search(page.extract_text())
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None


def _resolve_dimensions(
    declared: tuple[int, int] | None,
    placements: dict[tuple[int, int], bytes],
) -> tuple[int, int, tuple[int, int], DetectionWarning | None, float]:
    """`(columns, rows, origin, warning, confidence_penalty)` — `origin`
    est le `(row1, col1)` absolu à soustraire de chaque placement pour
    obtenir des coordonnées 0-based.

    Contrairement à `app/type_a.py` (où le numéro de colonne 1 correspond
    toujours à la première case du motif), les numéros d'axe imprimés ici
    ne démarrent pas nécessairement à 1 au bord du motif réellement brodé
    (marge non numérotée à 1 observée sur la fixture de référence) :
    l'origine est donc toujours calée sur le placement le plus proche du
    bord (`min`), jamais sur la valeur 1 de la règle elle-même — mesuré :
    ça fait correspondre l'étendue obtenue exactement aux dimensions
    annoncées par la légende (217x206) sur la fixture de référence."""
    min_row1 = min(row1 for row1, _ in placements)
    min_col1 = min(col1 for _, col1 in placements)
    max_row1 = max(row1 for row1, _ in placements)
    max_col1 = max(col1 for _, col1 in placements)
    seen_columns = max_col1 - min_col1 + 1
    seen_rows = max_row1 - min_row1 + 1
    origin = (min_row1, min_col1)

    if declared is None:
        return (
            seen_columns,
            seen_rows,
            origin,
            DetectionWarning(code="type_e.dimensions_inferred"),
            0.05,
        )

    columns, rows = declared
    if columns != seen_columns or rows != seen_rows:
        warning = DetectionWarning(
            code="type_e.dimensions_mismatch",
            params={
                "declared_columns": columns,
                "declared_rows": rows,
                "seen_columns": seen_columns,
                "seen_rows": seen_rows,
            },
        )
        return columns, rows, origin, warning, 0.1
    return columns, rows, origin, None, 0.0


# --------------------------------------------------------------------------
# Légende texte (comptages DMC exacts par couleur)
# --------------------------------------------------------------------------


@dataclass
class _LegendRow:
    code: str
    name: str
    declared_count: int


def _parse_legend(doc: Any, n_pages: int) -> list[_LegendRow]:
    """Parsée depuis le texte brut PyMuPDF (`page.get_text()`), pas
    `pdfplumber` : chaque champ de la légende est sur sa propre ligne
    (« DMC\\n168\\nPewter very light\\n2\\n0,9 Skeins\\n1238\\n... »),
    reconstruite fidèlement par PyMuPDF sans étape de mise en page
    supplémentaire. Renvoie les lignes dans l'ordre imprimé (fait autorité
    pour l'ordre de palette exposé — voir `_match_catalog_to_legend`)."""
    for i in range(n_pages):
        text = doc[i].get_text()
        matches = _LEGEND_ROW_RE.findall(text)
        if not matches:
            continue
        return [
            _LegendRow(code=code, name=name.strip(), declared_count=int(count))
            for code, name, _strands, count in matches
        ]
    return []


# --------------------------------------------------------------------------
# Catalogue d'images : couleur dominante réelle par image
# --------------------------------------------------------------------------


@dataclass
class _CatalogImage:
    digest: bytes
    count: int
    rgb: tuple[float, float, float]
    """Composantes 0-1, couleur de fond dominante réellement rendue."""
    page_number: int
    bbox: Bbox


def _dominant_color(png_or_jpeg_bytes: bytes) -> tuple[float, float, float]:
    """Couleur de pixel la plus fréquente de l'image (mode statistique, pas
    la moyenne) : le fond de chaque icône du catalogue est un aplat uni
    (voir docstring du module) et couvre toujours la majorité des pixels —
    la moyenne, elle, est biaisée par l'encre du symbole dessiné par-dessus
    (mesuré : moyenne visiblement plus proche du gris neutre que le fond
    réel sur les icônes sombres/saturées de la fixture de référence, alors
    que le mode reste identique au pixel de coin, hors symbole)."""
    with Image.open(io.BytesIO(png_or_jpeg_bytes)) as source:
        image = source.convert("RGB")
        # `maxcolors` couvre large (bien au-delà du nombre de pixels d'une
        # icône 64x64) : `getcolors` renvoie `None`, jamais une liste
        # tronquée en silence, au-delà de cette borne.
        raw_colors = image.getcolors(maxcolors=image.width * image.height)
    if not raw_colors:  # pragma: no cover - défensif, non observé sur nos fixtures
        return 0.0, 0.0, 0.0
    # Les stubs PIL typent `getcolors` très large (image RGB, palette ou
    # niveaux de gris) ; `image` est garantie RGB ici (`.convert("RGB")`
    # ci-dessus) donc chaque pixel est bien un triplet à l'exécution.
    _count, dominant_rgb = max(raw_colors, key=lambda item: item[0])
    r, g, b = (int(v) for v in dominant_rgb)  # type: ignore[attr-defined]
    return r / 255, g / 255, b / 255


def _build_catalog(
    doc: Any, digest_sample: dict[bytes, tuple[int, Bbox]], digest_count: Counter[bytes]
) -> list[_CatalogImage]:
    catalog: list[_CatalogImage] = []
    for digest, (page_number, bbox) in digest_sample.items():
        xref = _xref_for_bbox(doc, page_number, bbox)
        if xref is None:
            continue
        try:
            raw = doc.extract_image(xref)
            rgb = _dominant_color(raw["image"])
        except Exception:  # pragma: no cover - image corrompue, chemin défensif
            continue
        catalog.append(
            _CatalogImage(
                digest=digest,
                count=digest_count[digest],
                rgb=rgb,
                page_number=page_number,
                bbox=bbox,
            )
        )
    return catalog


def _xref_for_bbox(doc: Any, page_number: int, bbox: Bbox) -> int | None:
    page = doc[page_number - 1]
    for info in page.get_image_info(xrefs=True):
        if (
            abs(float(info["bbox"][0]) - bbox[0]) < 0.5
            and abs(float(info["bbox"][1]) - bbox[1]) < 0.5
        ):
            return int(info["xref"])
    return None


# --------------------------------------------------------------------------
# Rapprochement catalogue -> légende (comptage exact, puis repli couleur)
# --------------------------------------------------------------------------


def _symbol_key(index0: int) -> str:
    """Identique à `app/type_a.py::_symbol_key` — petite fonction pure
    dupliquée volontairement plutôt qu'importée d'un module privé d'un
    autre connecteur, pour garder ce module autonome (même convention que
    `app/type_bc.py::_symbol_key`)."""
    n = index0
    letters = ""
    while True:
        n, rem = divmod(n, 26)
        letters = chr(65 + rem) + letters
        if n == 0:
            return letters
        n -= 1


def _rgb_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _match_catalog_to_legend(
    catalog: list[_CatalogImage], legend_rows: list[_LegendRow]
) -> tuple[list[TypeEPaletteEntry], dict[bytes, int], list[DetectionWarning], float]:
    """Associe chaque image du catalogue à une ligne de légende. Signal
    primaire : comptage exact (voir docstring du module — bien plus fiable
    ici que la couleur). Repli : plus proche voisin de couleur perceptuelle,
    restreint aux codes de légende encore non attribués (cahier des charges
    §8.5), pour les images que le comptage ne peut départager sans ambiguïté
    (comptages en doublon, ou plus d'images que de lignes de légende)."""
    warnings: list[DetectionWarning] = []
    penalty = 0.0

    count_to_codes: dict[int, list[str]] = defaultdict(list)
    for row in legend_rows:
        count_to_codes[row.declared_count].append(row.code)
    count_to_digests: dict[int, list[bytes]] = defaultdict(list)
    for img in catalog:
        count_to_digests[img.count].append(img.digest)

    matched_code: dict[bytes, str] = {}
    match_method: dict[bytes, str] = {}
    used_codes: set[str] = set()

    for count, codes in count_to_codes.items():
        digests = count_to_digests.get(count, [])
        if len(codes) == 1 and len(digests) == 1:
            matched_code[digests[0]] = codes[0]
            match_method[digests[0]] = "count"
            used_codes.add(codes[0])

    remaining_images = [img for img in catalog if img.digest not in matched_code]
    remaining_codes = {row.code for row in legend_rows if row.code not in used_codes}

    if remaining_images and remaining_codes:
        warnings.append(
            DetectionWarning(
                code="type_e.count_match_ambiguous",
                params={"count": len(remaining_images)},
            )
        )
        penalty += min(0.3, 0.05 * len(remaining_images))
        # Appariement glouton par distance Lab croissante, jamais un ordre
        # arbitraire — la paire la plus fiable est fixée en premier.
        pending_codes = set(remaining_codes)
        candidates: list[tuple[float, bytes, str]] = []
        for img in remaining_images:
            match = nearest_dmc_among(img.rgb, pending_codes)
            if match is not None:
                candidates.append((match.distance, img.digest, match.code))
        for _distance, digest, code in sorted(candidates, key=lambda c: c[0]):
            if digest in matched_code or code not in pending_codes:
                continue
            matched_code[digest] = code
            match_method[digest] = "color"
            pending_codes.discard(code)

    palette: list[TypeEPaletteEntry] = []
    digest_to_index: dict[bytes, int] = {}
    images_by_digest = {img.digest: img for img in catalog}

    for row in legend_rows:
        matched_digest = next((d for d, c in matched_code.items() if c == row.code), None)
        if matched_digest is None:
            continue
        img = images_by_digest[matched_digest]
        index = len(palette) + 1
        digest_to_index[matched_digest] = index
        palette.append(
            TypeEPaletteEntry(
                code=row.code,
                name=row.name,
                rgb_hex=_rgb_hex(img.rgb),
                symbol_key=_symbol_key(index - 1),
                symbol_glyph=SymbolGlyphLocation(page_number=img.page_number, bbox=img.bbox),
                match_method=match_method.get(matched_digest, "count"),
            )
        )

    unmatched = [img for img in catalog if img.digest not in digest_to_index]
    if unmatched:
        warnings.append(
            DetectionWarning(
                code="type_e.unmatched_catalog_images",
                params={"count": len(unmatched)},
            )
        )
        penalty += min(0.3, 0.05 * len(unmatched))
        for img in unmatched:
            index = len(palette) + 1
            digest_to_index[img.digest] = index
            palette.append(
                TypeEPaletteEntry(
                    code="",
                    name="Symbole non reconnu",
                    rgb_hex=_rgb_hex(img.rgb),
                    symbol_key=_symbol_key(index - 1),
                    symbol_glyph=SymbolGlyphLocation(page_number=img.page_number, bbox=img.bbox),
                    match_method="unmatched",
                )
            )

    return palette, digest_to_index, warnings, penalty


# --------------------------------------------------------------------------
# Assemblage final
# --------------------------------------------------------------------------


def _fill_cells(
    columns: int,
    rows: int,
    origin: tuple[int, int],
    placements: dict[tuple[int, int], bytes],
    digest_to_index: dict[bytes, int],
    palette: list[TypeEPaletteEntry],
) -> tuple[list[int], list[int]]:
    origin_row, origin_col = origin
    cells = [0] * (columns * rows)
    uncertain_positions: set[int] = set()
    uncertain_methods = {"color", "unmatched"}
    # Index 1-based (comme `cells`) -> méthode de rapprochement de l'entrée
    # de palette correspondante, pour marquer les cases incertaines sans
    # dépendre de l'ordre d'itération d'un dict (jamais garanti stable ici).
    index_to_method = {i + 1: entry.match_method for i, entry in enumerate(palette)}

    for (row1, col1), digest in placements.items():
        row0 = row1 - origin_row
        col0 = col1 - origin_col
        if row0 < 0 or col0 < 0 or row0 >= rows or col0 >= columns:
            continue
        index = digest_to_index.get(digest)
        if index is None:
            continue
        flat = row0 * columns + col0
        cells[flat] = index
        if index_to_method.get(index) in uncertain_methods:
            uncertain_positions.add(flat)

    return cells, sorted(uncertain_positions)
