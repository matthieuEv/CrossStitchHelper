"""Tests for the type B/C extraction engine (Lot 5) against the four real
DMC fixtures — see `fixtures/README.md` and the
`.claude/skills/verify-extraction-fixtures/` skill.

The number of distinct colours actually used (`fixtures/README.md`) is
checked exactly for three of the four fixtures: 14 for `winter-wreath-dmc`,
17 for `botanical-citrus-dmc`, 18 for `cucurbit-dmc` (all 18 colours of
cucurbit's legend are indeed actually used in the grid — measured directly
on the coloured cells, not copied from the legend; contrary to what a quick
look at the legend might suggest, cf. `docs/specification.md` §4.3: never
assume, always measure).

`summer-flight-dmc` is Lot 5's trap case (§4.3): its colour page itself
already contains an amount of vector paths comparable to a full-fledged
symbol page. It serves here to check that the connector never blindly
assumes a two-page overlay, **and** — beyond measuring density per page —
that shape recognition honestly falls back to colour only (type B) when it
is not reliable enough across the whole file, rather than producing an
unusable palette of several hundred entries. This file actually uses a
richly shaded illustration (several tones per pattern element, not a single
flat fill per thread): the number of distinct colours measured is therefore
deliberately checked as a lower bound relative to the 12 codes of the
"counted stitches" legend, not copied from that legend — same rules as
`test_type_a.py`: no expected value defined by hand when the source file
allows it to be measured directly."""

from __future__ import annotations

import time
from pathlib import Path

import pymupdf
import pytest

from app.type_bc import TypeBCResult, detect_type_bc

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"

WINTER_WREATH = FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf"
BOTANICAL_CITRUS = FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf"
CUCURBIT = FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf"
SUMMER_FLIGHT = FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf"

DMC_FIXTURES = [WINTER_WREATH, BOTANICAL_CITRUS, CUCURBIT, SUMMER_FLIGHT]

# The two fixtures of another type (specification §4.4): `detect_type_bc`
# must cleanly step aside on them, as `detect_type_a` steps aside on the
# B/C/E fixtures (see `test_type_a.py`).
OTHER_TYPE_FIXTURES = [
    FIXTURES_ROOT / "cafe-brasserie-charting-export" / "CaffeBrasseriecoloursymbols.pdf",
    FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf",
]


def _distinct_colors(result: TypeBCResult) -> int:
    """Number of distinct colours actually present in the palette — several
    palette entries can share the same colour in type C (one colour
    associated with several distinct symbols), hence distinct from
    `len(result.palette)`."""
    return len({entry.rgb_hex for entry in result.palette})


@pytest.fixture(scope="module")
def winter_wreath() -> TypeBCResult:
    result = detect_type_bc(WINTER_WREATH)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def botanical_citrus() -> TypeBCResult:
    result = detect_type_bc(BOTANICAL_CITRUS)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def cucurbit() -> TypeBCResult:
    result = detect_type_bc(CUCURBIT)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def summer_flight() -> TypeBCResult:
    result = detect_type_bc(SUMMER_FLIGHT)
    assert result is not None
    return result


@pytest.mark.parametrize("path", DMC_FIXTURES, ids=lambda p: p.parent.name)
def test_fixture_files_present(path: Path) -> None:
    assert path.is_file(), f"fixture manquante : {path}"


def _assert_well_formed(result: TypeBCResult) -> None:
    assert result.columns > 0
    assert result.rows > 0
    assert len(result.cells) == result.columns * result.rows
    assert all(0 <= value <= len(result.palette) for value in result.cells)
    assert all(
        entry.rgb_hex.startswith("#") and len(entry.rgb_hex) == 7 for entry in result.palette
    )
    assert all(
        entry.symbol_key.isascii() and entry.symbol_key.isprintable() for entry in result.palette
    )
    assert all(0 <= idx < len(result.cells) for idx in result.uncertain_cells)
    assert 0.0 <= result.confidence <= 1.0


def test_winter_wreath_is_well_formed(winter_wreath: TypeBCResult) -> None:
    _assert_well_formed(winter_wreath)


