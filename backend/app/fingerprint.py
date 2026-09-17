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

`pdfplumber` (déjà utilisé par `app/type_a.py` pour l'analyse de police et
de texte, contrairement à PyMuPDF réservé au rendu/rasterisation dans
`app/type_bc.py`/`app/imports_engine.py`) plutôt que PyMuPDF : c'est lui qui
porte des annotations de type, ce qui évite ici une longue suite de
`# type: ignore[no-untyped-call]`."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pdfplumber

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
    with pdfplumber.open(source_path) as pdf:
        first_page = pdf.pages[0]
        page_size = (round(first_page.width), round(first_page.height))

        font_names: set[str] = set()
        for page in pdf.pages:
            font_names.update(_strip_subset_tag(str(char["fontname"])) for char in page.chars)

        # Trois premières pages seulement : la légende/l'en-tête générique
        # s'y trouve toujours sur les fixtures de référence, pas besoin de
        # lire un PDF de plusieurs dizaines de pages en entier pour ça.
        sample_text = "\n".join(page.extract_text() or "" for page in pdf.pages[:3]).lower()

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
