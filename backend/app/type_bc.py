"""Détection automatique des types B et C (grilles vectorielles DMC-style,
cahier des charges §4.3, §4.4 et §8.4-8.5, Lot 5).

Contrairement au type A (`app/type_a.py`), il n'y a **aucune police de
symboles embarquée** ici : la couleur de chaque case vient du remplissage
d'un rectangle vectoriel, et le symbole (quand il existe) d'un petit tracé
vectoriel (lignes/courbes/fragments de rectangles) — jamais du texte.

Rien n'est codé en dur pour une fixture précise. En particulier, **la
relation entre les pages d'un même PDF n'est jamais supposée fixe** (leçon
du cas piège `summer-flight-dmc`, cahier des charges §4.3) : ce module
mesure, pour chaque page candidate, la densité de tracés vectoriels par
rapport aux rectangles de couleur avant de décider si une page de symboles
séparée doit être superposée, ou si la page couleur porte déjà elle-même
les symboles (constaté aussi bien sur `summer-flight-dmc` que sur
`winter-wreath-dmc` — les deux se comportent pareil malgré ce qu'on
pourrait attendre d'un simple coup d'œil au cahier des charges : seule la
mesure réelle sur le fichier fait foi, jamais une hypothèse de structure
fixe, cf. `CLAUDE.md`).

Module pur : aucune dépendance FastAPI/SQLAlchemy. Le point d'entrée
`detect_type_bc` ne lève jamais d'exception — il renvoie `None` si le PDF ne
ressemble pas à un type B/C (y compris quand il s'agit en réalité d'un type
A, ou d'un type E à base d'images bitmap réutilisées comme
`river-and-mountains-laserarts`, cahier des charges §4.3)."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pdfplumber
import pymupdf
from pdfplumber.page import Page
from PIL import Image

from app.dmc_catalog import lab_distance, nearest_dmc, rgb_to_lab
from app.grid_lines import is_grid_ruling

# `app.schemas` ne dépend que de Pydantic — l'importer ici ne rompt pas la
# pureté du module (aucune dépendance FastAPI/SQLAlchemy, voir docstring).
from app.schemas import DetectionWarning
from app.type_a import SymbolGlyphLocation, detect_type_a

# Voir `app/type_a.py` pour le rationnel de ce typage : pdfplumber représente
# chaque objet positionné (rectangle, ligne, courbe) comme un dictionnaire
# hétérogène, sans TypedDict public à réutiliser.
Obj = dict[str, Any]
Color = tuple[float, ...]
Bbox = tuple[float, float, float, float]

# --------------------------------------------------------------------------
# Seuils — tous ajustables, aucun n'est spécifique à une fixture précise.
# --------------------------------------------------------------------------

# Nombre minimal de rectangles de la taille d'une case pour qu'une page soit
# candidate « grille couleur » (en dessous, ce n'est probablement qu'une
# légende ou une page de garde avec quelques pastilles de couleur).
_MIN_CELLSIZED_RECTS = 150
# Tolérance de taille pour qu'un rectangle rempli soit considéré comme « une
# case » plutôt qu'un fragment de trait de symbole (bien plus petit) ou une
# grosse pastille de légende (bien plus grand).
_CELL_SIZE_MIN_RATIO = 0.6
_CELL_SIZE_MAX_RATIO = 1.35
# Ratio largeur/hauteur de pas acceptable pour une grille de point de croix
# (cases proches du carré, jamais un tableau de texte).
_PITCH_RATIO_MIN = 0.5
_PITCH_RATIO_MAX = 2.0
# Un connecteur type B/C authentique observé (§4.1, §4.3) est 100 %
# vectoriel — aucune image bitmap sur ses pages de grille. `river-and-
# mountains-laserarts` (type E, catalogue d'icônes réutilisées) porte lui
# aussi un habillage de rectangles de fond par case sur toutes ses pages de
# grille (gabarit d'éditeur commun), ce qui le rendrait autrement éligible
# comme page couleur B/C — seule la présence d'au moins une image sur la
# page suffit à l'exclure : aucune tolérance, quitte à rater un éventuel
# logo isolé (repli sûr sur le mode assisté plutôt qu'un faux positif
# silencieux, règle impérative du `pdf-extraction-specialist`).
_MAX_IMAGES_ON_COLOR_PAGE = 0
# Densité (tracés vectoriels / cases coloriées) au-delà de laquelle la page
# couleur porte déjà elle-même les symboles (mesuré : ~0.02-0.04 sur les
# pages « propres » winter-wreath/botanical/cucurbit contre ~0.2-0.5 sur les
# pages déjà combinées winter-wreath et summer-flight — voir docstring du
# module). Marge large entre les deux régimes observés.
_SYMBOLS_ALREADY_PRESENT_DENSITY = 0.1
# Densité minimale sur une page candidate « symboles » pour l'accepter comme
# calque de superposition plutôt qu'une page annexe sans rapport.
_MIN_SYMBOL_PAGE_DENSITY = 0.15
# Un unique remplissage ne peut raisonnablement pas couvrir une fraction
# aussi énorme d'une grille multicolore : au-delà, c'est un calque de fond
# (ombrage alterné, aplat de fond de page) plutôt qu'un vrai fil à broder —
# voir `_exclude_background_color`.
_BACKGROUND_DOMINANCE_RATIO = 0.3
# Fusion de couleurs quasi identiques (bruit d'arrondi CMJN/RVB) en une
# seule entrée de palette — bien en dessous de l'écart perceptible le plus
# faible observé entre deux teintes réellement distinctes dans nos fixtures
# de référence (~4.4 en Lab).
_COLOR_MERGE_LAB_EPSILON = 2.5
# Au-delà de cette distance Lab, le rapprochement DMC le plus proche est
# jugé douteux et signalé (cahier des charges §8.5).
_UNCERTAIN_COLOR_DISTANCE = 12.0
# Correctif « cases incertaines » du Lot 5 (suite) : une première piste
# (desserrer un seuil de différence de bits sur l'ancien bitmap grossier
# 6x6, construit à partir des quelques points de tracé vectoriel de chaque
# case, de 3 à 4-6) avait été abandonnée après vérification visuelle sur
# `botanical-citrus-dmc` — à 4 bits d'écart, elle fusionnait à tort un
# symbole « + » et un symbole « flèche vers le haut ». Un second diagnostic,
# plus poussé, a montré pourquoi aucun seuil global sur ce bitmap ne
# pouvait marcher : sur `cucurbit-dmc`, des cases portant des symboles
# réellement différents (un rond, une flèche, une croix — confirmé en
# rendant les cases via `render_symbol_svg`) pouvaient tomber sur le
# *même* bitmap 6x6 (aliasing pur, faute de résolution avec seulement 4 à 6
# points de tracé source par case) — un problème d'identité dès le
# regroupement exact initial, pas seulement de tolérance de fusion.
#
# `_build_symbol_signatures` construit donc désormais l'empreinte de chaque
# case (`_raster_fingerprint`) à partir du rendu raster réel de la page de
# symboles (page rendue une seule fois par fichier via PyMuPDF, cf.
# `_render_symbol_page_gray`) plutôt que des points de tracé vectoriels —
# ~256 pixels par case contre ~4-6 points, un risque d'aliasing bien plus
# faible. `_merge_near_duplicate_signatures` compare ensuite ces empreintes
# avec une tolérance de petit décalage de quelques pixels (le bruit de
# redessin observé est bien une translation, pas un changement de forme) et
# un garde-fou supplémentaire sur l'aire d'encre (une vraie différence de
# forme, même à faible distance de recouvrement post-décalage, change
# presque toujours la quantité d'encre — utile par exemple contre un
# symbole qui serait un sous-ensemble strict d'un autre). Seuils mesurés sur
# les 4 fixtures DMC (voir `backend/tests/test_type_bc.py`) avant d'être
# fixés, jamais devinés — voir le détail sous chaque seuil ci-dessous.
#
# Troisième diagnostic (régression `winter-wreath-dmc`, 22 % -> 35 % de
# cases incertaines après le passage au rendu raster) : rendu visuel
# (`render_symbol_svg`) de plusieurs cases d'une même couleur canonique
# (vert olive) réparties sur toute la grille, pas seulement près de
# l'origine — deux cases portant le même symbole (une barre diagonale)
# tombaient dans deux regroupements différents. La différence n'était pas
# un fragment de la case voisine (hypothèse initiale) mais **un trait de
# quadrillage majeur** (une ligne « décade », tracée tous les 10 cases,
# bien plus épaisse que le quadrillage mineur — mesuré directement sur les
# `lines` vectorielles de la page : ~0.13-0.27 pt pour le quadrillage
# mineur contre jusqu'à 1.07-1.34 pt pour les lignes décade, soit jusqu'à
# ~6 px de large une fois rendu au zoom utilisé ici). Avec l'ancienne marge
# de 4 px, les cases adjacentes à une ligne décade gardaient un fragment de
# cette ligne épaisse dans leur recadrage — et seulement elles, ce qui
# explique pourquoi seule une fraction des cases d'une même couleur
# basculait dans un second regroupement (confirmé : les positions de grille
# des cases mal groupées se concentrent near des colonnes/lignes multiples
# de 10, pas uniformément sur la grille comme l'aurait produit une imprécision
# de recalage systématique).
#
# `river-and-mountains-laserarts` mis à part (type E, jamais éligible ici),
# les pages symboles de `botanical-citrus-dmc` et `cucurbit-dmc` portent
# elles aussi des lignes de ~6 px de large au même zoom, mais en bien plus
# petit nombre (quelques dizaines, probablement le rectangle de bordure et
# quelques repères, pas un quadrillage décade complet superposé à toute la
# grille comme sur `winter-wreath-dmc`) — ce qui explique qu'elles n'aient
# jamais montré ce symptôme avant que `winter-wreath-dmc` ne soit mesuré
# spécifiquement.
#
# `_RASTER_CORE_MARGIN_PX` a donc été élargie de 4 à 5 px et mesurée sur les
# 4 fixtures DMC de référence (jamais seulement sur celle qui régressait,
# cf. `CLAUDE.md`) : le taux de cases incertaines de `winter-wreath-dmc`
# tombe à 17.7 % (611/3460), sous son taux d'avant même le passage au rendu
# raster (~22 %), tandis que `botanical-citrus-dmc` (0.8 %) et
# `cucurbit-dmc` (3.7 %) restent identiques à leur valeur mesurée à 4 px —
# voir `backend/tests/test_type_bc.py`. Un balayage plus large (5 à 10 px)
# montre un comportement non monotone au-delà de 6 px (la résolution utile
# commence à se dégrader : `cucurbit-dmc` remonte à 17.7 % d'incertaines à
# 8 px) — 5 px est la valeur la plus basse qui élimine la contamination
# mesurée sur `winter-wreath-dmc`, jamais desserrée au-delà de ce qui est
# nécessaire. Le reliquat de cases incertaines sur `winter-wreath-dmc` après
# ce correctif (611 cases) vient très majoritairement (592/611, mesuré) de
# deux teintes sans correspondance DMC proche dans le catalogue communautaire
# partiel (§8.5) — une incertitude réelle et déjà attendue, indépendante de
# la reconnaissance de forme, jamais quelque chose que ce correctif doit ou
# peut faire disparaître.
_RASTER_CELL_PX = 24
"""Résolution du rendu de la page de symboles : pixels par case (zoom non
uniforme si le pas n'est pas parfaitement carré, cf. `_render_symbol_page_gray`).
Assez fin pour distinguer des formes de quelques pixels de large, sans
gonfler inutilement le temps de rendu d'une page entière."""
_RASTER_CORE_MARGIN_PX = 5
"""Marge retirée de chaque côté de la case avant comparaison — exclut le
quadrillage imprimé, qui longe exactement la frontière de case et
fausserait sinon toute comparaison de recouvrement (mesuré : sans cette
marge, la quasi-totalité des cases d'un même fichier se ressemblent à
cause du quadrillage commun, pas du symbole).

Élargie de 4 à 5 px (Lot 5, troisième correctif « cases incertaines »,
régression `winter-wreath-dmc`) : à 4 px, les cases adjacentes à une ligne
de quadrillage « décade » (tracée tous les 10 cases, bien plus épaisse que
le quadrillage mineur — jusqu'à ~6 px de large une fois rendue) gardaient
un fragment de cette ligne dans leur recadrage, ce qui faisait dériver leur
empreinte raster et cassait le regroupement de symboles pourtant
identiques. Voir le commentaire détaillé au-dessus de `_RASTER_CELL_PX`
pour le diagnostic complet et les mesures sur les 4 fixtures DMC."""
_RASTER_SHIFT_TOLERANCE_PX = 4
"""Décalage maximal (en pixels, dans chaque direction) toléré pour aligner
deux cases avant de les comparer — absorbe le bruit de sous-position
observé (redessin légèrement décalé du même symbole), mesuré suffisant sur
les 4 fixtures DMC de référence sans avoir besoin d'être élargi davantage
(le desserrer ne réduit plus la distance mesurée sur les cas de test au-delà
de ce seuil, cf. rapport de tâche)."""
_RASTER_INK_DELTA = 40
"""Un pixel est considéré comme de l'encre s'il est au moins ce nombre de
niveaux de gris plus sombre que la couleur dominante (le fond) de la case —
jamais un seuil de luminosité absolu : la couleur de fond d'une case type
B/C n'est pas toujours blanche (page couleur+symboles combinée, cas
`winter-wreath-dmc`), un seuil absolu classerait alors tout l'aplat de
couleur comme « encre » et ferait strictement tout fusionner (mesuré :
52 fusions erronées sur `winter-wreath-dmc` avec un seuil absolu, contre 3
avec ce seuil relatif à la couleur dominante locale)."""
_RASTER_MERGE_MAX_JACCARD = 0.40
"""Distance de Jaccard (1 - aire d'intersection / aire d'union, meilleur
décalage toléré) en dessous de laquelle deux cases sont regroupées. Mesuré
sur `cucurbit-dmc` (positions de grille (24,29)/(22,31)/(23,29)/(21,31), le
même rond redessiné) : distance maximale 0.369 entre les 4 cases. Mesuré sur
`botanical-citrus-dmc` (« + » contre flèche) : 0.475. Seuil placé à mi-chemin
avec une marge confortable des deux côtés — jamais resserré au point de
casser au moindre écart mineur, jamais desserré au point d'engloutir la
paire « + »/flèche."""
_RASTER_MERGE_MIN_AREA_RATIO = 0.75
"""Ratio (aire d'encre la plus petite / la plus grande) en dessous duquel
deux cases ne sont jamais regroupées, même à faible distance de Jaccard —
garde-fou indépendant contre un vrai symbole qui serait un sous-ensemble
strict d'un autre (un trait simple contenu dans un symbole plus riche, par
exemple) : ce cas de figure peut faire chuter la distance de Jaccard sans
que les deux formes soient réellement identiques, la distance de Jaccard
seule ne suffit donc pas toujours. Sur les 4 fixtures DMC de référence, les
regroupements réellement effectués ont tous un ratio d'aire d'au moins
0.938 (paire « + »/flèche de `botanical-citrus-dmc`, qui elle reste
distincte grâce à la distance de Jaccard, pas à ce garde-fou) à 0.943 (rond
redessiné de `cucurbit-dmc`, qui lui fusionne) — ce seuil n'est donc jamais
le facteur déterminant sur ces quatre fichiers précis, mais reste une
protection mesurée comme peu coûteuse (elle ne bloque aucun regroupement
correct observé) contre un cas non couvert par ces fixtures."""
# Nombre de regroupements distincts / nombre de cases coloriées au-delà
# duquel la reconnaissance de forme est jugée trop peu fiable pour tout le
# fichier (repli en type B). Mesuré avec l'empreinte raster (voir plus haut) :
# 0.006-0.014 sur les trois fixtures DMC à reconnaissance fiable contre
# 0.290 sur le cas piège `summer-flight-dmc` (illustration richement
# nuancée, §4.3) — grande marge entre les deux régimes, mais nettement plus
# bas qu'avec l'ancien bitmap vectoriel (où le même cas piège atteignait
# ~0.9) : l'empreinte raster, beaucoup moins bruitée, regroupe aussi mieux
# les fragments de l'illustration nuancée de `summer-flight-dmc` sans pour
# autant les rendre fiables (194 regroupements distincts sur 668 cases
# coloriées reste bien plus qu'un catalogue de symboles plausible) — ce
# seuil a donc dû être resserré en conséquence, pas seulement recopié.
_MAX_SIGNATURE_FRAGMENTATION = 0.1


@dataclass
class TypeBCPaletteEntry:
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_glyph: SymbolGlyphLocation | None = None


@dataclass
class TypeBCResult:
    columns: int
    rows: int
    cells: list[int]
    """Longueur `columns * rows`, ligne par ligne, (0,0) en haut à gauche en
    premier. 0 = case vide, n = index 1-based dans `palette`."""
    palette: list[TypeBCPaletteEntry]
    grid_type: Literal["B", "C"]
    confidence: float
    uncertain_cells: list[int] = field(default_factory=list)
    """Index 0-based dans `cells` des cases dont la couleur et/ou le symbole
    est incertain — jamais une case fausse laissée sans signalement (règle
    impérative du `pdf-extraction-specialist`)."""
    warnings: list[DetectionWarning] = field(default_factory=list)
    """Jamais un texte déjà composé en français : un code de message et ses
    paramètres, traduits côté client (`import.warning.<code>`, audit des
    traductions du Lot 8)."""


def detect_type_bc(pdf_path: Path) -> TypeBCResult | None:
    """Renvoie `None` (sans jamais lever) si le PDF ne ressemble pas à un
    export type B/C — voir le module pour le détail de la détection."""
    try:
        # Un export type A authentique (police de symboles embarquée, testé
        # sur les six fixtures de référence) ne doit jamais être également
        # proposé comme B/C — éviter tout double résultat concurrent pour un
        # même fichier (§4.4 : la typologie est une classification, pas un
        # empilement de suppositions).
        if detect_type_a(pdf_path) is not None:
            return None

        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages
            infos = [_analyze_page(page) for page in pages]

            color_page = _select_color_page(infos)
            if color_page is None:
                return None
            # `_select_color_page` ne renvoie que des pages où ces trois
            # valeurs sont déjà garanties non `None` (filtre sur
            # `len(cellsized_rects) >= _MIN_CELLSIZED_RECTS`, qui implique un
            # pas détecté, et `border is not None`) — assertions pour que
            # mypy le sache aussi, jamais pour masquer un cas réel.
            assert color_page.border is not None
            assert color_page.pitch_x is not None
            assert color_page.pitch_y is not None
            color_border = color_page.border
            color_pitch_x = color_page.pitch_x
            color_pitch_y = color_page.pitch_y

            symbol_page, grid_type, page_warning = _select_symbol_page(infos, color_page)
            warnings: list[DetectionWarning] = [page_warning] if page_warning is not None else []
            confidence = 1.0

            grid = _GridGeometry(
                columns=round((color_border[2] - color_border[0]) / color_pitch_x),
                rows=round((color_border[3] - color_border[1]) / color_pitch_y),
                origin_x=color_border[0],
                origin_top=color_border[1],
                pitch_x=color_pitch_x,
                pitch_y=color_pitch_y,
            )
            if grid.columns <= 0 or grid.rows <= 0:
                return None
            if color_page.border_is_fallback:
                warnings.append(DetectionWarning(code="type_bc.border_inferred"))
                confidence -= 0.15

            raw_cell_colors = _build_color_grid(color_page, grid)
            raw_cell_colors, background_warning = _exclude_background_color(
                raw_cell_colors, grid.columns * grid.rows
            )
            if background_warning is not None:
                warnings.append(background_warning)

            if not raw_cell_colors:
                return None

            canonical_of, canonical_colors = _cluster_colors(raw_cell_colors)
            cell_color_id: dict[tuple[int, int], int] = {
                pos: canonical_of[color] for pos, color in raw_cell_colors.items()
            }

            cell_signature: dict[tuple[int, int], int] = {}
            representative_bbox: dict[int, Bbox] = {}
            symbol_page_number: int | None = None
            if grid_type == "C" and symbol_page is not None:
                symbol_page_number = symbol_page.index + 1
                # Réutiliser telle quelle la géométrie de la page couleur
                # quand la page de symboles est la même page (cas
                # `winter-wreath-dmc`/`summer-flight-dmc`, §4.3) : recalculer
                # un pas à partir d'une bordure arrondie y introduirait un
                # écart infime mais systématique avec la grille déjà utilisée
                # pour extraire la couleur, qui fragmente artificiellement
                # les signatures de forme (mesuré : x4 le nombre de
                # regroupements obtenus). Le recalage n'a de sens que pour
                # une page réellement distincte.
                sym_grid = grid if symbol_page is color_page else _symbol_grid_for(
                    symbol_page, grid
                )
                cell_signature, representative_bbox = _build_symbol_signatures(
                    symbol_page, sym_grid, set(cell_color_id), pdf_path
                )
                if not any(cell_signature.values()):
                    # Densité mesurée suffisante mais aucune forme exploitable
                    # regroupée par case (recalage hors tolérance, par
                    # exemple) : ne jamais prétendre une reconnaissance de
                    # symbole qu'on n'a pas réellement — repli honnête en B.
                    grid_type = "B"
                    warnings.append(DetectionWarning(code="type_bc.symbol_page_unusable"))
                    confidence -= 0.2
                elif cell_signature:
                    n_clusters = len(set(cell_signature.values()))
                    n_colored = len(cell_signature)
                    if n_clusters / n_colored > _MAX_SIGNATURE_FRAGMENTATION:
                        # Beaucoup plus de signatures distinctes que
                        # plausible pour un catalogue de symboles réel
                        # (observé : illustration très richement nuancée sur
                        # `summer-flight-dmc`, où chaque case porte en plus
                        # du symbole plusieurs fragments d'ombrage qui font
                        # dériver sa signature) — la reconnaissance de forme
                        # n'est pas assez fiable pour l'ensemble du fichier :
                        # repli honnête en B plutôt qu'une « fausse » palette
                        # de plusieurs centaines d'entrées inutilisable
                        # (cahier des charges §4.4 : type B quand la
                        # confiance de reconnaissance de forme est trop
                        # basse pour l'ensemble du fichier).
                        grid_type = "B"
                        cell_signature = {}
                        warnings.append(
                            DetectionWarning(code="type_bc.symbol_recognition_unreliable")
                        )
                        confidence -= 0.2

            (
                palette,
                cells,
                uncertain_cells,
                palette_warnings,
                palette_penalty,
            ) = _build_palette_and_cells(
                grid=grid,
                cell_color_id=cell_color_id,
                canonical_colors=canonical_colors,
                cell_signature=cell_signature,
                representative_bbox=representative_bbox,
                grid_type=grid_type,
                symbol_page_number=symbol_page_number,
            )
            warnings.extend(palette_warnings)
            confidence -= palette_penalty

            confidence = max(0.0, min(1.0, confidence))
            return TypeBCResult(
                columns=grid.columns,
                rows=grid.rows,
                cells=cells,
                palette=palette,
                grid_type=grid_type,
                confidence=confidence,
                uncertain_cells=uncertain_cells,
                warnings=warnings,
            )
    except Exception:  # pragma: no cover - filet de sécurité, voir docstring
        # Ne jamais lever : un PDF inattendu doit simplement ne pas être
        # reconnu comme type B/C plutôt que faire échouer tout l'import
        # (règle impérative « ne jamais bloquer un import »).
        return None


# --------------------------------------------------------------------------
# Analyse structurelle par page
# --------------------------------------------------------------------------


@dataclass
class _PageInfo:
    index: int
    page: Page
    filled_rects: list[Obj]
    cellsized_rects: list[Obj]
    curves: list[Obj]
    lines: list[Obj]
    n_images: int
    pitch_x: float | None
    pitch_y: float | None
    border: Bbox | None
    border_is_fallback: bool


def _analyze_page(page: Page) -> _PageInfo:
    filled_rects = [r for r in page.rects if r.get("fill")]
    pitch = _estimate_pitch_from_rects(filled_rects)
    pitch_x, pitch_y = pitch if pitch is not None else (None, None)
    cellsized_rects: list[Obj] = []
    if pitch_x is not None and pitch_y is not None:
        min_w, max_w = _CELL_SIZE_MIN_RATIO * pitch_x, _CELL_SIZE_MAX_RATIO * pitch_x
        min_h, max_h = _CELL_SIZE_MIN_RATIO * pitch_y, _CELL_SIZE_MAX_RATIO * pitch_y
        cellsized_rects = [
            r
            for r in filled_rects
            if min_w <= (r["x1"] - r["x0"]) <= max_w and min_h <= (r["bottom"] - r["top"]) <= max_h
        ]
    # La bordure est détectée indépendamment du pas de case : une page de
    # symboles pure (fragments de traits, pas de grands aplats de couleur)
    # n'a pas de pas de case fiable dérivable de ses rectangles (ses
    # rectangles remplis, quand il y en a, sont de petits fragments de
    # trait, pas des cases), mais porte quand même le même cadre de grille
    # que la page couleur — indispensable pour la sélectionner comme page de
    # symboles à superposer (`_select_symbol_page`).
    border = _detect_border(page)
    border_is_fallback = False
    if border is None and len(cellsized_rects) >= _MIN_CELLSIZED_RECTS:
        xs = [r["x0"] for r in cellsized_rects] + [r["x1"] for r in cellsized_rects]
        ys = [r["top"] for r in cellsized_rects] + [r["bottom"] for r in cellsized_rects]
        border = (min(xs), min(ys), max(xs), max(ys))
        border_is_fallback = True
    return _PageInfo(
        index=page.page_number - 1,
        page=page,
        filled_rects=filled_rects,
        cellsized_rects=cellsized_rects,
        curves=list(page.curves),
        lines=list(page.lines),
        n_images=len(page.images),
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        border=border,
        border_is_fallback=border_is_fallback,
    )


def _estimate_pitch(distinct_sorted: list[float]) -> float | None:
    if len(distinct_sorted) < 2:
        return None
    diffs = [b - a for a, b in zip(distinct_sorted, distinct_sorted[1:], strict=False)]
    plausible = [d for d in diffs if d > 0.5]
    if not plausible:
        return None
    return statistics.median(plausible)


def _estimate_pitch_from_rects(filled_rects: list[Obj]) -> tuple[float, float] | None:
    if len(filled_rects) < _MIN_CELLSIZED_RECTS:
        return None
    widths = sorted(r["x1"] - r["x0"] for r in filled_rects)
    heights = sorted(r["bottom"] - r["top"] for r in filled_rects)
    pitch_x = statistics.median(widths)
    pitch_y = statistics.median(heights)
    if pitch_x <= 0 or pitch_y <= 0:
        return None
    if not (_PITCH_RATIO_MIN <= pitch_x / pitch_y <= _PITCH_RATIO_MAX):
        return None
    return pitch_x, pitch_y


# --------------------------------------------------------------------------
# Détection de la bordure de grille (étendue totale, pas seulement la zone
# brodée : une grille imprimée laisse presque toujours des cases de fond non
# brodées, dont l'étendue des rectangles de couleur seule sous-estimerait la
# taille réelle — voir docstring du module).
# --------------------------------------------------------------------------


def _segment_coverage(
    segments: list[tuple[float, float]], span_min: float, span_max: float
) -> float:
    span = span_max - span_min
    if span <= 0:
        return 0.0
    ivs = sorted(segments)
    covered = 0.0
    cur_a: float | None = None
    cur_b = 0.0
    for a, b in ivs:
        if cur_a is None:
            cur_a, cur_b = a, b
            continue
        if a <= cur_b + 1.5:
            cur_b = max(cur_b, b)
        else:
            covered += cur_b - cur_a
            cur_a, cur_b = a, b
    if cur_a is not None:
        covered += cur_b - cur_a
    return covered / span


def _detect_border(page: Page, tol: float = 1.5) -> Bbox | None:
    """Bordure externe du cadre de grille imprimé : soit un unique
    rectangle non rempli mais tracé (`stroke`), soit quatre côtés de même
    épaisseur de trait formant un rectangle fermé parmi les `lines` de la
    page. Les deux représentations sont observées selon le fichier (voir
    tests) — jamais supposées interchangeables sans vérification
    géométrique (une simple co-occurrence de 2 lignes de bord de page, par
    exemple des flèches de repère, n'est pas une bordure)."""
    page_area = page.width * page.height
    best: tuple[float, Bbox] | None = None

    for r in page.rects:
        if r.get("stroke") and not r.get("fill"):
            bbox = (r["x0"], r["top"], r["x1"], r["bottom"])
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if 0.05 * page_area < area < 0.97 * page_area and (best is None or area > best[0]):
                best = (area, bbox)

    groups: dict[float, list[Obj]] = defaultdict(list)
    for line in page.lines:
        lw = round(float(line.get("linewidth") or 0.0), 2)
        groups[lw].append(line)

    for lines in groups.values():
        if len(lines) < 4:
            continue
        horiz = [line for line in lines if abs(line["top"] - line["bottom"]) < 0.5]
        vert = [line for line in lines if abs(line["x0"] - line["x1"]) < 0.5]
        if not horiz or not vert:
            continue
        min_x = min(min(line["x0"], line["x1"]) for line in lines)
        max_x = max(max(line["x0"], line["x1"]) for line in lines)
        min_y = min(min(line["top"], line["bottom"]) for line in lines)
        max_y = max(max(line["top"], line["bottom"]) for line in lines)
        top_segs = [
            (min(line["x0"], line["x1"]), max(line["x0"], line["x1"]))
            for line in horiz
            if abs(line["top"] - min_y) < tol
        ]
        bot_segs = [
            (min(line["x0"], line["x1"]), max(line["x0"], line["x1"]))
            for line in horiz
            if abs(line["top"] - max_y) < tol
        ]
        left_segs = [
            (min(line["top"], line["bottom"]), max(line["top"], line["bottom"]))
            for line in vert
            if abs(line["x0"] - min_x) < tol
        ]
        right_segs = [
            (min(line["top"], line["bottom"]), max(line["top"], line["bottom"]))
            for line in vert
            if abs(line["x0"] - max_x) < tol
        ]
        coverage = min(
            _segment_coverage(top_segs, min_x, max_x),
            _segment_coverage(bot_segs, min_x, max_x),
            _segment_coverage(left_segs, min_y, max_y),
            _segment_coverage(right_segs, min_y, max_y),
        )
        if coverage < 0.7:
            continue
        bbox = (min_x, min_y, max_x, max_y)
        area = (max_x - min_x) * (max_y - min_y)
        if 0.05 * page_area < area < 0.97 * page_area and (best is None or area > best[0]):
            best = (area, bbox)

    return best[1] if best is not None else None


# --------------------------------------------------------------------------
# Sélection de la page couleur et, si nécessaire, de la page symboles
# --------------------------------------------------------------------------


def _select_color_page(infos: list[_PageInfo]) -> _PageInfo | None:
    """La page couleur candidate : celle qui pave le plus grand nombre de
    cases avec des rectangles remplis de la taille d'une case, hors pages
    dominées par des images bitmap (type E, jamais une vraie grille B/C —
    voir docstring du module)."""
    candidates = [
        info
        for info in infos
        if len(info.cellsized_rects) >= _MIN_CELLSIZED_RECTS
        and info.border is not None
        and info.n_images <= _MAX_IMAGES_ON_COLOR_PAGE
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda info: len(info.cellsized_rects))


def _page_density(info: _PageInfo) -> float:
    """Tracés vectoriels (courbes) rapportés au nombre de cases coloriées —
    voir les seuils `_SYMBOLS_ALREADY_PRESENT_DENSITY` /
    `_MIN_SYMBOL_PAGE_DENSITY` en tête de module pour l'usage. Les courbes
    seules (pas les lignes) sont le signal le plus discriminant mesuré sur
    les quatre fixtures de référence : elles portent presque exclusivement
    les parties arrondies des symboles, quasi absentes d'une page couleur
    propre, alors que les lignes incluent aussi le quadrillage décimal
    (présent en quantité comparable sur toutes les pages, coloriées ou
    non — un signal beaucoup moins discriminant)."""
    n_cells = max(1, len(info.cellsized_rects))
    return len(info.curves) / n_cells


def _select_symbol_page(
    infos: list[_PageInfo], color_page: _PageInfo
) -> tuple[_PageInfo | None, Literal["B", "C"], DetectionWarning | None]:
    """Décide, par mesure et jamais par position de page supposée fixe
    (§4.3 : cas piège `summer-flight-dmc`), si la page couleur porte déjà
    elle-même les symboles, si une page voisine doit être superposée, ou si
    aucun symbole exploitable n'est disponible (repli type B)."""
    own_density = _page_density(color_page)
    if own_density >= _SYMBOLS_ALREADY_PRESENT_DENSITY:
        return color_page, "C", None

    border = color_page.border
    assert border is not None
    color_width = border[2] - border[0]
    color_height = border[3] - border[1]

    best: _PageInfo | None = None
    best_density = 0.0
    for info in infos:
        if info.index == color_page.index or info.border is None:
            continue
        b = info.border
        width, height = b[2] - b[0], b[3] - b[1]
        if abs(width - color_width) > 0.1 * color_width:
            continue
        if abs(height - color_height) > 0.1 * color_height:
            continue
        density = len(info.curves) / max(1, len(color_page.cellsized_rects))
        if density > best_density:
            best_density = density
            best = info

    if best is not None and best_density >= _MIN_SYMBOL_PAGE_DENSITY:
        return best, "C", None

    return None, "B", DetectionWarning(code="type_bc.no_symbol_page")


# --------------------------------------------------------------------------
# Géométrie de grille et extraction de la couleur par case
# --------------------------------------------------------------------------


@dataclass
class _GridGeometry:
    columns: int
    rows: int
    origin_x: float
    origin_top: float
    pitch_x: float
    pitch_y: float

    def cell_of(self, cx: float, cy: float) -> tuple[int, int]:
        col0 = int((cx - self.origin_x) / self.pitch_x)
        row0 = int((cy - self.origin_top) / self.pitch_y)
        return row0, col0

    def cell_origin(self, row0: int, col0: int) -> tuple[float, float]:
        return (
            self.origin_x + col0 * self.pitch_x,
            self.origin_top + row0 * self.pitch_y,
        )


def _normalize_color(raw: Any) -> Color:
    """`non_stroking_color` peut être un scalaire (niveau de gris), un
    triplet RVB ou un quadruplet CMJN selon l'espace colorimétrique du PDF
    (cahier des charges §8.4) — toujours ramené à un tuple arrondi."""
    if isinstance(raw, int | float):
        value = round(float(raw), 4)
        return (value, value, value)
    if isinstance(raw, list | tuple):
        return tuple(round(float(v), 4) for v in raw)
    return (0.0, 0.0, 0.0)


@lru_cache(maxsize=4096)
def _cmyk_to_rgb_via_mupdf(cmyk: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Convertit du CMJN vers du RVB via la conversion colorimétrique de
    PyMuPDF (déjà une dépendance du projet, §7.2 du cahier des charges) au
    lieu de la formule naïve `R=(1-C)(1-K)` recommandée en repli par la
    spécification PDF. Mesuré (Lot 5, correctif cases incertaines) : sur les
    grilles vectorielles DMC, une bonne partie des remplissages sont en CMJN,
    et la formule naïve sursature nettement les teintes obtenues par mélange
    cyan+jaune (verts en particulier) — jusqu'à ~25 points de distance Lab
    d'écart avec la couleur réellement rendue pour une même teinte, largement
    au-dessus de `_UNCERTAIN_COLOR_DISTANCE`, ce qui faisait basculer à tort
    la quasi-totalité des cases d'une couleur en incertaines au rapprochement
    DMC (confirmé en comparant les deux formules à la couleur réellement
    rendue par PyMuPDF sur `botanical-citrus-dmc` et `cucurbit-dmc`). Mis en
    cache : le nombre de teintes CMJN distinctes par fichier est de l'ordre
    de la dizaine, très inférieur au nombre de cases."""
    c, m, y, k = (max(0.0, min(1.0, v)) for v in cmyk)
    samples = bytes([round(c * 255), round(m * 255), round(y * 255), round(k * 255)])
    pixmap_cmyk = pymupdf.Pixmap(pymupdf.csCMYK, 1, 1, samples, False)  # type: ignore[no-untyped-call]
    pixmap_rgb = pymupdf.Pixmap(pymupdf.csRGB, pixmap_cmyk)  # type: ignore[no-untyped-call]
    r, g, b = pixmap_rgb.pixel(0, 0)[:3]  # type: ignore[no-untyped-call]
    return r / 255, g / 255, b / 255


def _color_to_rgb(color: Color) -> tuple[float, float, float]:
    """Convertit une couleur normalisée (RVB, CMJN ou gris) en RVB 0-1."""
    if len(color) == 3:
        return color[0], color[1], color[2]
    if len(color) == 4:
        c, m, y, k = color
        return _cmyk_to_rgb_via_mupdf((c, m, y, k))
    if len(color) == 1:
        v = color[0]
        return v, v, v
    return 0.0, 0.0, 0.0


def _build_color_grid(
    color_page: _PageInfo, grid: _GridGeometry
) -> dict[tuple[int, int], Color]:
    """Couleur par case, dans l'ordre de dessin du PDF (`page.rects` est déjà
    dans l'ordre du flux de contenu) : quand plusieurs rectangles se
    superposent exactement à la même case (observé : un aplat de fond sous
    le remplissage réel de la case, cf. `_exclude_background_color`), le
    dernier dessiné est visuellement celui qui compte — jamais le plus
    petit en surface (heuristique du type A, invalide ici car les deux
    rectangles font ici la même taille)."""
    border = color_page.border
    assert border is not None
    margin_x = grid.pitch_x * 0.5
    margin_y = grid.pitch_y * 0.5
    cells: dict[tuple[int, int], Color] = {}
    for rect in color_page.cellsized_rects:
        cx = (rect["x0"] + rect["x1"]) / 2
        cy = (rect["top"] + rect["bottom"]) / 2
        if not (
            border[0] - margin_x <= cx <= border[2] + margin_x
            and border[1] - margin_y <= cy <= border[3] + margin_y
        ):
            continue
        row0, col0 = grid.cell_of(cx, cy)
        if row0 < 0 or col0 < 0 or row0 >= grid.rows or col0 >= grid.columns:
            continue
        cells[(row0, col0)] = _normalize_color(rect["non_stroking_color"])
    return cells


def _exclude_background_color(
    cells: dict[tuple[int, int], Color], total_grid_cells: int
) -> tuple[dict[tuple[int, int], Color], DetectionWarning | None]:
    """Exclut une couleur qui domine une fraction implausible de la grille
    entière (observé : un aplat de fond neutre appliqué sous chaque case,
    coloriée ou non, sur `summer-flight-dmc` — jamais un vrai fil à broder
    de motif multicolore ne couvre une telle proportion). Détection par
    fréquence, jamais par une valeur de couleur codée en dur : ne se
    déclenche sur aucune des trois autres fixtures de référence, où aucune
    couleur ne dépasse ~5 % des cases."""
    if not cells:
        return cells, None
    counts = Counter(cells.values())
    dominant_color, dominant_count = counts.most_common(1)[0]
    if dominant_count < _BACKGROUND_DOMINANCE_RATIO * total_grid_cells:
        return cells, None
    filtered = {pos: c for pos, c in cells.items() if c != dominant_color}
    warning = DetectionWarning(
        code="type_bc.background_color_excluded",
        params={"cells": dominant_count},
    )
    return filtered, warning


# --------------------------------------------------------------------------
# Fusion des couleurs quasi identiques (bruit d'arrondi CMJN/RVB)
# --------------------------------------------------------------------------


def _cluster_colors(
    cells: dict[tuple[int, int], Color]
) -> tuple[dict[Color, int], list[tuple[float, float, float]]]:
    """Regroupe les couleurs brutes distinctes par proximité Lab
    (`_COLOR_MERGE_LAB_EPSILON`) en couleurs canoniques. Renvoie la table de
    correspondance couleur brute -> index canonique et la liste des
    couleurs canoniques (moyenne RVB des couleurs regroupées, pondérée par
    leur nombre de cases)."""
    raw_counts = Counter(cells.values())
    raw_colors = sorted(raw_counts, key=lambda c: -raw_counts[c])
    raw_rgb = {c: _color_to_rgb(c) for c in raw_colors}
    raw_lab = {c: rgb_to_lab(raw_rgb[c]) for c in raw_colors}

    canonical_rgb: list[tuple[float, float, float]] = []
    canonical_weight: list[int] = []
    canonical_of: dict[Color, int] = {}

    for raw in raw_colors:  # du plus fréquent au moins fréquent
        best_index: int | None = None
        best_distance = float("inf")
        for index, rgb in enumerate(canonical_rgb):
            distance = lab_distance(raw_lab[raw], rgb_to_lab(rgb))
            if distance < best_distance:
                best_distance = distance
                best_index = index
        if best_index is not None and best_distance <= _COLOR_MERGE_LAB_EPSILON:
            weight = raw_counts[raw]
            prev_weight = canonical_weight[best_index]
            prev_rgb = canonical_rgb[best_index]
            new_weight = prev_weight + weight
            blended = raw_rgb[raw]
            canonical_rgb[best_index] = (
                (prev_rgb[0] * prev_weight + blended[0] * weight) / new_weight,
                (prev_rgb[1] * prev_weight + blended[1] * weight) / new_weight,
                (prev_rgb[2] * prev_weight + blended[2] * weight) / new_weight,
            )
            canonical_weight[best_index] = new_weight
            canonical_of[raw] = best_index
        else:
            canonical_of[raw] = len(canonical_rgb)
            canonical_rgb.append(raw_rgb[raw])
            canonical_weight.append(raw_counts[raw])

    return canonical_of, canonical_rgb


# --------------------------------------------------------------------------
# Reconnaissance de symboles vectoriels (page symboles, superposée ou non)
# --------------------------------------------------------------------------


def _symbol_grid_for(symbol_page: _PageInfo, grid: _GridGeometry) -> _GridGeometry:
    """Géométrie de grille à utiliser pour lire les tracés de `symbol_page` :
    même nombre de colonnes/lignes que la page couleur (jugé plus fiable,
    dérivé des rectangles de case plutôt que des tracés), mais un pas et une
    origine recalés sur la bordure propre de `symbol_page` plutôt que
    réutilisés tels quels. Nécessaire en pratique : les deux pages d'un même
    PDF ne partagent ni exactement la même origine ni exactement la même
    échelle (écarts de quelques points mesurés sur les fixtures de
    référence, qui s'accumulent sur la largeur de la grille sans ce
    recalage) — c'est le « réglage fin de recalage » prévu par le cahier des
    charges §7.2 étape 5."""
    if symbol_page.border is None:
        return grid
    b = symbol_page.border
    width, height = b[2] - b[0], b[3] - b[1]
    return _GridGeometry(
        columns=grid.columns,
        rows=grid.rows,
        origin_x=b[0],
        origin_top=b[1],
        pitch_x=width / grid.columns,
        pitch_y=height / grid.rows,
    )


def _is_grid_ruling(line: Obj, grid: _GridGeometry, tol_ratio: float = 0.15) -> bool:
    """Un trait du quadrillage décimal (ou de sa réglure mineure) est
    aligné exactement sur une frontière de case, contrairement à un trait de
    symbole qui se trouve à l'intérieur d'une case. Filtré uniquement pour
    les `lines` (axe-alignées par construction) — jamais pour les courbes,
    qui ne sont jamais utilisées pour tracer un quadrillage rectiligne.

    La règle elle-même vit dans `app/grid_lines.py` depuis le Lot 9 (le
    type A en a besoin pour ses points arrière) ; l'appel ci-dessous lui
    passe la bbox, exactement comme la version d'origine du Lot 5, et sans
    critère de longueur — le comportement type B/C est inchangé."""
    return is_grid_ruling(
        float(line["x0"]),
        float(line["top"]),
        float(line["x1"]),
        float(line["bottom"]),
        origin_x=grid.origin_x,
        origin_top=grid.origin_top,
        pitch_x=grid.pitch_x,
        pitch_y=grid.pitch_y,
        tol_ratio=tol_ratio,
    )


def _build_symbol_signatures(
    symbol_page: _PageInfo,
    sym_grid: _GridGeometry,
    colored_cells: set[tuple[int, int]],
    pdf_path: Path,
) -> tuple[dict[tuple[int, int], int], dict[int, Bbox]]:
    """Signature de forme par case : une empreinte issue du rendu raster
    réel de la case (voir `_raster_fingerprint`), jamais d'un bitmap dérivé
    des points de tracé vectoriels — permet de regrouper les cases portant
    le même symbole sans connaître à l'avance le catalogue de symboles
    possibles (règle impérative : jamais de liste de symboles figée en dur,
    cf. Lot 4).

    Une première version de ce module dérivait cette empreinte d'un bitmap
    grossier (grille 6x6) construit directement à partir des quelques points
    de tracé vectoriels de la case. Diagnostic (Lot 5, second correctif
    « cases incertaines ») : sur `cucurbit-dmc`, ce bitmap grossier
    *aliasait* parfois des symboles réellement différents (confirmé
    visuellement via `render_symbol_svg` : un rond, une flèche et une croix
    partageaient le même bitmap 6x6, faute de résolution suffisante avec
    aussi peu de points source) — un problème d'*identité* dès le
    regroupement exact initial, en amont de toute tolérance de fusion.
    Utiliser directement le rendu raster (bien plus riche : ~256 pixels
    contre ~4-6 points vectoriels par case) élimine ce risque d'aliasing à
    la source.

    Les tracés vectoriels (rectangles/courbes/lignes hors quadrillage)
    restent utilisés, mais seulement pour deux choses indépendantes de la
    forme exacte : détecter *si* une case porte un symbole (case vide vs
    case marquée) et fournir la bbox réelle affichée par l'assistant
    (`SymbolGlyphLocation`, coordonnées PDF précises, plus fidèles qu'un
    recadrage dérivé du rendu raster). Index spatial par case avant tout
    traitement (comme `_build_rect_index` de `app/type_a.py`) : indispensable
    ici aussi — `summer-flight-dmc` porte plus de 10 000 rectangles et 2 000
    tracés par page, une comparaison naïve tracé x case serait bien trop
    lente.

    `sym_grid` est la géométrie déjà recalée sur `symbol_page` (voir
    `_symbol_grid_for` et son site d'appel) — jamais recalculée ici, pour
    garder un seul endroit qui décide entre réutiliser la grille couleur
    telle quelle ou recaler sur la bordure propre de la page symboles."""
    cellsized_ids = {id(r) for r in symbol_page.cellsized_rects}

    buckets: dict[tuple[int, int], list[Obj]] = defaultdict(list)
    for rect in symbol_page.filled_rects:
        if id(rect) in cellsized_ids:
            continue
        _bucket_object(rect, sym_grid, buckets)
    for curve in symbol_page.curves:
        _bucket_object(curve, sym_grid, buckets)
    for line in symbol_page.lines:
        if _is_grid_ruling(line, sym_grid):
            continue
        _bucket_object(line, sym_grid, buckets)

    # Bbox vectorielle des cases marquées (coordonnées PDF, pour
    # `SymbolGlyphLocation`) — sert aussi de test de présence (case vide vs
    # marquée), indépendant de l'identité exacte de la forme.
    vector_bbox: dict[tuple[int, int], Bbox] = {}
    for pos in colored_cells:
        objs = buckets.get(pos)
        if not objs:
            continue
        xs: list[float] = []
        ys: list[float] = []
        for obj in objs:
            for px, py in obj.get("pts") or ():
                xs.append(px)
                ys.append(py)
        if xs and ys:
            vector_bbox[pos] = (min(xs), min(ys), max(xs), max(ys))

    if not vector_bbox:
        return {pos: 0 for pos in colored_cells}, {}

    gray, origin_px, origin_py = _render_symbol_page_gray(pdf_path, symbol_page.index + 1, sym_grid)

    signatures: dict[tuple[int, int], int] = {}
    representative_bbox: dict[int, Bbox] = {}
    representative_pos: dict[int, tuple[int, int]] = {}
    for pos in colored_cells:
        if pos not in vector_bbox:
            signatures[pos] = 0
            continue
        fingerprint = _raster_fingerprint(gray, origin_px, origin_py, pos)
        signatures[pos] = fingerprint
        if fingerprint != 0 and fingerprint not in representative_bbox:
            representative_bbox[fingerprint] = vector_bbox[pos]
            representative_pos[fingerprint] = pos

    return _merge_near_duplicate_signatures(
        signatures, representative_bbox, representative_pos, gray, origin_px, origin_py
    )


def _render_symbol_page_gray(
    pdf_path: Path, page_number: int, sym_grid: _GridGeometry
) -> tuple[Image.Image, int, int]:
    """Rend toute la page de symboles en niveaux de gris, une seule fois par
    fichier, à une résolution où chaque case de `sym_grid` occupe exactement
    `_RASTER_CELL_PX` x `_RASTER_CELL_PX` pixels (zoom non uniforme si le pas
    n'est pas parfaitement carré). Rendre la page entière plutôt qu'un
    fragment par case est indispensable pour rester dans le budget de temps
    (cahier des charges §10) : `_merge_near_duplicate_signatures` ne compare
    ensuite que les quelques dizaines de bitmaps *distincts* observés dans le
    fichier, jamais chacune des cases coloriées (qui peuvent se compter en
    milliers)."""
    zoom_x = _RASTER_CELL_PX / sym_grid.pitch_x
    zoom_y = _RASTER_CELL_PX / sym_grid.pitch_y
    matrix = pymupdf.Matrix(zoom_x, zoom_y)  # type: ignore[no-untyped-call]
    with pymupdf.open(pdf_path) as doc:  # type: ignore[no-untyped-call]
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).convert("L")
    origin_px = round(sym_grid.origin_x * zoom_x)
    origin_py = round(sym_grid.origin_top * zoom_y)
    return image, origin_px, origin_py


def _cell_ink_grid(
    gray: Image.Image,
    origin_px: int,
    origin_py: int,
    pos: tuple[int, int],
    pad: int,
) -> list[list[int]]:
    """Grille d'encre binaire (0/1) pour la case `pos`, recadrée avec une
    marge de `_RASTER_CORE_MARGIN_PX` (exclut le quadrillage imprimé, cf.
    `_RASTER_CORE_MARGIN_PX`) et un supplément `pad` de chaque côté pour
    permettre la recherche de décalage (`_best_shifted_jaccard_distance`).
    Les pixels hors de l'image (case près du bord de page) valent blanc,
    jamais noir : `Image.crop` remplirait sinon la zone hors bornes en noir,
    ce qui ferait passer un simple bord de page pour de l'encre.

    Seuil d'encre relatif à la couleur dominante *de cette case précise*
    (`_RASTER_INK_DELTA`), jamais un seuil de luminosité absolu — voir sa
    docstring pour la raison (page couleur+symboles combinée où le fond
    n'est pas blanc, cas `winter-wreath-dmc`)."""
    row0, col0 = pos
    width, height = gray.size
    x0 = origin_px + col0 * _RASTER_CELL_PX + _RASTER_CORE_MARGIN_PX - pad
    y0 = origin_py + row0 * _RASTER_CELL_PX + _RASTER_CORE_MARGIN_PX - pad
    size = (_RASTER_CELL_PX - 2 * _RASTER_CORE_MARGIN_PX) + 2 * pad
    pixels = gray.load()
    assert pixels is not None
    values: list[list[int]] = [[255] * size for _ in range(size)]
    for y in range(size):
        py = y0 + y
        if not (0 <= py < height):
            continue
        for x in range(size):
            px = x0 + x
            if 0 <= px < width:
                # Image en mode "L" (niveaux de gris) : la valeur est
                # toujours un entier malgré le type large des stubs PIL
                # (partagé avec les tuples RVB des autres modes).
                values[y][x] = int(pixels[px, py])  # type: ignore[arg-type]
    background = Counter(v for row in values for v in row).most_common(1)[0][0]
    return [[1 if background - v >= _RASTER_INK_DELTA else 0 for v in row] for row in values]


def _raster_fingerprint(
    gray: Image.Image, origin_px: int, origin_py: int, pos: tuple[int, int]
) -> int:
    """Empreinte entière (un bit par pixel d'encre) du rendu raster réel
    d'une case, sans marge de décalage — clé de regroupement exact utilisée
    par `_build_symbol_signatures` (deux cases dont le rendu est identique
    au pixel près obtiennent la même empreinte). Bien plus fin que l'ancien
    bitmap 6x6 dérivé des points de tracé (voir la docstring de
    `_build_symbol_signatures`), donc beaucoup moins sujet à l'aliasing de
    deux symboles réellement différents sur la même empreinte."""
    grid = _cell_ink_grid(gray, origin_px, origin_py, pos, 0)
    fingerprint = 0
    bit = 0
    for row in grid:
        for value in row:
            if value:
                fingerprint |= 1 << bit
            bit += 1
    return fingerprint


def _best_shifted_jaccard_distance(
    core: list[list[int]], padded: list[list[int]], max_shift: int
) -> float:
    """Distance de Jaccard entre `core` (case de référence, sans marge
    supplémentaire) et `padded` (même case comparée, avec `max_shift` pixels
    de marge de chaque côté), en essayant tous les petits décalages dans
    cette marge et en gardant le meilleur (le plus petit) — absorbe le bruit
    de sous-position d'un symbole redessiné (voir `_RASTER_SHIFT_TOLERANCE_PX`).
    `core` et `padded` sont déjà des grilles 0/1 (`_cell_ink_grid`)."""
    h, w = len(core), len(core[0])
    best = 1.0
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            intersection = 0
            union = 0
            for y in range(h):
                padded_row = padded[y + max_shift + dy]
                core_row = core[y]
                for x in range(w):
                    a = core_row[x]
                    b = padded_row[x + max_shift + dx]
                    if a or b:
                        union += 1
                        if a and b:
                            intersection += 1
            distance = 0.0 if union == 0 else 1 - intersection / union
            if distance < best:
                best = distance
    return best


def _merge_near_duplicate_signatures(
    signatures: dict[tuple[int, int], int],
    representative_bbox: dict[int, Bbox],
    representative_pos: dict[int, tuple[int, int]],
    gray: Image.Image,
    origin_px: int,
    origin_py: int,
) -> tuple[dict[tuple[int, int], int], dict[int, Bbox]]:
    """Fusionne les empreintes qui représentent le même symbole redessiné à
    un léger décalage près (bruit de sous-position), en comparant le rendu
    raster réel des cases avec une petite tolérance de décalage — voir la
    docstring de `_RASTER_MERGE_MAX_JACCARD` et consorts pour le diagnostic
    complet qui a mené à ces seuils. Fusion gloutonne, de l'empreinte la plus
    fréquente à la moins fréquente, jamais entre deux empreintes déjà
    fréquentes l'une et l'autre (signe de deux symboles réellement distincts
    plutôt que d'une variante bruitée d'un seul). `gray`/`origin_px`/
    `origin_py` sont le rendu déjà produit par `_build_symbol_signatures`
    (`_render_symbol_page_gray`) — jamais recalculés ici, un rendu de page
    entière par fichier suffit (cahier des charges §10)."""
    counts = Counter(signatures.values())
    # L'empreinte 0 (aucune encre détectée) n'est jamais fusionnée avec un
    # symbole réel : un vrai symbole absent est une information en soi, pas
    # un bruit d'un symbole présent.
    ordered = sorted((b for b in counts if b != 0), key=lambda b: -counts[b])
    remap: dict[int, int] = {0: 0}
    if not ordered:
        return dict(signatures), {}

    core_of = {
        b: _cell_ink_grid(gray, origin_px, origin_py, representative_pos[b], 0) for b in ordered
    }
    padded_of = {
        b: _cell_ink_grid(
            gray, origin_px, origin_py, representative_pos[b], _RASTER_SHIFT_TOLERANCE_PX
        )
        for b in ordered
    }
    area_of = {b: sum(sum(row) for row in core_of[b]) for b in ordered}

    canonical: list[int] = []
    for bitmap in ordered:
        merged_into: int | None = None
        for existing in canonical:
            if counts[existing] < counts[bitmap]:
                continue
            area_a, area_b = area_of[bitmap], area_of[existing]
            if area_a == 0 or area_b == 0:
                continue
            area_ratio = min(area_a, area_b) / max(area_a, area_b)
            if area_ratio < _RASTER_MERGE_MIN_AREA_RATIO:
                continue
            distance = _best_shifted_jaccard_distance(
                core_of[bitmap], padded_of[existing], _RASTER_SHIFT_TOLERANCE_PX
            )
            if distance <= _RASTER_MERGE_MAX_JACCARD:
                merged_into = existing
                break
        if merged_into is None:
            canonical.append(bitmap)
            remap[bitmap] = bitmap
        else:
            remap[bitmap] = merged_into

    merged_signatures = {pos: remap[bitmap] for pos, bitmap in signatures.items()}
    merged_bbox = {
        canon: representative_bbox[canon] for canon in canonical if canon in representative_bbox
    }
    return merged_signatures, merged_bbox


def _bucket_object(
    obj: Obj, grid: _GridGeometry, buckets: dict[tuple[int, int], list[Obj]]
) -> None:
    cx = (obj["x0"] + obj["x1"]) / 2
    cy = (obj["top"] + obj["bottom"]) / 2
    row0, col0 = grid.cell_of(cx, cy)
    if 0 <= row0 < grid.rows and 0 <= col0 < grid.columns:
        buckets[(row0, col0)].append(obj)


# --------------------------------------------------------------------------
# Assemblage final : palette, cases, incertitudes
# --------------------------------------------------------------------------


def _symbol_key(index0: int) -> str:
    """Identique à `app/type_a.py::_symbol_key` (clé courte façon « colonnes
    de tableur ») — petite fonction pure dupliquée volontairement plutôt
    qu'importée d'un module privé d'un autre connecteur, pour garder ce
    module autonome."""
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


def _build_palette_and_cells(
    grid: _GridGeometry,
    cell_color_id: dict[tuple[int, int], int],
    canonical_colors: list[tuple[float, float, float]],
    cell_signature: dict[tuple[int, int], int],
    representative_bbox: dict[int, Bbox],
    grid_type: Literal["B", "C"],
    symbol_page_number: int | None,
) -> tuple[list[TypeBCPaletteEntry], list[int], list[int], list[DetectionWarning], float]:
    warnings: list[DetectionWarning] = []
    cells = [0] * (grid.columns * grid.rows)

    combo_counts: Counter[tuple[int, int]] = Counter()
    color_clusters: dict[int, Counter[int]] = defaultdict(Counter)
    for pos, color_id in cell_color_id.items():
        cluster_id = cell_signature.get(pos, 0) if grid_type == "C" else 0
        combo_counts[(color_id, cluster_id)] += 1
        color_clusters[color_id][cluster_id] += 1

    palette: list[TypeBCPaletteEntry] = []
    combo_index: dict[tuple[int, int], int] = {}
    dmc_distance: dict[int, float] = {}
    uncertain_color_codes: set[str] = set()

    for (color_id, cluster_id), _count in sorted(
        combo_counts.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        index = len(palette) + 1
        combo_index[(color_id, cluster_id)] = index
        rgb = canonical_colors[color_id]
        match = nearest_dmc(rgb)
        dmc_distance[index] = match.distance
        if match.distance > _UNCERTAIN_COLOR_DISTANCE:
            uncertain_color_codes.add(match.code)
        symbol_glyph = None
        if grid_type == "C" and cluster_id != 0 and symbol_page_number is not None:
            bbox = representative_bbox.get(cluster_id)
            if bbox is not None:
                symbol_glyph = SymbolGlyphLocation(page_number=symbol_page_number, bbox=bbox)
        palette.append(
            TypeBCPaletteEntry(
                code=match.code,
                name=match.name,
                # La couleur réellement extraite du PDF fait foi pour
                # l'affichage (§1 : « couleur exacte par case ») — bien plus
                # fiable ici que la teinte théorique du catalogue DMC, qui ne
                # sert qu'au rapprochement du code (`nearest_dmc`), jamais
                # utilisée seule pour décider d'une couleur (§8.5 : le texte
                # de légende, quand il existe, prime toujours sur la
                # couleur — hors périmètre de ce module, qui n'a que la
                # couleur).
                rgb_hex=_rgb_hex(rgb),
                symbol_key=_symbol_key(index - 1),
                symbol_glyph=symbol_glyph,
            )
        )

    uncertain_positions: set[tuple[int, int]] = set()
    for pos, color_id in cell_color_id.items():
        cluster_id = cell_signature.get(pos, 0) if grid_type == "C" else 0
        index = combo_index[(color_id, cluster_id)]
        row0, col0 = pos
        cells[row0 * grid.columns + col0] = index

        if combo_counts[(color_id, cluster_id)] == 1:
            uncertain_positions.add(pos)
        if dmc_distance[index] > _UNCERTAIN_COLOR_DISTANCE:
            uncertain_positions.add(pos)
        if grid_type == "C":
            counter = color_clusters[color_id]
            if len(counter) > 1:
                dominant_cluster, dominant_count = counter.most_common(1)[0]
                dominant_ratio = dominant_count / sum(counter.values())
                if dominant_ratio < 0.6 or cluster_id != dominant_cluster:
                    uncertain_positions.add(pos)

    total_colored = len(cell_color_id)
    fraction_uncertain = len(uncertain_positions) / total_colored if total_colored else 0.0
    penalty = min(0.4, fraction_uncertain)

    if uncertain_color_codes:
        warnings.append(
            DetectionWarning(
                code="type_bc.uncertain_dmc_match",
                params={"count": len(uncertain_color_codes)},
            )
        )
    if uncertain_positions:
        warnings.append(
            DetectionWarning(
                code="type_bc.uncertain_cells",
                params={"count": len(uncertain_positions)},
            )
        )

    uncertain_cells = sorted(row0 * grid.columns + col0 for row0, col0 in uncertain_positions)
    return palette, cells, uncertain_cells, warnings, penalty
