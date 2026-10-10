"""Tests for the type B/C extraction engine (Lot 5, issue #44) against the
four real DMC fixtures — see `fixtures/README.md` and the
`.claude/skills/verify-extraction-fixtures/` skill.

Since issue #44, the palette comes from each file's **text legend**
(specification §8.5: when the legend provides the codes as text, they are
authoritative): one palette entry per legend code actually used on the
grid, never one per (colour x symbol variant) pair, never a code from the
nearest shade of the community catalogue. The expected codes below are read
from each fixture's legend page (checked visually on the rendered page), not
from the extraction under test: 14 codes for `winter-wreath-dmc`, 12 for
`summer-flight-dmc`, 17 for `botanical-citrus-dmc`, 18 for `cucurbit-dmc` —
all of them used on the grid, measured (each grid colour equals one legend
swatch's fill, Lab distance <= 1.1 except `summer-flight-dmc`'s 07 at 5.8;
the "6 unused swatches" once documented for `cucurbit-dmc` was not
confirmed by measurement).

`summer-flight-dmc` is Lot 5's trap case (§4.3): its colour page itself
already carries the symbols, so a second page must never be blindly
overlaid. Issue #44 also measured that its colour page draws, on top of each
cell's real fill, a thin outline frame (darkened shade of the cell colour,
or neutral grey) whose inner hole is a smaller square: taken for fills,
those frames made the pitch 5.734 pt instead of 6.059 pt (a 90 x 90 grid
instead of the real 85 x 85, with empty rows/columns inserted) and replaced
the real colour of hundreds of cells — the "richly shaded illustration"
once assumed here was that artefact. With the frames recognised, it has
exactly its 12 legend colours and its own-page symbols are reliable enough
for type C (glyphs read from page 1, never page 2)."""

from __future__ import annotations

import time
from pathlib import Path

import pdfplumber
import pymupdf
import pytest

from app import type_bc
from app.dmc_catalog import nearest_dmc
from app.type_bc import TypeBCResult, detect_type_bc

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"

WINTER_WREATH = FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf"
BOTANICAL_CITRUS = FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf"
CUCURBIT = FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf"
SUMMER_FLIGHT = FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf"

DMC_FIXTURES = [WINTER_WREATH, BOTANICAL_CITRUS, CUCURBIT, SUMMER_FLIGHT]

# Codes printed in each fixture's full-stitch legend, as printed (read on
# the rendered legend page — see the module docstring).
LEGEND_CODES = {
    "winter_wreath": {
        "3345", "3346", "471", "472", "11", "18", "3821",
        "726", "3853", "3854", "blanc", "351", "814", "E321",
    },
    "summer_flight": {
        "blanc", "07", "08", "09", "352", "3854", "3820", "19", "3822", "3823", "11", "369",
    },
    "botanical_citrus": {
        "Blanc", "10", "445", "307", "18", "444", "3819", "972", "733",
        "562", "703", "970", "3816", "702", "947", "561", "3818",
    },
    "cucurbit": {
        "Blanc", "746", "3865", "3078", "677", "743", "644", "738", "742",
        "3782", "741", "703", "970", "562", "947", "561", "900", "500",
    },
}
ALL_DMC_FIXTURE_NAMES = sorted(LEGEND_CODES)

# The two fixtures of another type (specification §4.4): `detect_type_bc`
# must cleanly step aside on them, as `detect_type_a` steps aside on the
# B/C/E fixtures (see `test_type_a.py`).
OTHER_TYPE_FIXTURES = [
    FIXTURES_ROOT / "cafe-brasserie-charting-export" / "CaffeBrasseriecoloursymbols.pdf",
    FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf",
]


