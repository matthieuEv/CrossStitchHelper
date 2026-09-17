"""Tests du moteur d'extraction type A (Lot 4) contre la fixture réelle
`cafe-brasserie-charting-export` — voir `fixtures/README.md` et le skill
`.claude/skills/verify-extraction-fixtures/`.

Aucune valeur attendue n'est recopiée à la main ici pour les comptages par
couleur : ils sont reparsés depuis la page 11 ("Usage Summary") du PDF
lui-même à chaque exécution, pour ne jamais dupliquer une vérité déjà
présente dans le fichier de référence (voir le skill précité, qui met en
garde contre ce genre de duplication)."""

from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path

import pdfplumber
import pymupdf
import pytest
from PIL import Image

from app.imports_engine import render_symbol_svg
from app.type_a import TypeAResult, detect_type_a

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_PATH = (
    FIXTURES_ROOT / "cafe-brasserie-charting-export" / "CaffeBrasseriecoloursymbols.pdf"
)

# Les autres fixtures du dépôt (types B/C/E, cahier des charges §4.4) ne
# sont pas du type A : `detect_type_a` doit s'effacer sans lever ni forcer
# un résultat de mauvaise qualité (règle « ne jamais bloquer un import »,
# `.claude/agents/pdf-extraction-specialist.md`). Ce module ne les traite
# pas (Lots 5/7) — ce test vérifie seulement l'absence de faux positif.
OTHER_TYPE_FIXTURES = [
    FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf",
    FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf",
    FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf",
    FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf",
    FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf",
]

_USAGE_ROW_RE = re.compile(r"^DMC\s+([A-Za-z0-9]+)\s+(\d+)\s")


def _expected_full_stitch_counts() -> list[tuple[str, int]]:
    """`(code, comptage_plein)` dans l'ordre de la page 11 du PDF, tel
    qu'imprimé — c'est le même ordre que la section légende « Full Stitches »
    de la page 9 (vérifié manuellement une fois, voir le rapport de tâche),
    donc directement comparable position à position avec `result.palette`."""
    rows: list[tuple[str, int]] = []
    with pdfplumber.open(FIXTURE_PATH) as pdf:
        page = pdf.pages[10]  # page 11, "Usage Summary"
        for line in page.extract_text_lines():
            match = _USAGE_ROW_RE.match(str(line["text"]))
            if match is None:
                continue
            rows.append((match.group(1), int(match.group(2))))
    return rows


@pytest.fixture(scope="module")
def result() -> TypeAResult:
    detected = detect_type_a(FIXTURE_PATH)
    assert detected is not None
    return detected


def test_fixture_file_present() -> None:
    assert FIXTURE_PATH.is_file(), f"fixture manquante : {FIXTURE_PATH}"


def test_dimensions_match_declared_255x180(result: TypeAResult) -> None:
    assert result.columns == 255
    assert result.rows == 180
    assert len(result.cells) == 255 * 180


def test_palette_has_34_dmc_colours(result: TypeAResult) -> None:
    dmc_entries = [entry for entry in result.palette if entry.code]
    assert len(dmc_entries) == 34
    # Aucun code DMC dupliqué en tant que *clé de palette* n'est attendu ici
    # au sens d'une fusion : DMC 3776 apparaît deux fois dans la légende
    # (deux symboles distincts, comptages différents) et doit donc rester
    # deux entrées séparées — voir fixtures/README.md.
    codes = [entry.code for entry in dmc_entries]
    assert codes.count("3776") == 2


def test_full_stitch_counts_match_page_11_exactly(result: TypeAResult) -> None:
    expected = _expected_full_stitch_counts()
    assert len(expected) == 34

    dmc_entries = [entry for entry in result.palette if entry.code]
    assert len(dmc_entries) == len(expected)

    counts_by_index: dict[int, int] = {}
    for value in result.cells:
        counts_by_index[value] = counts_by_index.get(value, 0) + 1

    mismatches = []
    for position, ((expected_code, expected_count), entry) in enumerate(
        zip(expected, dmc_entries, strict=True), start=1
    ):
        actual_code = entry.code
        actual_count = counts_by_index.get(position, 0)
        if actual_code != expected_code or actual_count != expected_count:
            mismatches.append(
                f"ligne {position}: attendu {expected_code}={expected_count}, "
                f"obtenu {actual_code}={actual_count}"
            )
    assert not mismatches, "\n".join(mismatches)


