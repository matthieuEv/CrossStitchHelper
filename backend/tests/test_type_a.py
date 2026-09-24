"""Tests for the type A extraction engine (Lot 4) against the real
`cafe-brasserie-charting-export` fixture — see `fixtures/README.md` and the
`.claude/skills/verify-extraction-fixtures/` skill.

No expected value is copied by hand here for the per-colour counts: they are
re-parsed from page 11 ("Usage Summary") of the PDF itself on every run, so
as never to duplicate a truth already present in the reference file (see the
skill above, which warns against this kind of duplication)."""

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

# `_cross_check_sections`/`_Legend` are private: a deliberate exception to
# the "tests only use the module's public API" rule. The reference fixture
# never triggers this cross-check (everything its legend declares is found),
# and calling it directly is the only way to really exercise its warning
# codes — see `test_declared_but_missing_special_stitches_are_flagged`.
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

# The repository's other fixtures (types B/C/E, specification §4.4) are not
# type A: `detect_type_a` must step aside without raising or forcing a
# poor-quality result ("never block an import" rule,
# `.claude/agents/pdf-extraction-specialist.md`). This module does not handle
# them (Lots 5/7) — this test only checks the absence of false positives.
OTHER_TYPE_FIXTURES = [
    FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf",
    FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf",
    FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf",
    FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf",
    FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf",
]

_USAGE_ROW_RE = re.compile(r"^DMC\s+([A-Za-z0-9]+)\s+(\d+)\s")

# Columns of the "Usage Summary" table: Type Number Full Half Quarter
# Petite Back(cm) Str(cm) Spec(cm) French Bead Skein Est.
_USAGE_FULL_ROW_RE = re.compile(
    r"^DMC\s+([A-Za-z0-9]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
    r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)"
)


def _expected_full_stitch_counts() -> list[tuple[str, int]]:
    """`(code, full_count)` in the order of the PDF's page 11, as printed —
    the same order as the "Full Stitches" legend section on page 9 (checked
    manually once, see the task report), so directly comparable position by
    position with `result.palette`."""
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
    """A row of the "Usage Summary" table (page 11), accumulated per DMC
    code — the same code can appear twice there (DMC 3776)."""

    full: int = 0
    half: int = 0
    quarter: int = 0
    backstitch: float = 0.0
    french_knots: int = 0


def _expected_usage_by_code() -> dict[str, _UsageRow]:
    """Complete ground truth from page 11, re-parsed on every run.

    **Unit of the "Back(cm)" column:** despite its heading, it is expressed
    in inches on this file — measured in Lot 9, each code's value is exactly
    its length in cells divided by the declared fabric count ("Fabric: Aida
    16", i.e. 1 cell = 1/16 inch). The tests below therefore convert from the
    fabric count read in the PDF, never from a hard-coded factor."""
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
    # No DMC code duplicated as a *palette key* is expected here in the sense
    # of a merge: DMC 3776 appears twice in the legend (two distinct symbols,
    # different counts) and must therefore remain two separate entries — see
    # fixtures/README.md.
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
        # Never the raw glyph of the PDF's private font as a UI key.
        assert entry.symbol_key.isascii()
        assert entry.symbol_key.isprintable()


def test_palette_entries_carry_symbol_glyph_location(result: TypeAResult) -> None:
    """Needed to recover the PDF's real symbol (`render_symbol_svg`) rather
    than a synthetic letter in the UI — see `SymbolGlyphLocation`."""
    dmc_entries = [entry for entry in result.palette if entry.code]
    assert dmc_entries
    for entry in dmc_entries:
        assert entry.symbol_glyph is not None
        assert 1 <= entry.symbol_glyph.page_number <= 11
        x0, top, x1, bottom = entry.symbol_glyph.bbox
        assert x1 > x0
        assert bottom > top


def test_render_symbol_svg_produces_a_real_legible_glyph_crop(result: TypeAResult) -> None:
    """End to end: the position captured by `detect_type_a` must really make
    it possible to cut out a readable image of the symbol — not just look
    well-formed, and not just a white square between two glyphs."""
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
    """Safety net against a coordinate bug that would always cut out the
    same area of the page whatever glyph is requested."""
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
    """Before Lot 9, this file's 1/2 and 1/4 stitches ended up as
    "Unrecognised symbol" entries (6 entries, 4,583 cells) for lack of being
    read from the legend: that was Lot 4's honest behaviour, not an
    inevitability. Now that the "Half/Quarter Stitches" sections are read, no
    symbol of this file should remain unmatched — and any unrecognised entry
    that remained should stay flagged by its warning (code + parameters,
    never French text frozen on the server, Lot 8 translation audit)."""
    unmapped = [entry for entry in result.palette if not entry.code]
    assert unmapped == []
    assert [w for w in result.warnings if w.code == "type_a.unmapped_symbols"] == []


