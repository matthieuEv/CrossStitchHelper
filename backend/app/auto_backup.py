"""Daily automatic backup (Lot 8, specification §7.5).

Writes a snapshot of `app.backup.build_backup` to disk, in
`Settings.backups_dir`, at a regular interval: no new infrastructure
dependency (no external scheduler — `CLAUDE.md`: "no multi-service
installation"), just an asyncio loop running as a background task of the
application process, started and stopped with the FastAPI lifecycle
(`app/main.py`).

Can be toggled by the user (`AppMeta`, settings §7.5) — a server setting,
never a browser-local preference (`frontend/src/screens/SettingsScreen.tsx`),
so that it applies even if nobody opens the application that day.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.backup import build_backup
from app.models import AppMeta

logger = logging.getLogger(__name__)

_ENABLED_KEY = "auto_backup_enabled"
_FILENAME_FORMAT = "backup-%Y-%m-%dT%H-%M-%S-%f.json"
"""Microseconds included: two writes within the same second (quick container
restart, or the test loop with a shortened interval) must never silently
overwrite each other."""
_FILENAME_GLOB = "backup-*.json"

RETENTION = 14
"""Number of automatic snapshots kept — beyond that, the oldest are deleted
on every new write, so the volume never grows without bound on an instance
that runs for years."""

INTERVAL_SECONDS = 24 * 60 * 60


def is_auto_backup_enabled(session: Session) -> bool:
    """Enabled by default (no `AppMeta` row written yet) — same default as
    the switch in the frozen mockup (`SettingsScreen.tsx`)."""
    row = session.get(AppMeta, _ENABLED_KEY)
    return row is None or row.value == "true"


def set_auto_backup_enabled(session: Session, enabled: bool) -> None:
    row = session.get(AppMeta, _ENABLED_KEY)
    value = "true" if enabled else "false"
    if row is None:
        session.add(AppMeta(key=_ENABLED_KEY, value=value))
    else:
        row.value = value
    session.commit()


def write_auto_backup(session: Session, backups_dir: Path) -> Path:
    """Write a snapshot and purge the oldest ones beyond `RETENTION`.

    Always unconditional (the caller checks `is_auto_backup_enabled` first,
    see `run_auto_backup_loop`): one function, one role, directly testable
    without depending on the clock or on a real 24h wait."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    document = build_backup(session)
    path = backups_dir / datetime.now(UTC).strftime(_FILENAME_FORMAT)
    path.write_text(document.model_dump_json(), encoding="utf-8")

    existing = sorted(backups_dir.glob(_FILENAME_GLOB))
    for stale in existing[:-RETENTION]:
        stale.unlink(missing_ok=True)

    return path


async def run_auto_backup_loop(
    session_factory: Callable[[], Session], backups_dir: Path
) -> None:
    """One backup at every startup (if enabled), then one every
    `INTERVAL_SECONDS` while the process runs. Cleanly cancelled when the
    application stops (`app/main.py`, `CancelledError` swallowed here)."""
    try:
        while True:
            try:
                with session_factory() as session:
                    if is_auto_backup_enabled(session):
                        path = write_auto_backup(session, backups_dir)
                        logger.info("Automatic backup written: %s", path)
            except Exception:
                logger.exception("Daily automatic backup failed")
            await asyncio.sleep(INTERVAL_SECONDS)
    except asyncio.CancelledError:
        pass
