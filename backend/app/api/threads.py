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


@router.get("/dmc", response_model=list[ThreadShadeOut], summary="DMC colour chart")
def list_dmc_shades() -> list[ThreadShadeOut]:
    return [
        ThreadShadeOut(code=code, name=name, rgb_hex=rgb_hex)
        for code, name, rgb_hex in catalog_entries()
    ]
