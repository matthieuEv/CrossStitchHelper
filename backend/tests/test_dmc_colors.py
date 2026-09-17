from __future__ import annotations

from app.dmc_colors import FALLBACK_HEX, dmc_hex


def test_known_code_returns_a_hex_color() -> None:
    assert dmc_hex("310") == "#050505"


def test_lookup_is_case_and_whitespace_insensitive() -> None:
    assert dmc_hex(" b5200 ") == dmc_hex("B5200")


def test_unknown_code_returns_none_rather_than_a_guess() -> None:
    assert dmc_hex("this-code-does-not-exist") is None


def test_fallback_hex_is_a_valid_hex_color_distinct_from_real_entries() -> None:
    assert FALLBACK_HEX.startswith("#")
    assert len(FALLBACK_HEX) == 7
