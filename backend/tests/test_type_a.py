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
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pdfplumber
import pymupdf
import pytest
from PIL import Image

from app.imports_engine import render_symbol_svg

# `_cross_check_sections`/`_Legend` sont privés : exception assumée à la
# règle « les tests n'utilisent que l'API publique du module ». La fixture de
# référence ne déclenche jamais ce croisement (tout ce que sa légende annonce
# est retrouvé), et l'appeler directement est la seule façon d'exercer
# vraiment ses codes d'avertissement — voir
# `test_declared_but_missing_special_stitches_are_flagged`.
from app.type_a import (
    TypeAPaletteEntry,
    TypeAResult,
    _cross_check_sections,
    _Legend,
    detect_type_a,
)

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

# Colonnes du tableau « Usage Summary » : Type Number Full Half Quarter
# Petite Back(cm) Str(cm) Spec(cm) French Bead Skein Est.
_USAGE_FULL_ROW_RE = re.compile(
    r"^DMC\s+([A-Za-z0-9]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
    r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)"
)


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


@dataclass
class _UsageRow:
    """Une ligne du tableau « Usage Summary » (page 11), cumulée par code
    DMC — un même code peut y apparaître deux fois (DMC 3776)."""

    full: int = 0
    half: int = 0
    quarter: int = 0
    backstitch: float = 0.0
    french_knots: int = 0


def _expected_usage_by_code() -> dict[str, _UsageRow]:
    """Vérité terrain complète de la page 11, reparsée à chaque exécution.

    **Unité de la colonne « Back(cm) » :** malgré son intitulé, elle est
    exprimée en pouces sur ce fichier — mesuré au Lot 9, la valeur de chaque
    code vaut exactement sa longueur en cases divisée par le compte de toile
    déclaré (« Fabric: Aida 16 », soit 1 case = 1/16 de pouce). Les tests
    ci-dessous font donc la conversion à partir du compte de toile lu dans le
    PDF, jamais d'un facteur écrit en dur."""
    usage: dict[str, _UsageRow] = {}
    with pdfplumber.open(FIXTURE_PATH) as pdf:
        for line in pdf.pages[10].extract_text_lines():
            match = _USAGE_FULL_ROW_RE.match(str(line["text"]))
            if match is None:
                continue
            row = usage.setdefault(match.group(1), _UsageRow())
            row.full += int(match.group(2))
            row.half += int(match.group(3))
            row.quarter += int(match.group(4))
            row.backstitch += float(match.group(6))
            row.french_knots += int(match.group(9))
    return usage


