"""Agrégation de l'historique d'activité à partir de `progress_events`.

Rien n'est stocké séparément (§11, Lot 3) : le journal des deltas déjà écrit
pour la synchronisation multi-appareils (Lot 1) est la seule source de vérité
de « qui a brodé quand ». Séparé de `app/api/patterns.py` pour rester testable
sans base de données — voir `backend/tests/test_activity.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.schemas import ActivityDayOut, ActivitySessionOut, PatternActivityOut

# Au-delà de cette coupure, deux événements de progression sont considérés
# comme deux séances de broderie distinctes plutôt qu'une seule interrompue.
SESSION_GAP = timedelta(minutes=30)

# Le graphique d'activité ne couvre que les 7 derniers jours glissants — un
# historique plus long n'apporte rien à un geste de confort de suivi.
ACTIVITY_WINDOW = timedelta(days=7)

MAX_SESSIONS = 20


def _stitched_count(ops: list[dict[str, Any]]) -> int:
    return sum(1 for op in ops if op.get("stitched"))


def compute_activity(
    events: list[tuple[datetime, list[dict[str, Any]]]], now: datetime | None = None
) -> PatternActivityOut:
    """`events` doit être trié par `ts` croissant (l'ordre naturel de la table)."""
    now = now if now is not None else datetime.now(UTC)

    activity_by_weekday: dict[int, int] = {}
    window_start = now - ACTIVITY_WINDOW
    for ts, ops in events:
        if ts < window_start:
            continue
        stitched = _stitched_count(ops)
        if stitched == 0:
            continue
        weekday = ts.isoweekday() - 1  # ISO : lundi=1..dimanche=7 -> 0..6
        activity_by_weekday[weekday] = activity_by_weekday.get(weekday, 0) + stitched
    activity = [
        ActivityDayOut(weekday=weekday, stitches=activity_by_weekday.get(weekday, 0))
        for weekday in range(7)
    ]

    sessions: list[ActivitySessionOut] = []
    current_start: datetime | None = None
    current_end: datetime | None = None
    current_stitches = 0

    def flush() -> None:
        nonlocal current_start, current_end, current_stitches
        if current_start is None or current_end is None:
            return
        duration_minutes = max(1, round((current_end - current_start).total_seconds() / 60))
        hours_ago = max(0.0, (now - current_end).total_seconds() / 3600)
        sessions.append(
            ActivitySessionOut(
                hours_ago=round(hours_ago, 1), stitches=current_stitches, minutes=duration_minutes
            )
        )
        current_start, current_end, current_stitches = None, None, 0

    for ts, ops in events:
        if current_end is not None and ts - current_end > SESSION_GAP:
            flush()
        if current_start is None:
            current_start = ts
        current_end = ts
        current_stitches += _stitched_count(ops)
    flush()

    sessions.sort(key=lambda session: session.hours_ago)
    return PatternActivityOut(activity=activity, sessions=sessions[:MAX_SESSIONS])