def test_half_and_quarter_counts_match_page_11_exactly(result: TypeAResult) -> None:
    """Fractional stitches (Lot 9): the 1/2 and 1/4 layers must carry
    exactly the counts declared on page 11 — without moving a single cell of
    the full-stitch layer, which
    `test_full_stitch_counts_match_page_11_exactly` checks on its side."""
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
    # A non-empty layer is indeed a complete grid, comparable with `cells`.
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
    """Backstitch lengths per colour, converted from cells via the fabric
    count declared by the PDF (see `_expected_usage_by_code` for the real
    unit of the "Back(cm)" column) — never a conversion factor hard-coded
    here.

    The 1% tolerance is deliberately tighter than the length of a single
    legend swatch (~4.3 cells, i.e. +4.5% on the shortest of the eight
    codes): this test would therefore fail if the swatch strokes drawn off
    the grid on page 10 were imported as real backstitch — it is the
    measurable counterpart of
    `test_backstitch_stays_inside_the_assembled_grid`."""
    expected = _expected_usage_by_code()
    assert result.fabric_count is not None

    lengths: dict[str, float] = {}
    for entry in result.palette:
        if entry.code:
            lengths[entry.code] = lengths.get(entry.code, 0.0) + entry.backstitch_length_cells

    declared = {code: row.backstitch for code, row in expected.items() if row.backstitch}
    assert declared, "page 11 must declare backstitch"

    mismatches = []
    for code, expected_length in declared.items():
        measured = lengths.get(code, 0.0) / result.fabric_count
        if abs(measured - expected_length) > 0.01 * expected_length:
            mismatches.append(f"{code}: attendu {expected_length}, obtenu {measured:.2f}")
    assert not mismatches, "\n".join(mismatches)

    # No colour *without* declared backstitch may receive any.
    unexpected = [
        code
        for code, length in lengths.items()
        if length > 0 and not expected.get(code, _UsageRow()).backstitch
    ]
    assert unexpected == []


def test_backstitch_stays_inside_the_assembled_grid(result: TypeAResult) -> None:
    """Roadmap Lot 9 §3: nothing decorative off the grid may be imported.

    The reference file really contains some: page 10 prints, for each
    backstitch code, a swatch stroke in **exactly** the same colour as the
    grid's strokes (which is precisely what makes matching them possible).
    These strokes are not part of the pattern and must never become segments
    to stitch."""
    assert result.backstitch
    for segment in result.backstitch:
        assert 0 <= segment.x1 <= result.columns
        assert 0 <= segment.x2 <= result.columns
        assert 0 <= segment.y1 <= result.rows
        assert 0 <= segment.y2 <= result.rows
        assert (segment.x1, segment.y1) != (segment.x2, segment.y2)
        # `BackstitchSegment` convention: cell corners (or cell midpoints for
        # strokes starting from the centre), never arbitrary points inherited
        # from PDF coordinates.
        for value in (segment.x1, segment.y1, segment.x2, segment.y2):
            assert value * 2 == int(value * 2), f"endpoint off the half-cell lattice: {value}"
        assert 1 <= segment.palette_index <= len(result.palette)

    for knot in result.french_knots:
        assert 0 <= knot.x <= result.columns
        assert 0 <= knot.y <= result.rows
        assert 1 <= knot.palette_index <= len(result.palette)


def test_declared_but_missing_special_stitches_are_flagged() -> None:
    """Contract of the legend <-> extraction cross-check warnings (roadmap
    Lot 9 §4). The reference fixture does not trigger them (everything its
    legend declares is found), so this test goes through the cross-check
    function itself rather than `detect_type_a`: without that, these four
    warning codes would never be exercised, and a typo in one of them would
    go unnoticed until the frontend.
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
    """Guard for the two previous tests: checks that the trap is real.

    Page 10 (legend, never a grid page) does carry strokes drawn in the
    pattern's backstitch colours. Without this check, the tests above could
    pass for lack of a trap to avoid in the file rather than thanks to the
    footprint filter."""
    with pdfplumber.open(FIXTURE_PATH) as pdf:
        legend_page = pdf.pages[9]
        assert "Floss Used for Back Stitches:" in legend_page.extract_text()
        coloured = [
            line
            for line in legend_page.lines
            if len(line["stroking_color"] or ()) == 3
            and len(set(float(c) for c in line["stroking_color"])) > 1
        ]
    # Eight backstitch codes, each drawn twice (dark pass then light pass) —
    # measured in Lot 9.
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
    """Types B/C/E (vector grids or bitmap image catalogue, no embedded
    symbol font): no type A false positive."""
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
