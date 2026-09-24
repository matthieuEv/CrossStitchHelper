"""Tests for the type E extraction engine (Lot 7) against the real
`river-and-mountains-laserarts` fixture — see `fixtures/README.md` and the
`.claude/skills/verify-extraction-fixtures/` skill.

Like `test_type_a.py`/`test_type_bc.py`: no expected value is copied by hand
for the per-colour counts — they are re-parsed from the legend (page 17 of
the PDF) on every run."""

from __future__ import annotations

import base64
import re
import time
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from app.imports_engine import render_symbol_svg
from app.type_e import TypeEResult, detect_type_e

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_PATH = FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf"

# The repository's other five fixtures (types A/B/C, specification §4.4) must
# keep being cleanly ignored by this new connector — exactly as
# `detect_type_a`/`detect_type_bc` already step aside on fixtures of another
# type (see `test_type_a.py`/`test_type_bc.py`).
OTHER_TYPE_FIXTURES = [
    FIXTURES_ROOT / "cafe-brasserie-charting-export" / "CaffeBrasseriecoloursymbols.pdf",
    FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf",
    FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf",
    FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf",
    FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf",
]

_LEGEND_ROW_RE = re.compile(r"DMC\s+(\S+)\n(.+?)\n(\d+)\n[\d.,]+\s*Skeins\n(\d+)")
_DECLARED_DIMENSIONS_RE = re.compile(r"(\d+)x(\d+)\s+Stitches")


def _expected_legend_rows() -> list[tuple[str, str, int]]:
    """`(code, name, stitch_count)` in the legend's printed order (page 17) —
    re-parsed from the PDF itself via PyMuPDF, never copied by hand (same
    rule as `test_type_a.py::_expected_full_stitch_counts`)."""
    with pymupdf.open(FIXTURE_PATH) as doc:  # type: ignore[no-untyped-call]
        for page in doc:
            matches = _LEGEND_ROW_RE.findall(page.get_text())
            if matches:
                return [
                    (code, name.strip(), int(count)) for code, name, _strands, count in matches
                ]
    return []


def _expected_declared_dimensions() -> tuple[int, int] | None:
    with pymupdf.open(FIXTURE_PATH) as doc:  # type: ignore[no-untyped-call]
        for page in doc:
            match = _DECLARED_DIMENSIONS_RE.search(page.get_text())
            if match is not None:
                return int(match.group(1)), int(match.group(2))
    return None


@pytest.fixture(scope="module")
def result() -> TypeEResult:
    detected = detect_type_e(FIXTURE_PATH)
    assert detected is not None
    return detected


def test_fixture_file_present() -> None:
    assert FIXTURE_PATH.is_file(), f"fixture manquante : {FIXTURE_PATH}"


def test_dimensions_match_declared_legend(result: TypeEResult) -> None:
    expected = _expected_declared_dimensions()
    assert expected is not None, "the legend must state its dimensions plainly"
    assert (result.columns, result.rows) == expected
    assert len(result.cells) == result.columns * result.rows


def test_palette_has_20_dmc_colours_matching_legend_order(result: TypeEResult) -> None:
    expected_rows = _expected_legend_rows()
    assert len(expected_rows) == 20

    dmc_entries = [entry for entry in result.palette if entry.code]
    assert len(dmc_entries) == 20
    for (expected_code, expected_name, _count), entry in zip(
        expected_rows, dmc_entries, strict=True
    ):
        assert entry.code == expected_code
        assert entry.name == expected_name


def test_full_stitch_counts_match_legend_exactly(result: TypeEResult) -> None:
    """Core of the verification (specification §7.4: when the PDF itself
    provides the counts, they are used to verify the extraction)."""
    expected_rows = _expected_legend_rows()
    dmc_entries = [entry for entry in result.palette if entry.code]

    counts_by_index: dict[int, int] = {}
    for value in result.cells:
        counts_by_index[value] = counts_by_index.get(value, 0) + 1

    mismatches = []
    for position, ((expected_code, _name, expected_count), entry) in enumerate(
        zip(expected_rows, dmc_entries, strict=True), start=1
    ):
        actual_count = counts_by_index.get(position, 0)
        if entry.code != expected_code or actual_count != expected_count:
            mismatches.append(
                f"ligne {position}: attendu {expected_code}={expected_count}, "
                f"obtenu {entry.code}={actual_count}"
            )
    assert not mismatches, "\n".join(mismatches)


