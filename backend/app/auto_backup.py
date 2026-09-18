"""Sauvegarde automatique quotidienne (Lot 8, cahier des charges §7.5).

Écrit un instantané de `app.backup.build_backup` sur disque, dans
`Settings.backups_dir`, à intervalle régulier : pas de nouvelle dépendance
d'infrastructure (pas de planificateur externe — `CLAUDE.md` : « aucune
installation à plusieurs services »), juste une boucle asyncio en tâche de
fond du processus applicatif, démarrée et arrêtée avec le cycle de vie
FastAPI (`app/main.py`).

Activable/désactivable par l'utilisateur (`AppMeta`, réglages §7.5) — un
réglage serveur, jamais une préférence locale au navigateur
(`frontend/src/screens/SettingsScreen.tsx`), pour qu'elle s'applique même si
personne n'ouvre l'application ce jour-là.
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
"""Microsecondes incluses : deux écritures dans la même seconde (redémarrage
rapide du conteneur, ou la boucle de test à intervalle raccourci) ne doivent
jamais s'écraser l'une l'autre silencieusement."""
_FILENAME_GLOB = "backup-*.json"

RETENTION = 14
"""Nombre d'instantanés automatiques conservés — au-delà, les plus anciens
sont supprimés à chaque nouvelle écriture, pour ne jamais faire croître le
volume sans limite sur une instance qui tourne pendant des années."""

INTERVAL_SECONDS = 24 * 60 * 60


def is_auto_backup_enabled(session: Session) -> bool:
    """Activée par défaut (aucune ligne `AppMeta` encore écrite) — même
    défaut que le commutateur du mockup figé (`SettingsScreen.tsx`)."""
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
    """Écrit un instantané et purge les plus anciens au-delà de `RETENTION`.

    Toujours inconditionnelle (l'appelant vérifie `is_auto_backup_enabled`
    avant, voir `run_auto_backup_loop`) : une fonction, un rôle, directement
    testable sans dépendre de l'horloge ni d'une vraie attente de 24h."""
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
    """Une sauvegarde à chaque démarrage (si activée), puis une par
    `INTERVAL_SECONDS` tant que le processus tourne. Annulée proprement à
    l'arrêt de l'application (`app/main.py`, `CancelledError` avalée ici)."""
    try:
        while True:
            try:
                with session_factory() as session:
                    if is_auto_backup_enabled(session):
                        path = write_auto_backup(session, backups_dir)
                        logger.info("Sauvegarde automatique écrite : %s", path)
            except Exception:
                logger.exception("Échec de la sauvegarde automatique quotidienne")
            await asyncio.sleep(INTERVAL_SECONDS)
    except asyncio.CancelledError:
        pass
