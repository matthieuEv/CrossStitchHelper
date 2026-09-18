"""Empreinte de fichier pour les recettes réutilisables (Lot 6, cahier des
charges §8.7).

L'empreinte identifie le **logiciel/éditeur/boutique** qui a produit le PDF
— jamais le motif lui-même. Elle ne doit donc jamais dépendre d'une valeur
qui varie avec le contenu créatif d'un fichier à l'autre (dimensions de la
grille, couleurs utilisées, nombre de pages de grille, titre du motif) :
seule la structure du gabarit d'export compte — taille de page, polices
embarquées, et présence de libellés génériques que le logiciel imprime sur
chaque export quel que soit le motif (« Floss Used for », « Symbol »...).

Ne lève jamais : un PDF illisible ou atypique doit simplement ne pas avoir
d'empreinte réutilisable, jamais faire échouer l'import (cahier des charges
§10, même contrat que `type_a.detect_type_a`/`type_bc.detect_type_bc`).

PyMuPDF plutôt que `pdfplumber` (utilisé par `app/type_a.py` pour l'analyse
fine de police/texte) : `pdfplumber` reconstruit un layout par glyphe
(clustering géométrique) même pour une simple liste de noms de polices, et
s'est mesuré à ~2s **par page** sur `cafe-brasserie-charting-export`
(police de symboles dense, des milliers de glyphes par page de grille),
largement trop pour une tâche de fond — voir l'historique de ce fichier :
la première version utilisait `pdfplumber` et a dû être corrigée après une
régression observée sur les suites e2e (calcul d'empreinte devenu le poste
dominant du temps de détection). `page.get_fonts()`/`page.get_text()` de
PyMuPDF n'ont pas ce coût (mesuré à quelques millisecondes sur ce même
fichier, toutes pages confondues) : ils lisent le dictionnaire de
ressources et le flux de texte de la page, sans reclustering géométrique."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymupdf

# Libellés génériques qu'un logiciel de charting imprime sur chaque export,
# indépendamment du motif — jamais le titre du motif ou le nom d'une couleur
# spécifique, qui seraient du contenu créatif. Repérés sur les fixtures de
# référence (`cafe-brasserie-charting-export`, les quatre fichiers DMC).
_BOILERPLATE_PHRASES = (
    "floss used for",
    "symbol",
    "strands",
    "color",
    "dmc",
    "anchor",
    "usage summary",
    "backstitch",
    "french knot",
    "full stitch",
    "stitches",
    "legend",
)

_SUBSET_TAG_RE = re.compile(r"^[A-Z]{6}\+")

# Pages sondées pour le texte générique — pas le document entier : la
# légende/l'en-tête s'y trouve toujours sur les fixtures de référence, et
# `get_text()` reste cher à l'échelle de plusieurs dizaines de pages.
_TEXT_SAMPLE_PAGES = 3


def compute_fingerprint(source_path: Path, kind: str) -> str | None:
    """`None` pour tout ce qui n'est pas un PDF (une photo n'a pas de
    structure de logiciel à reconnaître), ou si l'analyse échoue."""
    if kind != "pdf":
        return None
    try:
        return _compute(source_path)
    except Exception:
        return None


def _compute(source_path: Path) -> str:
    with pymupdf.open(source_path) as doc:  # type: ignore[no-untyped-call]
        first_page = doc[0]
        rect = first_page.rect
        page_size = (round(rect.width), round(rect.height))

        font_names: set[str] = set()
        sample_text_parts: list[str] = []
        for index, page in enumerate(doc):
            for font in page.get_fonts():
                font_names.add(_strip_subset_tag(str(font[3])))
            if index < _TEXT_SAMPLE_PAGES:
                sample_text_parts.append(page.get_text())

    sample_text = "\n".join(sample_text_parts).lower()
    boilerplate_hits = tuple(
        sorted(phrase for phrase in _BOILERPLATE_PHRASES if phrase in sample_text)
    )
    features = {
        "page_size": page_size,
        "fonts": sorted(font_names),
        "boilerplate": boilerplate_hits,
    }
    return hashlib.sha256(json.dumps(features, sort_keys=True).encode("utf-8")).hexdigest()


def _strip_subset_tag(base_font_name: str) -> str:
    """« ABCDEE+Wingdings » -> « Wingdings ». Le préfixe de six lettres
    capitales suivi de « + » est un tag de sous-ensemble de police généré
    aléatoirement à chaque export (convention PDF standard, cf. PDF 32000-1
    §9.6.4) : il ne serait jamais commun à deux fichiers d'un même éditeur,
    contrairement au nom de police lui-même."""
    return _SUBSET_TAG_RE.sub("", base_font_name)
