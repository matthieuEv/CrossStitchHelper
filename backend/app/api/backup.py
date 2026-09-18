"""Routes de sauvegarde/restauration complète (Lot 8, cahier des charges §7.5).

Distinct de `app/api/patterns.py::export_pattern` (`.cshp`, un seul motif) :
ici, toute l'instance en un document JSON (`app/backup.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auto_backup import is_auto_backup_enabled, set_auto_backup_enabled
from app.backup import BackupFormatError, build_backup, restore_backup
from app.db import get_session
from app.http import content_disposition
from app.schemas import AutoBackupSettings, BackupDocument, BackupRestoreSummary

router = APIRouter(prefix="/backup", tags=["sauvegarde"])


@router.get(
    "",
    summary="Export complet des données (JSON, format ouvert)",
    response_class=Response,
)
def export_backup(session: Annotated[Session, Depends(get_session)]) -> Response:
    document = build_backup(session)
    filename = f"crossstitchhelper-{datetime.now(UTC):%Y-%m-%d}.json"
    return Response(
        content=document.model_dump_json(),
        media_type="application/json",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post(
    "/restore",
    response_model=BackupRestoreSummary,
    summary="Restauration complète — remplace toutes les données existantes",
)
def restore(
    document: BackupDocument, session: Annotated[Session, Depends(get_session)]
) -> BackupRestoreSummary:
    try:
        return restore_backup(session, document)
    except BackupFormatError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get(
    "/auto",
    response_model=AutoBackupSettings,
    summary="Réglage de la sauvegarde automatique quotidienne",
)
def get_auto_backup(session: Annotated[Session, Depends(get_session)]) -> AutoBackupSettings:
    return AutoBackupSettings(enabled=is_auto_backup_enabled(session))


@router.put(
    "/auto",
    response_model=AutoBackupSettings,
    summary="Active ou désactive la sauvegarde automatique quotidienne",
)
def put_auto_backup(
    payload: AutoBackupSettings, session: Annotated[Session, Depends(get_session)]
) -> AutoBackupSettings:
    set_auto_backup_enabled(session, payload.enabled)
    return payload
