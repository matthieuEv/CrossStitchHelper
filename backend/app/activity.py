"""Aggregation of the activity history from `progress_events`.

Nothing is stored separately (§11, Lot 3): the delta log already written for
multi-device synchronisation (Lot 1) is the only source of truth for "who
stitched when". Kept separate from `app/api/patterns.py` so it stays testable
without a database — see `backend/tests/test_activity.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.schemas import ActivityDayOut, ActivitySessionOut, PatternActivityOut

# Beyond this gap, two progress events are considered two distinct stitching
# sessions rather than a single interrupted one.
SESSION_GAP = timedelta(minutes=30)

# The activity chart only covers the last 7 rolling days — a longer history
# adds nothing to a tracking-comfort feature.
ACTIVITY_WINDOW = timedelta(days=7)

MAX_SESSIONS = 20


def _stitched_count(ops: list[dict[str, Any]]) -> int:
    return sum(1 for op in ops if op.get("stitched"))


def compute_activity(
    events: list[tuple[datetime, list[dict[str, Any]]]], now: datetime | None = None
) -> PatternActivityOut:
    """`events` must be sorted by ascending `ts` (the table's natural order)."""
    now = now if now is not None else datetime.now(UTC)

    activity_by_weekday: dict[int, int] = {}
    window_start = now - ACTIVITY_WINDOW
    for ts, ops in events:
        if ts < window_start:
            continue
        stitched = _stitched_count(ops)
        if stitched == 0:
            continue
        weekday = ts.isoweekday() - 1  # ISO: Monday=1..Sunday=7 -> 0..6
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