def _distinct_colors(result: TypeBCResult) -> int:
    """Number of distinct colours actually present in the palette — in the
    catalogue fallback (no usable legend), several entries can share the same
    colour in type C (one per symbol variant), hence distinct from
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


def test_summer_flight_has_exactly_its_legend_colours(summer_flight: TypeBCResult) -> None:
    """Issue #44: once its per-cell outline frames are no longer taken for
    fills (see the module docstring), `summer-flight-dmc` has exactly the 12
    colours of its "cross stitch" legend — not the 22 "shades" measured
    before, which were darkened outline rings drawn after the real fill."""
    assert _distinct_colors(summer_flight) == 12


def test_summer_flight_grid_pitch_ignores_outline_frames(summer_flight: TypeBCResult) -> None:
    """Issue #44: the real cells are 6.059 pt fills tiled at a 6.059 pt step
    inside a 515.1 x 514.4 pt border, i.e. 85 x 85 — the inner squares of
    the outline frames (5.734 pt, more numerous than the fills) used to make
    the size-based pitch estimate report 90 x 90."""
    assert (summer_flight.columns, summer_flight.rows) == (85, 85)


def test_summer_flight_background_layer_is_still_excluded(summer_flight: TypeBCResult) -> None:
    """The neutral grey layer covering most of the grid is still excluded
    (never a thread), but no longer hides the real fill drawn under it."""
    assert "type_bc.background_color_excluded" in {w.code for w in summer_flight.warnings}


@pytest.mark.parametrize(
    "fixture_name", ["winter_wreath", "summer_flight"], ids=lambda n: n.replace("_", "-")
)
def test_symbols_reused_from_the_colour_page_itself(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Measured case (§4.3): the colour page of `winter-wreath-dmc` and of
    the trap case `summer-flight-dmc` itself already carries the symbols — no
    separate page is needed, and the connector must measure that rather than
    assume the "page 1 colour only / page 2 symbols" structure. Page 2 of
    these files (a black-and-white duplicate) is never overlaid."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    assert result.grid_type == "C"
    glyphs = [e.symbol_glyph for e in result.palette if e.symbol_glyph is not None]
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


@pytest.mark.parametrize("fixture_name", ALL_DMC_FIXTURE_NAMES, ids=lambda n: n.replace("_", "-"))
def test_palette_codes_are_the_legend_codes_actually_used(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Issue #44, specification §8.5: the legend's codes are authoritative.
    Before, `winter-wreath-dmc` came out with 40 entries, most of them codes
    absent from its legend (469, 319, 470, 321...), and `botanical-citrus-dmc`
    with 17 entries of which only 3 were real legend codes. Every code must
    now come from the legend, and on these four files every legend colour is
    used on the grid (measured)."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    codes = [entry.code for entry in result.palette]
    assert set(codes) == LEGEND_CODES[fixture_name]


@pytest.mark.parametrize("fixture_name", ALL_DMC_FIXTURE_NAMES, ids=lambda n: n.replace("_", "-"))
def test_one_palette_entry_per_code_never_duplicated(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Issue #44: a thread whose cells carry several symbol variants (a
    backstitch line crossing the symbol, a French knot on top) used to become
    several palette entries with the same code (`winter-wreath-dmc`: 470 x6,
    938 x7, 3853 x7...). One entry per code, and every coloured cell keeps a
    palette entry."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    codes = [entry.code.lower() for entry in result.palette]
    assert len(codes) == len(set(codes))
    used = {value for value in result.cells if value != 0}
    assert used == set(range(1, len(result.palette) + 1))


@pytest.mark.parametrize("fixture_name", ALL_DMC_FIXTURE_NAMES, ids=lambda n: n.replace("_", "-"))
def test_uncertain_cells_warning_matches_flagged_cells(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """On every DMC fixture, the `type_bc.uncertain_cells` warning is present
    exactly when cells are flagged, and announces exactly their number —
    merging a thread's symbol variants into one entry (issue #44) must never
    make flagged cells disappear from the banner. (The cells actually flagged
    on `winter-wreath-dmc`/`summer-flight-dmc` were checked on the rendered
    page: symbols crossed by a backstitch line or a French knot.)"""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    counts = [w.params["count"] for w in result.warnings if w.code == "type_bc.uncertain_cells"]
    assert counts == ([len(result.uncertain_cells)] if result.uncertain_cells else [])


def test_summer_flight_colour_off_its_swatch_is_flagged(summer_flight: TypeBCResult) -> None:
    """Never a silent wrong value: `summer-flight-dmc`'s 07 cells are 5.8
    Lab units from the legend's 07 swatch (every other grid colour of the
    four fixtures is within 1.1) — still assigned to 07 (the next code is 25
    units away), but every one of those cells is flagged and announced."""
    index_07 = next(i for i, e in enumerate(summer_flight.palette, start=1) if e.code == "07")
    cells_07 = {i for i, value in enumerate(summer_flight.cells) if value == index_07}
    assert cells_07
    assert cells_07 <= set(summer_flight.uncertain_cells)
    dmc_warnings = [w for w in summer_flight.warnings if w.code == "type_bc.uncertain_dmc_match"]
    assert [w.params["count"] for w in dmc_warnings] == [1]


@pytest.mark.parametrize(
    "fixture_name",
    ["winter_wreath", "botanical_citrus", "cucurbit"],
    ids=lambda n: n.replace("_", "-"),
)
def test_exact_legend_matches_raise_no_dmc_warning(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Every grid colour of these three files is its legend swatch's exact
    fill: no doubtful-match warning (before issue #44, two of
    `winter-wreath-dmc`'s colours had no close shade in the community
    catalogue and flagged 592 cells for nothing)."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    assert "type_bc.uncertain_dmc_match" not in {w.code for w in result.warnings}


@pytest.mark.parametrize(
    "fixture_name", ["winter_wreath", "summer_flight"], ids=lambda n: n.replace("_", "-")
)
def test_uncertain_cells_are_explicitly_flagged_not_silently_wrong(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Mandatory rule (`pdf-extraction-specialist`): every uncertain cell
    must be flagged, never silently left wrong. Checks that the flagging
    mechanism is really wired end to end (not just present in the data
    contract), on the two fixtures that still have real uncertainty since
    issue #44 (symbol variants caused by backstitch lines crossing cells,
    and `summer-flight-dmc`'s 07 colour off its swatch) —
    `botanical-citrus-dmc`, used here before, no longer has any: its only
    uncertainty came from the community catalogue's distance, gone now that
    its legend gives the exact codes."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    assert result.uncertain_cells
    # Flagged by a code + parameters, never French text frozen on the server
    # (translation audit, Lot 8) — and the announced count must match exactly
    # the cells actually marked uncertain.
    uncertain_warnings = [w for w in result.warnings if w.code == "type_bc.uncertain_cells"]
    assert len(uncertain_warnings) == 1
    assert uncertain_warnings[0].params["count"] == len(result.uncertain_cells)


@pytest.mark.parametrize(
    ("fixture_name", "max_uncertain_fraction"),
    [
        ("botanical_citrus", 0.05),
        ("cucurbit", 0.10),
        ("winter_wreath", 0.05),
        ("summer_flight", 0.40),
    ],
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
    before each fix.

    Issue #44 (legend-authoritative codes): the remaining uncertainty is
    now only real ambiguity. Measured: `botanical-citrus-dmc` 0/2802 and
    `cucurbit-dmc` 0/1911 (each grid colour is exactly its legend swatch and
    carries a single symbol group — their former 23 and 71 uncertain cells
    were one catalogue colour each with no close community shade);
    `winter-wreath-dmc` 38/3460 (cells crossed by a backstitch line, so
    their symbol differs from their thread's dominant one — checked on the
    rendered cells); `summer-flight-dmc` 230/766 (its 37 cells of 07, off
    their swatch, plus symbol variants: backstitch lines and French knots
    over many of its small cells, and thread 369 whose cells have no
    dominant symbol group above 60%)."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    total = sum(1 for value in result.cells if value != 0)
    fraction = len(result.uncertain_cells) / total
    assert fraction < max_uncertain_fraction


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
    # Since issue #44 an entry groups a whole thread whatever its symbol: the
    # merge of the redrawn circle is now checked through the absence of any
    # "symbol differs from the dominant one" flag on these cells.
    assert not (set(indices) & set(cucurbit.uncertain_cells))


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


@pytest.mark.parametrize("fixture_name", ALL_DMC_FIXTURE_NAMES, ids=lambda n: n.replace("_", "-"))
def test_confidence_reflects_the_uncertain_cell_rate(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """`detect_type_bc` subtracts the uncertain-cell rate (capped at 0.4)
    from the confidence: it can never exceed 1 minus that rate. (Before
    issue #44 this test checked `summer-flight-dmc`'s type B fallback
    penalty; that file is now a reliable type C, see the module
    docstring.)"""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    total = sum(1 for value in result.cells if value != 0)
    rate = len(result.uncertain_cells) / total
    assert result.confidence <= 1.0 - min(0.4, rate) + 1e-9


def test_without_a_usable_legend_the_catalogue_fallback_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never block an import for lack of a legend: when `_parse_legend`
    finds nothing usable, the historical assembly (codes from the nearest
    community-catalogue shade, one entry per colour x symbol pair, Lot 5) is
    used as is — checked on a real fixture with the legend parser disabled."""
    monkeypatch.setattr(type_bc, "_parse_legend", lambda pages: [])
    result = detect_type_bc(WINTER_WREATH)
    assert result is not None
    assert result.grid_type == "C"
    assert _distinct_colors(result) == 14
    # Catalogue codes, one entry per (colour x symbol) pair: more entries
    # than colours, codes absent from the legend (what issue #44 reported).
    assert len(result.palette) > 14
    for entry in result.palette:
        rgb = tuple(int(entry.rgb_hex[i : i + 2], 16) / 255 for i in (1, 3, 5))
        assert entry.code == nearest_dmc((rgb[0], rgb[1], rgb[2])).code