def test_confidence_is_high_on_clean_fixture(result: TypeAResult) -> None:
    assert result.confidence > 0.85


def test_palette_entries_have_display_colour(result: TypeAResult) -> None:
    for entry in result.palette:
        assert entry.rgb_hex.startswith("#")
        assert len(entry.rgb_hex) == 7
        # Jamais le glyphe brut de la police privée du PDF comme clé UI.
        assert entry.symbol_key.isascii()
        assert entry.symbol_key.isprintable()


def test_palette_entries_carry_symbol_glyph_location(result: TypeAResult) -> None:
    """Nécessaire pour retrouver le vrai symbole du PDF (`render_symbol_svg`)
    plutôt qu'une lettre synthétique côté UI — voir `SymbolGlyphLocation`."""
    dmc_entries = [entry for entry in result.palette if entry.code]
    assert dmc_entries
    for entry in dmc_entries:
        assert entry.symbol_glyph is not None
        assert 1 <= entry.symbol_glyph.page_number <= 11
        x0, top, x1, bottom = entry.symbol_glyph.bbox
        assert x1 > x0
        assert bottom > top


def test_render_symbol_svg_produces_a_real_legible_glyph_crop(result: TypeAResult) -> None:
    """Bout en bout : la position capturée par `detect_type_a` doit vraiment
    permettre de découper une image lisible du symbole — pas juste être bien
    formée en apparence, et pas juste un carré blanc entre deux glyphes."""
    entry = next(e for e in result.palette if e.code)
    assert entry.symbol_glyph is not None
    svg = render_symbol_svg(FIXTURE_PATH, entry.symbol_glyph.page_number, entry.symbol_glyph.bbox)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "image/png;base64," in svg

    png_bytes = base64.b64decode(svg.split("base64,", 1)[1].split('"', 1)[0])
    with Image.open(BytesIO(png_bytes)) as image:
        assert image.width >= 32
        assert image.height >= 32
        low, high = image.convert("L").getextrema()
        assert isinstance(low, int) and isinstance(high, int)
        assert high - low > 40


def test_render_symbol_svg_differs_between_distinct_symbols(result: TypeAResult) -> None:
    """Filet contre un bug de coordonnées qui découperait toujours la même
    zone de la page quel que soit le glyphe demandé."""
    dmc_entries = [entry for entry in result.palette if entry.code]
    first, second = dmc_entries[0], dmc_entries[1]
    assert first.symbol_glyph is not None
    assert second.symbol_glyph is not None
    svg_first = render_symbol_svg(
        FIXTURE_PATH, first.symbol_glyph.page_number, first.symbol_glyph.bbox
    )
    svg_second = render_symbol_svg(
        FIXTURE_PATH, second.symbol_glyph.page_number, second.symbol_glyph.bbox
    )
    assert svg_first != svg_second


def test_unmapped_cells_are_flagged_not_silently_empty(result: TypeAResult) -> None:
    """Les points de demi-croix (hors périmètre du Lot 4) partagent parfois
    le même glyphe que des points pleins d'une autre couleur dans ce fichier
    — ils doivent finir en entrées « Symbole non reconnu » explicites,
    jamais en case vide (0) silencieuse ni fusionnés dans la mauvaise
    couleur pleine."""
    unmapped = [entry for entry in result.palette if not entry.code]
    assert unmapped
    assert all(entry.name == "Symbole non reconnu" for entry in unmapped)
    assert any("non reconnu" in warning for warning in result.warnings)


def _tiny_non_type_a_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 100), "Just a plain PDF, not a pattern export.")
    path = tmp_path / "not-type-a.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    return path


def test_returns_none_for_non_type_a_pdf(tmp_path: Path) -> None:
    path = _tiny_non_type_a_pdf(tmp_path)
    assert detect_type_a(path) is None


@pytest.mark.parametrize("path", OTHER_TYPE_FIXTURES, ids=lambda p: p.parent.name)
def test_returns_none_for_other_fixture_types(path: Path) -> None:
    """Types B/C/E (grilles vectorielles ou catalogue d'images bitmap, sans
    police de symboles embarquée) : pas de faux positif type A."""
    if not path.is_file():
        pytest.skip(f"fixture manquante : {path}")
    assert detect_type_a(path) is None


def test_never_raises_on_empty_pdf(tmp_path: Path) -> None:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page(width=300, height=200)
    path = tmp_path / "empty.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    assert detect_type_a(path) is None
