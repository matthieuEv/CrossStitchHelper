"""File fingerprint for reusable recipes (Lot 6, specification §8.7).

The fingerprint identifies the **software/publisher/shop** that produced the
PDF — never the pattern itself. It must therefore never depend on a value
that varies with the creative content from one file to the next (grid
dimensions, colours used, number of grid pages, pattern title): only the
structure of the export template counts — page size, embedded fonts, and the
presence of generic labels the software prints on every export whatever the
pattern ("Floss Used for", "Symbol"...).

Never raises: an unreadable or atypical PDF must simply have no reusable
fingerprint, never make the import fail (specification §10, same contract as
`type_a.detect_type_a`/`type_bc.detect_type_bc`).

PyMuPDF rather than `pdfplumber` (used by `app/type_a.py` for fine-grained
font/text analysis): `pdfplumber` rebuilds a per-glyph layout (geometric
clustering) even for a simple list of font names, and was measured at ~2s
**per page** on `cafe-brasserie-charting-export` (dense symbol font,
thousands of glyphs per grid page), far too much for a background task — see
this file's history: the first version used `pdfplumber` and had to be fixed
after a regression observed on the e2e suites (fingerprint computation had
become the dominant cost of detection time). PyMuPDF's
`page.get_fonts()`/`page.get_text()` do not have this cost (measured at a few
milliseconds on the same file, all pages together): they read the page's
resource dictionary and text stream, with no geometric reclustering."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymupdf

# Generic labels a charting program prints on every export, independently of
# the pattern — never the pattern title or a specific colour name, which
# would be creative content. Spotted on the reference fixtures
# (`cafe-brasserie-charting-export`, the four DMC files).
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

# Pages sampled for generic text — not the whole document: the legend/header
# is always there on the reference fixtures, and `get_text()` remains
# expensive at the scale of several dozen pages.
_TEXT_SAMPLE_PAGES = 3


def compute_fingerprint(source_path: Path, kind: str) -> str | None:
    """`None` for anything that is not a PDF (a photo has no software
    structure to recognise), or if the analysis fails."""
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
    """"ABCDEE+Wingdings" -> "Wingdings". The six-capital-letter prefix
    followed by "+" is a font subset tag randomly generated on every export
    (standard PDF convention, cf. PDF 32000-1 §9.6.4): it would never be
    shared by two files from the same publisher, unlike the font name
    itself."""
    return _SUBSET_TAG_RE.sub("", base_font_name)