def test_botanical_citrus_is_well_formed(botanical_citrus: TypeBCResult) -> None:
    _assert_well_formed(botanical_citrus)


def test_cucurbit_is_well_formed(cucurbit: TypeBCResult) -> None:
    _assert_well_formed(cucurbit)


def test_summer_flight_is_well_formed(summer_flight: TypeBCResult) -> None:
    _assert_well_formed(summer_flight)


def test_winter_wreath_distinct_colours_match_legend(winter_wreath: TypeBCResult) -> None:
    """`fixtures/README.md`: legend on page 4, 14 DMC codes (3345, 3346, 471,
    472, 11, 18, 3821, 726, 3853, 3854, white, 351, 814, E321)."""
    assert _distinct_colors(winter_wreath) == 14


def test_botanical_citrus_distinct_colours_match_legend(botanical_citrus: TypeBCResult) -> None:
    """`fixtures/README.md`: legend on page 4, 17 DMC colours."""
    assert _distinct_colors(botanical_citrus) == 17


def test_cucurbit_distinct_colours_match_legend(cucurbit: TypeBCResult) -> None:
    """`fixtures/README.md` reports 18 colours in the legend including 6
    swatches not in the pattern — but measured directly on the grid's
    actually coloured cells (never on the legend), all 18 of cucurbit's
    colours are indeed used in the grid: none of the 18 is a colour
    duplicate of another. The "not in the pattern" filtering described in
    the fixture therefore applies to the legend as printed (which includes
    swatches not used in the drawing), not to an excess of colours measured
    here — consistent with the instruction to verify directly rather than
    copy an indicative figure."""
    assert _distinct_colors(cucurbit) == 18


def test_summer_flight_uses_more_shades_than_its_flat_legend_suggests(
    summer_flight: TypeBCResult,
) -> None:
    """The "counted stitches" legend of `summer-flight-dmc` lists 12 DMC
    codes, but the colour page actually draws a shaded illustration (several
    distinct tones per pattern area rather than a single flat fill per
    thread) — measured directly, not copied from the legend. The connector
    must therefore find noticeably more than 12 distinct colours there."""
    assert _distinct_colors(summer_flight) > 12


def test_winter_wreath_symbols_reused_from_its_own_colour_page(
    winter_wreath: TypeBCResult,
) -> None:
    """Measured case (§4.3): the colour page of `winter-wreath-dmc` itself
    already carries the symbols — no separate page is needed, and the
    connector must measure that rather than assume the "page 1 colour only /
    page 2 symbols" structure a quick look at specification §4.1 would
    suggest."""
    assert winter_wreath.grid_type == "C"
    glyphs = [e.symbol_glyph for e in winter_wreath.palette if e.symbol_glyph is not None]
    assert glyphs
    assert all(g.page_number == 1 for g in glyphs)