def test_all_matches_use_the_reliable_count_method(result: TypeEResult) -> None:
    """Checks that the primary signal (exact count, see the `app/type_e.py`
    docstring) is really enough on this fixture — not just in theory: none
    of the 20 colours should need the colour fallback, clearly less reliable
    here (12/20 misidentified if relying on colour alone, measured while
    developing this module)."""
    dmc_entries = [entry for entry in result.palette if entry.code]
    assert all(entry.match_method == "count" for entry in dmc_entries)


def test_no_cells_flagged_uncertain_on_this_clean_fixture(result: TypeEResult) -> None:
    """Direct consequence of the previous test: no colour fallback or
    unrecognised symbol should have been needed on this clean fixture —
    `uncertain_cells` must therefore be empty here (unlike `test_type_bc.py`,
    where real uncertainty always remains: it is not the same fallback
    mechanism, and nothing requires both connectors to behave alike on this
    particular point)."""
    assert result.uncertain_cells == []


def test_confidence_is_high_on_clean_fixture(result: TypeEResult) -> None:
    assert result.confidence > 0.85


def test_palette_entries_have_display_colour(result: TypeEResult) -> None:
    for entry in result.palette:
        assert entry.rgb_hex.startswith("#")
        assert len(entry.rgb_hex) == 7
        assert entry.symbol_key.isascii()
        assert entry.symbol_key.isprintable()


def test_palette_entries_carry_symbol_glyph_location(result: TypeEResult) -> None:
    for entry in result.palette:
        assert entry.symbol_glyph is not None
        assert 2 <= entry.symbol_glyph.page_number <= 17
        x0, top, x1, bottom = entry.symbol_glyph.bbox
        assert x1 > x0
        assert bottom > top


def test_render_symbol_svg_produces_a_real_legible_icon_crop(result: TypeEResult) -> None:
    """End to end, like `test_type_a.py`: the captured position must really
    make it possible to cut out a readable image of the combined colour +
    symbol icon."""
    entry = result.palette[0]
    assert entry.symbol_glyph is not None
    svg = render_symbol_svg(FIXTURE_PATH, entry.symbol_glyph.page_number, entry.symbol_glyph.bbox)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    png_bytes = base64.b64decode(svg.split("base64,", 1)[1].split('"', 1)[0])
    with Image.open(BytesIO(png_bytes)) as image:
        assert image.width >= 16
        assert image.height >= 16


def test_grid_is_densely_filled_not_mostly_blank(result: TypeEResult) -> None:
    """Safety net against a false detection that would place almost no cell
    (guard already present in `detect_type_e`, verified end to end here):
    this pattern must be mostly filled."""
    filled = sum(1 for v in result.cells if v != 0)
    fraction = filled / len(result.cells)
    assert fraction > 0.5


def _tiny_non_type_e_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 100), "Just a plain PDF, not a pattern export.")
    path = tmp_path / "not-type-e.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    return path


def test_returns_none_for_non_type_e_pdf(tmp_path: Path) -> None:
    assert detect_type_e(_tiny_non_type_e_pdf(tmp_path)) is None


def test_never_raises_on_empty_pdf(tmp_path: Path) -> None:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page(width=300, height=200)
    path = tmp_path / "empty.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    assert detect_type_e(path) is None


@pytest.mark.parametrize("path", OTHER_TYPE_FIXTURES, ids=lambda p: p.parent.name)
def test_returns_none_for_other_fixture_types(path: Path) -> None:
    """Types A/B/C (symbol font or vector grids, no reused bitmap image): no
    type E false positive."""
    if not path.is_file():
        pytest.skip(f"fixture manquante : {path}")
    assert detect_type_e(path) is None


def test_runs_within_reasonable_time() -> None:
    """Generous performance benchmark (specification §10: "under 30 seconds"
    for a 10-page PDF; this one has 18, with tens of thousands of image
    placements)."""
    start = time.perf_counter()
    detect_type_e(FIXTURE_PATH)
    assert time.perf_counter() - start < 30.0
