"""Tests de `app/dmc_catalog.py`, en particulier `nearest_dmc_among` (Lot 7) —
jamais exercé par la fixture `river-and-mountains-laserarts` elle-même (voir
`app/type_e.py` : le repli couleur n'y est jamais déclenché, le comptage
exact suffit sur ce fichier), donc vérifié ici directement plutôt que
seulement de façon indirecte via un connecteur."""

from __future__ import annotations

from app.dmc_catalog import nearest_dmc, nearest_dmc_among


def test_nearest_dmc_among_restricts_to_the_given_codes() -> None:
    # Presque noir : le plus proche voisin sans restriction serait "310"
    # (Noir), mais restreint à un ensemble qui ne le contient pas, un autre
    # code sombre doit être choisi à la place.
    near_black = (0.02, 0.02, 0.02)
    unrestricted = nearest_dmc(near_black)
    assert unrestricted.code == "310"

    restricted = nearest_dmc_among(near_black, {"666", "n/a-inexistant"})
    assert restricted is not None
    assert restricted.code == "666"
    assert restricted.distance > unrestricted.distance


def test_nearest_dmc_among_is_case_insensitive_on_codes() -> None:
    match = nearest_dmc_among((0.0, 0.0, 0.0), {"BLANC"})
    assert match is not None
    assert match.code == "BLANC"  # renvoie le code tel que demandé, pas la clé interne en minuscule


def test_nearest_dmc_among_returns_none_when_no_code_is_known() -> None:
    assert nearest_dmc_among((0.5, 0.5, 0.5), {"ce-code-n-existe-pas"}) is None


def test_nearest_dmc_among_returns_none_for_empty_codes() -> None:
    assert nearest_dmc_among((0.5, 0.5, 0.5), set()) is None
