"""Tests for `app/fingerprint.py` (Lot 6) against the six reference
fixtures — see `fixtures/README.md`.

The only result verifiable without a genuine "same publisher, different
file" pair produced by third parties is the one already observed on this
fixture set: `botanical-citrus-dmc` and `cucurbit-dmc` are two official
4-page DMC charts with the same export template — the fingerprint must
recognise them as identical. `winter-wreath-dmc` and `summer-flight-dmc`
deliberately use a different DMC template (5 pages, different internal
structure, specification §4.1): their fingerprint must stay distinct from
the pair above and from each other. `cafe-brasserie-charting-export`
(third-party software, not DMC) and `river-and-mountains-laserarts`
(a different third-party publisher) must each remain isolated."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.fingerprint import compute_fingerprint

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"

CAFE_BRASSERIE = (
    FIXTURES_ROOT / "cafe-brasserie-charting-export" / "CaffeBrasseriecoloursymbols.pdf"
)
BOTANICAL_CITRUS = FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf"
CUCURBIT = FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf"
WINTER_WREATH = FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf"
SUMMER_FLIGHT = FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf"
RIVER_AND_MOUNTAINS = FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf"

ALL_FIXTURES = [
    CAFE_BRASSERIE,
    BOTANICAL_CITRUS,
    CUCURBIT,
    WINTER_WREATH,
    SUMMER_FLIGHT,
    RIVER_AND_MOUNTAINS,
]


def test_same_dmc_export_template_gets_the_same_fingerprint() -> None:
    assert compute_fingerprint(BOTANICAL_CITRUS, "pdf") == compute_fingerprint(CUCURBIT, "pdf")


@pytest.mark.parametrize(
    "path",
    [CAFE_BRASSERIE, WINTER_WREATH, SUMMER_FLIGHT, RIVER_AND_MOUNTAINS],
    ids=lambda p: p.parent.name,
)
def test_different_editors_or_templates_get_distinct_fingerprints(path: Path) -> None:
    reference = compute_fingerprint(BOTANICAL_CITRUS, "pdf")
    assert compute_fingerprint(path, "pdf") != reference


def test_all_six_fixtures_collapse_into_exactly_five_distinct_fingerprints() -> None:
    fingerprints = {compute_fingerprint(path, "pdf") for path in ALL_FIXTURES}
    assert len(fingerprints) == 5


def test_fingerprint_is_stable_across_repeated_calls() -> None:
    first = compute_fingerprint(CAFE_BRASSERIE, "pdf")
    second = compute_fingerprint(CAFE_BRASSERIE, "pdf")
    assert first is not None
    assert first == second


def test_non_pdf_kind_has_no_fingerprint() -> None:
    assert compute_fingerprint(CAFE_BRASSERIE, "image") is None


def test_unreadable_file_never_raises(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a real pdf")
    assert compute_fingerprint(broken, "pdf") is None