def test_a_misread_legend_layout_is_rejected_rather_than_trusted() -> None:
    """Structural counter-example measured on the type A fixture (never
    handed to `detect_type_bc` in practice — `detect_type_a` wins first): in
    its legend, the word nearest to each colour swatch is the strand count
    `2`, not the DMC code. The same "code" next to many different swatch
    colours means the layout was misread: the whole legend must be rejected
    (catalogue fallback) rather than collapse every colour into code "2"."""
    path = OTHER_TYPE_FIXTURES[0]
    if not path.is_file():
        pytest.skip(f"fixture manquante : {path}")
    with pdfplumber.open(path) as pdf:
        infos = [type_bc._analyze_page(page) for page in pdf.pages]
        pages = type_bc._legend_candidate_pages(infos, set())
        assert pages  # its legend pages are candidates...
        assert type_bc._parse_legend(pages) == []  # ...but never trusted


@pytest.mark.parametrize(
    ("fixture_name", "legend_size"),
    [("winter_wreath", 14), ("summer_flight", 12), ("botanical_citrus", 17), ("cucurbit", 18)],
    ids=lambda v: str(v).replace("_", "-"),
)
def test_legend_parser_reads_every_full_stitch_row(fixture_name: str, legend_size: int) -> None:
    """The legend is located by structure (code text right of a filled
    square swatch, no word in between), never by page number: every
    full-stitch row of each DMC legend is read, with its printed code, and
    nothing else (backstitch rows, skein counts, footers)."""
    path = {
        "winter_wreath": WINTER_WREATH,
        "summer_flight": SUMMER_FLIGHT,
        "botanical_citrus": BOTANICAL_CITRUS,
        "cucurbit": CUCURBIT,
    }[fixture_name]
    with pdfplumber.open(path) as pdf:
        infos = [type_bc._analyze_page(page) for page in pdf.pages]
        pages = type_bc._legend_candidate_pages(infos, {0, 1})
        legend = type_bc._parse_legend(pages)
    assert len(legend) == legend_size
    assert {entry.code for entry in legend} == LEGEND_CODES[fixture_name]


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
