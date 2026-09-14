"""Point de santé de l'instance.

Utilisé par trois publics : l'écran d'accueil du frontend (pour afficher
« serveur joignable »), l'utilisateur qui auto-héberge (pour vérifier son
installation), et ``docker compose`` via son ``healthcheck``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_session
from app.models import AppMeta

router = APIRouter(tags=["système"])


class HealthResponse(BaseModel):
    status: str = Field(description="`ok` si l'instance est pleinement fonctionnelle.")
    version: str = Field(description="Version du backend.")
    database: str = Field(description="`ok` si la base répond en lecture.")
    schema_revision: str | None = Field(
        default=None,
        description="Révision Alembic appliquée, ou null si aucune migration n'a tourné.",
    )


@router.get("/health", response_model=HealthResponse, summary="État de l'instance")
def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    try:
        # Une vraie requête sur une vraie table : vérifie que la base répond en
        # lecture, pas seulement que le fichier existe.
        session.execute(select(AppMeta).limit(1)).first()
        database = "ok"
    except SQLAlchemyError:
        database = "erreur"

    try:
        row = session.execute(text("SELECT version_num FROM alembic_version")).first()
        schema_revision = str(row[0]) if row is not None else None
    except SQLAlchemyError:
        schema_revision = None

    return HealthResponse(
        status="ok" if database == "ok" and schema_revision is not None else "degraded",
        version=__version__,
        database=database,
        schema_revision=schema_revision,
    )
