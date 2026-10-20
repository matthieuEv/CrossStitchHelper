"""Instance health endpoint.

Used by three audiences: the frontend home screen (to show "server
reachable"), the self-hosting user (to check their installation), and
``docker compose`` via its ``healthcheck``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import AppMeta
from app.schema import SCHEMA_FINGERPRINT_KEY

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str = Field(description="`ok` if the instance is fully functional.")
    version: str = Field(description="Backend version.")
    database: str = Field(description="`ok` if the database responds to reads.")
    schema_revision: str | None = Field(
        default=None,
        description=(
            "Fingerprint of the models the schema was created from "
            "(`app/schema.py`), or null if the schema was never created."
        ),
    )


@router.get("/health", response_model=HealthResponse, summary="Instance status")
def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    try:
        # A real query on a real table: checks that the database responds to
        # reads, not just that the file exists.
        session.execute(select(AppMeta).limit(1)).first()
        database = "ok"
    except SQLAlchemyError:
        database = "error"

    try:
        stored = session.get(AppMeta, SCHEMA_FINGERPRINT_KEY)
        schema_revision = stored.value if stored is not None else None
    except SQLAlchemyError:
        schema_revision = None

    return HealthResponse(
        status="ok" if database == "ok" and schema_revision is not None else "degraded",
        version=get_settings().app_version,
        database=database,
        schema_revision=schema_revision,
    )
