from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.activity import compute_activity

# Wednesday 2026-01-07 12:00 UTC — known ISO weekday (2 = Wednesday, 0-based
# like `ActivityDayOut.weekday`), a fixed reference point so the tests never
# depend on the date they run.
NOW = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)


def test_empty_events_gives_zeroed_week_and_no_sessions() -> None:
    result = compute_activity([], now=NOW)
    assert len(result.activity) == 7
    assert all(day.stitches == 0 for day in result.activity)
    assert result.sessions == []


def test_stitches_bucketed_by_iso_weekday() -> None:
    # NOW is a Wednesday (weekday=2); an event the day before falls on
    # weekday=1 (Tuesday).
    events = [
        (NOW, [{"index": 1, "stitched": True}, {"index": 2, "stitched": True}]),
        (NOW - timedelta(days=1), [{"index": 3, "stitched": True}]),
    ]
    result = compute_activity(events, now=NOW)
    by_weekday = {day.weekday: day.stitches for day in result.activity}
    assert by_weekday[2] == 2
    assert by_weekday[1] == 1
    assert by_weekday[0] == 0


def test_unstitch_ops_do_not_count_as_activity() -> None:
    events = [(NOW, [{"index": 1, "stitched": False}])]
    result = compute_activity(events, now=NOW)
    assert all(day.stitches == 0 for day in result.activity)


def test_events_older_than_seven_days_are_excluded_from_the_chart() -> None:
    events = [(NOW - timedelta(days=8), [{"index": 1, "stitched": True}])]
    result = compute_activity(events, now=NOW)
    assert all(day.stitches == 0 for day in result.activity)


def test_close_events_merge_into_a_single_session() -> None:
    events = [
        (NOW - timedelta(minutes=20), [{"index": 1, "stitched": True}]),
        (NOW - timedelta(minutes=5), [{"index": 2, "stitched": True}]),
    ]
    result = compute_activity(events, now=NOW)
    assert len(result.sessions) == 1
    session = result.sessions[0]
    assert session.stitches == 2
    assert session.minutes == 15
    assert session.hours_ago == round(5 / 60, 1)


def test_gap_over_threshold_splits_into_two_sessions() -> None:
    events = [
        (NOW - timedelta(hours=3), [{"index": 1, "stitched": True}]),
        (NOW - timedelta(minutes=10), [{"index": 2, "stitched": True}]),
    ]
    result = compute_activity(events, now=NOW)
    assert len(result.sessions) == 2
    # Sessions are returned most recent first.
    assert result.sessions[0].hours_ago < result.sessions[1].hours_ago


def test_single_event_session_has_a_one_minute_floor() -> None:
    events = [(NOW, [{"index": 1, "stitched": True}])]
    result = compute_activity(events, now=NOW)
    assert result.sessions[0].minutes == 1


def test_sessions_are_capped_and_sorted_most_recent_first() -> None:
    # Sorted by ascending `ts`, as `compute_activity` requires — the oldest
    # (the largest number of hours in the past) first.
    # Far more than MAX_SESSIONS, one isolated event each.
    events = [
        (NOW - timedelta(hours=hours), [{"index": hours, "stitched": True}])
        for hours in reversed(range(0, 200, 2))
    ]
    result = compute_activity(events, now=NOW)
    assert len(result.sessions) == 20
    hours_ago = [session.hours_ago for session in result.sessions]
    assert hours_ago == sorted(hours_ago)
