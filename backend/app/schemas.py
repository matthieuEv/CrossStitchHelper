"""Schémas Pydantic de l'API (cahier des charges §9)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PaletteEntryOut(BaseModel):
    index_in_grid: int
    brand: str
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_svg: str | None = None
    strands_full: int | None = None
    strands_back: int | None = None
    count_full: int
    count_half: int
    count_quarter: int
    count_french: int
    count_beads: int
    backstitch_length_cm: float | None = None

    model_config = {"from_attributes": True}


class PatternSummary(BaseModel):
    """Ce qu'il faut pour une vignette de la bibliothèque (§7.1)."""

    id: str
    name: str
    width: int
    height: int
    palette_count: int
    stitched_count: int
    cell_count: int
    percent: int
    created_at: datetime
    updated_at: datetime


class PatternDetail(BaseModel):
    id: str
    owner_id: str | None
    name: str
    source_filename: str | None
    fabric_count: int | None
    width: int
    height: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    palette: list[PaletteEntryOut]

    model_config = {"from_attributes": True}


class BackstitchSegment(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    palette_index: int


class FrenchKnot(BaseModel):
    x: float
    y: float
    palette_index: int


class GridOut(BaseModel):
    pattern_id: str
    width: int
    height: int
    encoding: str
    version: int
    layer_full: str = Field(description="Uint16Array encodée en base64, ligne par ligne.")
    layer_half: str | None = None
    layer_quarter: str | None = None
    backstitch: list[BackstitchSegment]
    french_knots: list[FrenchKnot]


class ProgressOut(BaseModel):
    pattern_id: str
    version: int
    stitched_count: int
    cell_count: int
    bitmap: str = Field(description="1 bit par case, encodé en base64, ligne par ligne.")


class ProgressOp(BaseModel):
    """Une modification de case, exprimée en état absolu — donc idempotente
    (cahier des charges §9 : « cocher une case est une opération idempotente,
    ce qui rend les conflits triviaux à résoudre »)."""

    index: int = Field(ge=0)
    stitched: bool


class ProgressSyncRequest(BaseModel):
    base_version: int = Field(ge=0, description="Dernière version de progression connue du client.")
    ops: list[ProgressOp] = Field(default_factory=list)


class ProgressSyncResponse(BaseModel):
    version: int
    stitched_count: int
    conflict: bool = Field(
        description="Vrai si le client avait manqué des changements faits par un autre appareil."
    )
    missing_ops: list[ProgressOp] = Field(
        description=(
            "Opérations appliquées par d'autres appareils depuis `base_version`, "
            "à rejouer côté client."
        )
    )