def _counts_by_code(result: TypeAResult, attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in result.palette:
        if not entry.code:
            continue
        counts[entry.code] = counts.get(entry.code, 0) + int(getattr(entry, attribute))
    return counts


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


def test_no_symbol_is_left_unmapped(result: TypeAResult) -> None:
    """Avant le Lot 9, les points 1/2 et 1/4 de ce fichier finissaient en
    entrées « Symbole non reconnu » (6 entrées, 4 583 cases) faute d'être lus
    dans la légende : c'était le comportement honnête du Lot 4, pas une
    fatalité. Maintenant que les sections « Half/Quarter Stitches » sont
    lues, plus aucun symbole de ce fichier ne doit rester non rapproché —
    et toute entrée non reconnue qui subsisterait devrait rester signalée
    par son avertissement (code + paramètres, jamais un texte français figé
    côté serveur, audit des traductions du Lot 8)."""
    unmapped = [entry for entry in result.palette if not entry.code]
    assert unmapped == []
    assert [w for w in result.warnings if w.code == "type_a.unmapped_symbols"] == []


def test_half_and_quarter_counts_match_page_11_exactly(result: TypeAResult) -> None:
    """Points fractionnés (Lot 9) : les couches 1/2 et 1/4 doivent porter
    exactement les comptages annoncés par la page 11 — et sans déplacer une
    seule case de la couche des points entiers, ce que vérifie de son côté
    `test_full_stitch_counts_match_page_11_exactly`."""
    expected = _expected_usage_by_code()
    half = _counts_by_code(result, "count_half")
    quarter = _counts_by_code(result, "count_quarter")

    mismatches = [
        f"{code}: 1/2 attendu {row.half}, obtenu {half.get(code, 0)} ; "
        f"1/4 attendu {row.quarter}, obtenu {quarter.get(code, 0)}"
        for code, row in expected.items()
        if half.get(code, 0) != row.half or quarter.get(code, 0) != row.quarter
    ]
    assert not mismatches, "\n".join(mismatches)
    # Une couche non vide est bien une grille complète, comparable à `cells`.
    assert sum(row.half for row in expected.values()) > 0
    assert len(result.cells_half) == result.columns * result.rows
    assert len(result.cells_quarter) == result.columns * result.rows


def test_french_knots_match_page_11_exactly(result: TypeAResult) -> None:
    expected = _expected_usage_by_code()
    knots = _counts_by_code(result, "count_french_knots")
    assert sum(row.french_knots for row in expected.values()) > 0
    assert {code: row.french_knots for code, row in expected.items() if row.french_knots} == {
        code: count for code, count in knots.items() if count
    }
    assert len(result.french_knots) == sum(row.french_knots for row in expected.values())


def test_backstitch_lengths_match_page_11_within_one_percent(result: TypeAResult) -> None:
    """Longueurs de point arrière par couleur, converties depuis les cases
    via le compte de toile déclaré par le PDF (voir `_expected_usage_by_code`
    pour l'unité réelle de la colonne « Back(cm) ») — jamais un facteur de
    conversion écrit en dur ici.

    La tolérance de 1 % est volontairement plus serrée que la longueur d'un
    seul échantillon de légende (~4.3 cases, soit +4.5 % sur le plus court
    des huit codes) : ce test échouerait donc si les traits d'échantillon
    tracés hors grille sur la page 10 étaient importés comme du vrai point
    arrière — c'est la contrepartie mesurable de
    `test_backstitch_stays_inside_the_assembled_grid`."""
    expected = _expected_usage_by_code()
    assert result.fabric_count is not None

    lengths: dict[str, float] = {}
    for entry in result.palette:
        if entry.code:
            lengths[entry.code] = lengths.get(entry.code, 0.0) + entry.backstitch_length_cells

    declared = {code: row.backstitch for code, row in expected.items() if row.backstitch}
    assert declared, "la page 11 doit déclarer du point arrière"

    mismatches = []
    for code, expected_length in declared.items():
        measured = lengths.get(code, 0.0) / result.fabric_count
        if abs(measured - expected_length) > 0.01 * expected_length:
            mismatches.append(f"{code}: attendu {expected_length}, obtenu {measured:.2f}")
    assert not mismatches, "\n".join(mismatches)

    # Aucune couleur *sans* point arrière déclaré ne doit en recevoir.
    unexpected = [
        code
        for code, length in lengths.items()
        if length > 0 and not expected.get(code, _UsageRow()).backstitch
    ]
    assert unexpected == []


def test_backstitch_stays_inside_the_assembled_grid(result: TypeAResult) -> None:
    """Roadmap Lot 9 §3 : rien de décoratif hors grille ne doit être importé.

    Le fichier de référence en contient vraiment : la page 10 imprime, pour
    chaque code de point arrière, un trait d'échantillon dans **exactement**
    la même couleur que les tracés de la grille (c'est d'ailleurs ce qui
    permet de les rapprocher). Ces traits ne font pas partie du motif et ne
    doivent jamais devenir des segments à broder."""
    assert result.backstitch
    for segment in result.backstitch:
        assert 0 <= segment.x1 <= result.columns
        assert 0 <= segment.x2 <= result.columns
        assert 0 <= segment.y1 <= result.rows
        assert 0 <= segment.y2 <= result.rows
        assert (segment.x1, segment.y1) != (segment.x2, segment.y2)
        # Convention `BackstitchSegment` : des coins de case (ou des milieux
        # de case pour les tracés qui partent du centre), jamais des points
        # arbitraires hérités des coordonnées PDF.
        for value in (segment.x1, segment.y1, segment.x2, segment.y2):
            assert value * 2 == int(value * 2), f"extrémité hors réseau demi-case : {value}"
        assert 1 <= segment.palette_index <= len(result.palette)

    for knot in result.french_knots:
        assert 0 <= knot.x <= result.columns
        assert 0 <= knot.y <= result.rows
        assert 1 <= knot.palette_index <= len(result.palette)


def test_declared_but_missing_special_stitches_are_flagged() -> None:
    """Contrat des avertissements de croisement légende <-> extraction
    (roadmap Lot 9 §4). La fixture de référence ne les déclenche pas (tout
    ce que sa légende annonce est retrouvé), donc ce test passe par la
    fonction de croisement elle-même plutôt que par `detect_type_a` : sans
    ça, ces quatre codes d'avertissement ne seraient jamais exercés, et une
    faute de frappe dans l'un d'eux passerait inaperçue jusqu'au frontend.
    """
    entry = TypeAPaletteEntry(code="310", name="Black", symbol_key="A", rgb_hex="#050505")
    legend = _Legend(
        palette=[entry],
        key_to_target={},
        sample_color_to_index={},
        fractional_glyph_to_target={},
        codes_by_section={"backstitch": [1], "french_knot": [1]},
        unknown_codes=[],
        ambiguous_codes=[],
    )
    empty = TypeAResult(columns=1, rows=1, cells=[0], palette=[entry], confidence=1.0)
    warnings = _cross_check_sections(legend, empty)
    assert [w.code for w in warnings] == [
        "type_a.backstitch_codes_missing",
        "type_a.french_knot_codes_missing",
    ]
    assert all(w.params == {"count": 1, "codes": "310"} for w in warnings)


def test_legend_page_really_carries_decorative_strokes() -> None:
    """Garde-fou des deux tests précédents : vérifie que le piège est réel.

    La page 10 (légende, jamais une page de grille) porte bien des traits
    tracés dans les couleurs de point arrière du motif. Sans cette
    vérification, les tests ci-dessus pourraient passer faute de piège à
    éviter dans le fichier plutôt que grâce au filtre d'emprise."""
    with pdfplumber.open(FIXTURE_PATH) as pdf:
        legend_page = pdf.pages[9]
        assert "Floss Used for Back Stitches:" in legend_page.extract_text()
        coloured = [
            line
            for line in legend_page.lines
            if len(line["stroking_color"] or ()) == 3
            and len(set(float(c) for c in line["stroking_color"])) > 1
        ]
    # Huit codes de point arrière, chacun tracé deux fois (passe sombre puis
    # passe claire) — mesuré au Lot 9.
    assert len(coloured) >= 8


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
