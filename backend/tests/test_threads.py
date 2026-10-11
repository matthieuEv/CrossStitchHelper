"""DMC colour chart endpoint (issue #39): what the import wizard relies on to
fill in a colour and its name from a typed code."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.dmc_catalog import catalog_entries


def test_dmc_chart_lists_the_whole_catalogue(client: TestClient) -> None:
    response = client.get("/api/threads/dmc")
    assert response.status_code == 200
    shades = response.json()
    assert len(shades) == len(catalog_entries())
    by_code = {shade["code"]: shade for shade in shades}
    # The issue's own example, and the two lettered codes.
    assert by_code["3820"] == {"code": "3820", "name": "Straw-Dark", "rgb_hex": "#daa520"}
    assert by_code["310"]["name"] == "Black"
    assert "ecru" in by_code and "b5200" in by_code


def test_dmc_chart_codes_are_unique_and_colours_valid(client: TestClient) -> None:
    shades = client.get("/api/threads/dmc").json()
    codes = [shade["code"] for shade in shades]
    assert len(codes) == len(set(code.lower() for code in codes))
    for shade in shades:
        assert len(shade["rgb_hex"]) == 7 and shade["rgb_hex"].startswith("#")
        int(shade["rgb_hex"][1:], 16)