@pytest.mark.parametrize(
    "fixture_name", ["botanical_citrus", "cucurbit"], ids=lambda n: n.replace("_", "-")
)
def test_botanical_and_cucurbit_overlay_a_separate_symbol_page(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Measured case (§4.3, `fixtures/README.md`): the colour page of these
    two fixtures is clean (few paths), page 2 carries the symbols — a
    two-page overlay is genuinely needed here, unlike `winter-wreath-dmc`
    and `summer-flight-dmc`."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    assert result.grid_type == "C"
    glyphs = [e.symbol_glyph for e in result.palette if e.symbol_glyph is not None]
    assert glyphs
    assert all(g.page_number == 2 for g in glyphs)


def test_summer_flight_never_blindly_overlays_a_redundant_page(
    summer_flight: TypeBCResult,
) -> None:
    """The heart of the trap case (§4.3): this file must never make the
    connector fail by making it believe in a real overlayable symbol page.
    Here, shape recognition turns out to be too unreliable across the whole
    file (shaded illustration, not one crisp symbol per cell) — an honest
    fallback to type B, never a palette of several hundred entries presented
    as reliable."""
    assert summer_flight.grid_type == "B"
    assert len(summer_flight.palette) < 50
    # The fallback must be announced explicitly, through a message code
    # (never French text frozen on the server — translation audit, Lot 8):
    # one of the three codes that signal a fallback to colour only.
    fallback_codes = {
        "type_bc.symbol_recognition_unreliable",
        "type_bc.symbol_page_unusable",
        "type_bc.no_symbol_page",
    }
    assert {w.code for w in summer_flight.warnings} & fallback_codes


def test_uncertain_cells_are_explicitly_flagged_not_silently_wrong(
    botanical_citrus: TypeBCResult,
) -> None:
    """Mandatory rule (`pdf-extraction-specialist`): every uncertain cell
    must be flagged, never silently left wrong. Checks that the flagging
    mechanism is really wired end to end (not just present in the data
    contract)."""
    assert botanical_citrus.uncertain_cells
    # Flagged by a code + parameters, never French text frozen on the server
    # (translation audit, Lot 8) — and the announced count must match exactly
    # the cells actually marked uncertain.
    uncertain_warnings = [
        w for w in botanical_citrus.warnings if w.code == "type_bc.uncertain_cells"
    ]
    assert len(uncertain_warnings) == 1
    assert uncertain_warnings[0].params["count"] == len(botanical_citrus.uncertain_cells)


@pytest.mark.parametrize(
    ("fixture_name", "max_uncertain_fraction"),
    [("botanical_citrus", 0.05), ("cucurbit", 0.10), ("winter_wreath", 0.25)],
    ids=lambda v: str(v),
)
def test_uncertain_cell_rate_stays_reasonable_not_almost_the_whole_grid(
    fixture_name: str, max_uncertain_fraction: float, request: pytest.FixtureRequest
) -> None:
    """Non-regression of Lot 5's three successive "uncertain cells" fixes.
    Before the first one, `botanical-citrus-dmc` and `cucurbit-dmc` flagged
    58% and 34% of the coloured cells as uncertain respectively
    (`1630/2802` and `642/1911`), to the point of covering almost the whole
    of some pattern areas in the wizard's brush — far more than a real
    proportion of ambiguous colours/symbols. Cause measured and fixed:
    `_color_to_rgb` converted CMYK to RGB with the naive formula recommended
    as a fallback by the PDF spec (`R=(1-C)(1-K)`...), which clearly
    oversaturates shades obtained by mixing cyan+yellow (greens in
    particular) and artificially inflated the Lab distance in DMC matching
    for several colours with a large cell population — confirmed by
    comparing this formula with the colour actually rendered by PyMuPDF for
    the same CMYK values. `_cmyk_to_rgb_via_mupdf` replaces it. An avenue
    explored at the time (loosening the bit-difference threshold of the 6x6
    bitmap then used by `_build_symbol_signatures` to absorb repositioning
    noise between signatures of the same redrawn symbol) was **abandoned**:
    at a 4-bit threshold, it wrongly merged a "+" symbol with an "up arrow"
    symbol on `botanical-citrus-dmc` (confirmed visually by rendering both
    bitmaps via `render_symbol_svg`).

    A second, deeper diagnosis showed *why* no threshold on that 6x6 bitmap
    could work: on `cucurbit-dmc`, cells carrying genuinely different symbols
    (confirmed visually) could land on the *same* 6x6 bitmap, for lack of
    sufficient resolution with only 4 to 6 vector path points per cell — an
    aliasing problem from the initial exact grouping onwards, not just a
    merge tolerance issue. `_build_symbol_signatures` now builds each cell's
    fingerprint from the real raster rendering of the symbol page (~256
    pixels per cell, cf. `_raster_fingerprint`/`_render_symbol_page_gray`)
    rather than from those few vector points, and
    `_merge_near_duplicate_signatures` compares these fingerprints with a
    shift tolerance of a few pixels and a guard on ink area. Measured after
    this second fix: 0.8% (`23/2802`) on `botanical-citrus-dmc` and 3.7%
    (`71/1911`) on `cucurbit-dmc` — a sharp drop compared with the
    20.7%/21.0% measured after the CMYK->RGB fix alone. But this second fix
    made `winter-wreath-dmc` regress from ~22% to 35% (`1221/3460`), not
    measured at the time for lack of a dedicated test on that particular
    file.

    Third diagnosis (the one that added `winter_wreath` to this
    parametrisation): `winter-wreath-dmc` is the only one of the 4 reference
    DMC files where the colour page itself already carries its symbols
    (combined colour+symbol page, adjacent cells touching, no separate white
    page overlaid). Visual rendering (`render_symbol_svg`) of several cells
    of the same canonical colour spread across the whole grid: two cells
    carrying the same symbol fell into two different groups because of a
    fragment of a **"decade" grid line** (drawn every 10 cells, much thicker
    than the minor grid — measured directly on the page's vector `lines`: up
    to ~6 px wide once rendered, versus the 4 px margin removed by
    `_RASTER_CORE_MARGIN_PX` at the time) that remained in the crop of cells
    adjacent to a decade line, and only those — see the
    `_RASTER_CORE_MARGIN_PX` docstring in `app/type_bc.py` for the full
    details of the measurements. Widened from 4 to 5 px, this margin brings
    `winter-wreath-dmc` down to 17.7% (`611/3460`) — below its rate from
    before even the switch to raster rendering — without changing
    `botanical-citrus-dmc` or `cucurbit-dmc` by a single case (still
    0.8%/3.7%, measured). The remainder of `winter-wreath-dmc` (611 cells)
    comes overwhelmingly (592/611, measured) from two shades with no close
    DMC match in the partial community catalogue (§8.5) — real uncertainty,
    independent of shape recognition, which this fix cannot and must not
    make disappear, hence a bound (0.25) much wider than that of
    `botanical-citrus-dmc`/`cucurbit-dmc`.

    The bounds below keep a comfortable margin above these measured values
    (never tightened to the point of breaking at the slightest minor
    deviation) while forbidding a regression towards a rate close to the one
    before each fix. Never checks that `uncertain_cells` is empty: part of
    the uncertainty measured here is real (a few shades out of reach of the
    partial community DMC catalogue, §8.5) and must remain flagged."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    total = sum(1 for value in result.cells if value != 0)
    fraction = len(result.uncertain_cells) / total
    assert fraction < max_uncertain_fraction
    assert result.uncertain_cells  # real, measured uncertainty must remain flagged


def _cell_index(result: TypeBCResult, row0: int, col0: int) -> int:
    return row0 * result.columns + col0


def test_cucurbit_redrawn_round_symbol_merges_despite_repositioning_noise(
    cucurbit: TypeBCResult,
) -> None:
    """Non-regression lock for the second "uncertain cells" fix
    (shift-tolerant raster comparison rather than a 6x6 bitmap, see
    `_merge_near_duplicate_signatures` in `app/type_bc.py`). The 4 cells
    below carry, measured and visually verified (`render_symbol_svg`), the
    same "O" circle redrawn with slight sub-position noise, on the
    near-white canonical colour — they must get the same palette entry (same
    colour+symbol combination), not 4 distinct entries flagged as uncertain
    for lack of a dominant match."""
    positions = [(24, 29), (22, 31), (23, 29), (21, 31)]
    indices = [_cell_index(cucurbit, row0, col0) for row0, col0 in positions]
    values = {cucurbit.cells[idx] for idx in indices}
    assert all(v != 0 for v in values), "these 4 cells must be coloured"
    assert len(values) == 1, (
        "the 4 cells of the same redrawn circle must share the same palette "
        f"entry, got: {[cucurbit.cells[idx] for idx in indices]}"
    )


def test_botanical_citrus_plus_and_arrow_symbols_never_merge(
    botanical_citrus: TypeBCResult,
) -> None:
    """Symmetric lock of the previous test: a "+" symbol and an "up arrow"
    symbol, confirmed visually distinct (`render_symbol_svg`) and at the
    same bit distance (4) as `cucurbit-dmc`'s redrawn circle on the old 6x6
    bitmap — the shift-tolerant raster comparison must never merge them,
    whatever the future tuning of `_merge_near_duplicate_signatures`'s
    thresholds."""
    plus_idx = _cell_index(botanical_citrus, 93, 52)
    arrow_idx = _cell_index(botanical_citrus, 89, 54)
    plus_value = botanical_citrus.cells[plus_idx]
    arrow_value = botanical_citrus.cells[arrow_idx]
    assert plus_value != 0
    assert arrow_value != 0
    assert plus_value != arrow_value, (
        '"+" and "up arrow" must never share the same '
        "palette entry"
    )


def test_winter_wreath_diagonal_bar_merges_across_decade_gridline(
    winter_wreath: TypeBCResult,
) -> None:
    """Non-regression lock for the third "uncertain cells" fix (raster crop
    margin widened from 4 to 5 px, see the `_RASTER_CORE_MARGIN_PX` docstring
    in `app/type_bc.py`). The 4 cells below carry, measured and visually
    verified (`render_symbol_svg`), the same diagonal bar on the same
    canonical colour (olive green) — two of them are adjacent to a "decade"
    grid line (column 10, much thicker than the minor grid) a fragment of
    which contaminated their crop before this fix, tipping them into a
    second distinct group despite an identical symbol. All 4 must get the
    same palette entry."""
    positions = [(33, 4), (58, 4), (44, 9), (31, 10)]
    indices = [_cell_index(winter_wreath, row0, col0) for row0, col0 in positions]
    values = {winter_wreath.cells[idx] for idx in indices}
    assert all(v != 0 for v in values), "these 4 cells must be coloured"
    assert len(values) == 1, (
        "the 4 cells of the same redrawn diagonal bar must share the same "
        f"palette entry, got: {[winter_wreath.cells[idx] for idx in indices]}"
    )
    assert not (set(indices) & set(winter_wreath.uncertain_cells))


def test_confidence_reflects_the_type_b_fallback_penalty(
    summer_flight: TypeBCResult,
) -> None:
    """`detect_type_bc` always subtracts 0.2 from the confidence when shape
    recognition honestly falls back to type B (see the `confidence -= 0.2`
    block of `detect_type_bc`) — confidence can therefore never exceed 0.8
    in that case, whatever the rate of uncertain cells (which can only lower
    it further, never raise it). Comparing `summer_flight.confidence`
    directly with another fixture's (`winter_wreath` in particular) is no
    longer reliable since Lot 5's CMYK->RGB fix (uncertain cells): both
    fixtures share the same 228-shade community DMC palette, whose coverage
    varies independently of the file template from one fixture to another
    (measured: `winter-wreath-dmc` drops slightly in confidence after that
    fix despite perfectly reliable shape recognition, simply because two of
    its shades have no close DMC match in this necessarily partial
    catalogue) — only the fallback mechanism itself, not a raw comparison
    between fixtures, is a robust guarantee here."""
    assert summer_flight.confidence <= 0.8


def _tiny_non_type_bc_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 100), "Just a plain PDF, not a pattern export.")
    path = tmp_path / "not-type-bc.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    return path


def test_returns_none_for_non_type_bc_pdf(tmp_path: Path) -> None:
    assert detect_type_bc(_tiny_non_type_bc_pdf(tmp_path)) is None


def test_never_raises_on_empty_pdf(tmp_path: Path) -> None:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page(width=300, height=200)
    path = tmp_path / "empty.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    assert detect_type_bc(path) is None


@pytest.mark.parametrize("path", OTHER_TYPE_FIXTURES, ids=lambda p: p.parent.name)
def test_returns_none_for_other_fixture_types(path: Path) -> None:
    """Type A (embedded symbol font) and type E (catalogue of reused bitmap
    images, `river-and-mountains-laserarts`): no B/C false positive.
    `river-and-mountains-laserarts` is an extra trap case for this
    particular connector: its grid pages also carry a dressing of background
    rectangles per cell (publisher template), which would make it eligible as
    a B/C colour page if the presence of bitmap images were not checked
    first."""
    if not path.is_file():
        pytest.skip(f"fixture manquante : {path}")
    assert detect_type_bc(path) is None


@pytest.mark.parametrize("path", DMC_FIXTURES, ids=lambda p: p.parent.name)
def test_runs_within_reasonable_time(path: Path) -> None:
    """Generous performance benchmark (specification §10: "under 30 seconds"
    for a 10-page PDF) — see the task report for the precise times measured
    per fixture."""
    start = time.perf_counter()
    detect_type_bc(path)
    assert time.perf_counter() - start < 30.0
