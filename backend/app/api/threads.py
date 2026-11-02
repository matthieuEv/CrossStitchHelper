"""Thread colour charts — read-only (issue #39).

Serves the DMC catalogue already used for Lab matching (`app/dmc_catalog.py`)
so the import wizard can fill in a colour and its name from a typed code.
DMC only: it is the only brand the app knows (specification §7, "DMC by
default"); supporting other brands is still an open question
(`docs/features-and-limits.md`).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dmc_catalog import catalog_entries
from app.schemas import ThreadShadeOut

router = APIRouter(prefix="/threads", tags=["threads"])


def _chart_order(position: int, code: str) -> tuple[int, int]:
    """Sort key putting shades in the order of a printed DMC chart: the
    named whites first (blanc, white, b5200, ecru, in catalogue order), then
    the numbered shades by number, then the Light Effects (`e…`) by number.
    The catalogue itself is grouped by hue, which made the wizard's code
    suggestions look shuffled (issue #39 review)."""
    if code.isdigit():
        return (1, int(code))
    if code[:1].lower() == "e" and code[1:].isdigit():
        return (2, int(code[1:]))
    return (0, position)


@router.get("/dmc", response_model=list[ThreadShadeOut], summary="DMC colour chart")
def list_dmc_shades() -> list[ThreadShadeOut]:
    entries = sorted(
        enumerate(catalog_entries()),
        key=lambda item: _chart_order(item[0], item[1][0]),
    )
    return [
        ThreadShadeOut(code=code, name=name, rgb_hex=rgb_hex)
        for _, (code, name, rgb_hex) in entries
    ]
