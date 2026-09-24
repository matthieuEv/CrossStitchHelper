"""Full backup/restore routes (Lot 8, specification §7.5).

Distinct from `app/api/patterns.py::export_pattern` (`.cshp`, a single
pattern): here, the whole instance as one JSON document (`app/backup.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auto_backup import is_auto_backup_enabled, set_auto_backup_enabled
from app.backup import BackupFormatError, build_backup, restore_backup
from app.db import get_session
from app.http import api_error, content_disposition
from app.schemas import AutoBackupSettings, BackupDocument, BackupRestoreSummary

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get(
    "",
    summary="Full data export (JSON, open format)",
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
    summary="Full restore — replaces all existing data",
)
def restore(
    document: BackupDocument, session: Annotated[Session, Depends(get_session)]
) -> BackupRestoreSummary:
    try:
        return restore_backup(session, document)
    except BackupFormatError as error:
        raise api_error(400, error.code, **error.params) from error


@router.get(
    "/auto",
    response_model=AutoBackupSettings,
    summary="Daily automatic backup setting",
)
def get_auto_backup(session: Annotated[Session, Depends(get_session)]) -> AutoBackupSettings:
    return AutoBackupSettings(enabled=is_auto_backup_enabled(session))


@router.put(
    "/auto",
    response_model=AutoBackupSettings,
    summary="Enable or disable the daily automatic backup",
)
def put_auto_backup(
    payload: AutoBackupSettings, session: Annotated[Session, Depends(get_session)]
) -> AutoBackupSettings:
    set_auto_backup_enabled(session, payload.enabled)
    return payload
