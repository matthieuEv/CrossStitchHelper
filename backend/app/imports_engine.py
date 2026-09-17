"""Moteur manuel de l'assistant d'import (Lot 2).

Aucune détection automatique ici — c'est ce qui distingue le Lot 2 des
Lots 4 à 7 (cahier des charges §8, roadmap). Ce module ne fait que :
rendre une page (PDF ou image) en raster pour l'aperçu de cadrage, et
assembler une grille à partir des zones peintes manuellement par
l'utilisateur (« remplissage des couleurs par zone », roadmap Lot 2).
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import pymupdf
from PIL import Image

MAX_PREVIEW_DIMENSION = 2000
"""Borne raisonnable pour un aperçu : assez net pour cadrer à la main, sans
transmettre une image à pleine résolution scanner sur une connexion mobile."""


class UnsupportedFileError(ValueError):
    """Le fichier déposé n'est ni un PDF ni une image prise en charge."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_page_count(path: Path) -> int:
    # pymupdf n'est pas typé (pas de py.typed) : `int(...)` documente et
    # vérifie le type réel à la frontière plutôt que de renvoyer `Any`.
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        return int(doc.page_count)


def render_pdf_page(
    path: Path, page_number: int, max_dimension: int = MAX_PREVIEW_DIMENSION
) -> bytes:
    """Rend la page `page_number` (1-based) d'un PDF en PNG raster."""
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Page {page_number} hors limites (1..{doc.page_count})")
        page = doc[page_number - 1]
        # Le zoom est calculé pour que la plus grande dimension de page
        # n'excède pas `max_dimension`, sans jamais agrandir une petite page.
        zoom = min(max_dimension / page.rect.width, max_dimension / page.rect.height, 3.0)
        matrix = pymupdf.Matrix(zoom, zoom)  # type: ignore[no-untyped-call]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return bytes(pixmap.tobytes("png"))


_SYMBOL_GLYPH_PADDING = 0.14
"""Marge autour du glyphe, en fraction de son plus grand côté — assez pour
ne pas rogner l'antialiasing du bord, sans trop réduire le symbole dans son
cadre."""

_SYMBOL_GLYPH_TARGET_PX = 64
"""Résolution du carré normalisé : net à la taille d'affichage d'une case
(quelques dizaines de pixels CSS), sans gonfler inutilement chaque motif de
34+ couleurs."""


def render_symbol_svg(
    path: Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
    target_px: int = _SYMBOL_GLYPH_TARGET_PX,
) -> str:
    """Découpe le symbole réel (`bbox`, coordonnées `pdfplumber`) depuis la
    page rendue et le renvoie comme un `<svg>` autonome (image encodée en
    base64 dedans) prêt à être stocké et affiché tel quel.

    Rogner un raster de la page déjà rendue plutôt que d'interpréter les
    tables de la police embarquée (glyphe -> contour vectoriel) : la seconde
    approche est fragile d'un exportateur PDF à l'autre (CID -> GID direct
    ou via table, police Type3 vs TrueType/CFF...), alors que rendre la page
    est déjà le mécanisme éprouvé de l'aperçu de cadrage (`render_pdf_page`)
    — fidèle par construction, quel que soit le PDF.

    Carré recentré sur le glyphe (pas son `bbox` brut) : les proportions du
    glyphe varient d'un symbole à l'autre dans un même fichier, alors qu'une
    case de grille est toujours carrée — un carré normalisé compose de façon
    prévisible quelle que soit la forme d'origine."""
    x0, top, x1, bottom = bbox
    width, height = x1 - x0, bottom - top
    side = max(width, height) * (1 + 2 * _SYMBOL_GLYPH_PADDING)
    cx, cy = (x0 + x1) / 2, (top + bottom) / 2
    clip = pymupdf.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)  # type: ignore[no-untyped-call]

    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Page {page_number} hors limites (1..{doc.page_count})")
        page = doc[page_number - 1]
        zoom = target_px / side if side > 0 else 1.0
        matrix = pymupdf.Matrix(zoom, zoom)  # type: ignore[no-untyped-call]
        pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=True)
        png_b64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pixmap.width} {pixmap.height}">'
        f'<image width="{pixmap.width}" height="{pixmap.height}" '
        f'href="data:image/png;base64,{png_b64}"/></svg>'
    )


def render_image_page(path: Path, max_dimension: int = MAX_PREVIEW_DIMENSION) -> bytes:
    """Redimensionne (si besoin) une photo déposée et la renvoie en PNG."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.width > max_dimension or image.height > max_dimension:
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def apply_fills(
    columns: int, rows: int, fills: list[dict[str, int]], base: list[int] | None = None
) -> list[int]:
    """Assemble une grille `columns` × `rows` à partir des zones peintes.

    Chaque zone est un rectangle inclusif de coordonnées de case
    (``x0``, ``y0``, ``x1``, ``y1``) associé à ``palette_index`` (1-based,
    0 = case vide). Les zones sont appliquées dans l'ordre reçu — la
    dernière à toucher une case l'emporte, exactement comme
    `fillSelection` côté client (`frontend/src/state/useTracker.ts`), pour
    que le comportement du pinceau soit identique pendant l'import et
    pendant le suivi.

    `base` (Lot 4) : une grille détectée automatiquement (`app/type_a.py`)
    sert de fond plutôt qu'une case vide — les zones peintes par
    l'utilisateur restent des *corrections* par-dessus la proposition, sans
    aucun nouveau mécanisme de peinture à écrire côté client.
    """
    if base is not None:
        if len(base) != columns * rows:
            raise ValueError("`base` doit avoir exactement columns*rows cases")
        cells = list(base)
    else:
        cells = [0] * (columns * rows)
    for fill in fills:
        x0 = max(0, min(fill["x0"], fill["x1"]))
        x1 = min(columns - 1, max(fill["x0"], fill["x1"]))
        y0 = max(0, min(fill["y0"], fill["y1"]))
        y1 = min(rows - 1, max(fill["y0"], fill["y1"]))
        palette_index = fill["palette_index"]
        for y in range(y0, y1 + 1):
            row_offset = y * columns
            for x in range(x0, x1 + 1):
                cells[row_offset + x] = palette_index
    return cells
