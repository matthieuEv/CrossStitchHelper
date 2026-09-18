"""Tests de `app/fingerprint.py` (Lot 6) contre les six fixtures de
référence — voir `fixtures/README.md`.

Le seul résultat vérifiable sans une véritable paire "même éditeur, fichier
différent" fabriquée par des tiers est celui déjà observé sur ce jeu de
fixtures : `botanical-citrus-dmc` et `cucurbit-dmc` sont deux grilles DMC
officielles de 4 pages, même gabarit d'export — l'empreinte doit les
reconnaître comme identiques. `winter-wreath-dmc` et `summer-flight-dmc`
sont volontairement d'un gabarit DMC différent (5 pages, structure interne
différente, cahier des charges §4.1) : leur empreinte doit rester distincte
de la paire ci-dessus et l'une de l'autre. `cafe-brasserie-charting-export`
(logiciel tiers, pas DMC) et `river-and-mountains-laserarts` (éditeur tiers
différent) doivent chacun rester isolés."""

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
