/**
 * Activity history (Lot 3): derived on the server from `progress_events`
 * (see `backend/app/activity.py`) — never recomputed on the client, which
 * does not have the complete multi-device view of that log anyway.
 *
 * For a purely local demo pattern (no existence on the server), a fake
 * history is shown rather than calling a `/api/patterns/{id}/activity` that
 * would answer 404 for genuine reasons.
 */

import { useEffect, useState } from "react";

import { fetchPatternActivity } from "../lib/api";
import type { ActivityDay, ActivitySession } from "../screens/StatsScreen";

const DEMO_ACTIVITY: readonly ActivityDay[] = [
  { weekday: 0, stitches: 340 },
  { weekday: 1, stitches: 0 },
  { weekday: 2, stitches: 580 },
  { weekday: 3, stitches: 860 },
  { weekday: 4, stitches: 220 },
  { weekday: 5, stitches: 1000 },
  { weekday: 6, stitches: 460 },
];

const DEMO_SESSIONS: readonly ActivitySession[] = [
  { hoursAgo: 14, stitches: 312, minutes: 48 },
  { hoursAgo: 62, stitches: 704, minutes: 112 },
  { hoursAgo: 110, stitches: 186, minutes: 26 },
  { hoursAgo: 134, stitches: 421, minutes: 64 },
];

const EMPTY_ACTIVITY: readonly ActivityDay[] = [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({
  weekday,
  stitches: 0,
}));

export interface PatternActivity {
  activity: readonly ActivityDay[];
  sessions: readonly ActivitySession[];
}

/** Empty `patternId` (Statistics screen not shown): no network call. */
export function usePatternActivity(patternId: string, isDemo: boolean): PatternActivity {
  const [state, setState] = useState<PatternActivity>(
    isDemo
      ? { activity: DEMO_ACTIVITY, sessions: DEMO_SESSIONS }
      : { activity: EMPTY_ACTIVITY, sessions: [] },
  );

  useEffect(() => {
    if (isDemo) {
      setState({ activity: DEMO_ACTIVITY, sessions: DEMO_SESSIONS });
      return;
    }
    if (patternId === "") return;

    setState({ activity: EMPTY_ACTIVITY, sessions: [] });
    const controller = new AbortController();
    fetchPatternActivity(patternId, controller.signal)
      .then((data) => {
        setState({
          activity: data.activity,
          sessions: data.sessions.map((session) => ({
            hoursAgo: session.hours_ago,
            stitches: session.stitches,
            minutes: session.minutes,
          })),
        });
      })
      .catch(() => {
        // Server unreachable or pattern not found on the server (offline
        // cache, Lot 1): nothing to show rather than a made-up history for a
        // real pattern.
      });
    return () => controller.abort();
  }, [patternId, isDemo]);

  return state;
}
