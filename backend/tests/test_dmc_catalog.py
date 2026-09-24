"""Tests for `app/dmc_catalog.py`, in particular `nearest_dmc_among` (Lot 7) —
never exercised by the `river-and-mountains-laserarts` fixture itself (see
`app/type_e.py`: the colour fallback is never triggered there, the exact
count is enough on that file), so verified here directly rather than only
indirectly through a connector."""

from __future__ import annotations

from app.dmc_catalog import nearest_dmc, nearest_dmc_among


def test_nearest_dmc_among_restricts_to_the_given_codes() -> None:
    # Almost black: the unrestricted nearest neighbour would be "310"
    # (Black), but restricted to a set that does not contain it, another
    # dark code must be chosen instead.
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
    assert match.code == "BLANC"  # returns the code as requested, not the lowercase internal key


def test_nearest_dmc_among_returns_none_when_no_code_is_known() -> None:
    assert nearest_dmc_among((0.5, 0.5, 0.5), {"ce-code-n-existe-pas"}) is None


def test_nearest_dmc_among_returns_none_for_empty_codes() -> None:
    assert nearest_dmc_among((0.5, 0.5, 0.5), set()) is None
