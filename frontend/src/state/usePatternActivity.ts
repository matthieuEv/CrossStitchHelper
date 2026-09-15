/**
 * Historique d'activité (Lot 3) : dérivé côté serveur de `progress_events`
 * (voir `backend/app/activity.py`) — jamais recalculé côté client, qui
 * n'a de toute façon pas la vue complète multi-appareils de ce journal.
 *
 * Pour un motif de démonstration purement local (aucune existence côté
 * serveur), on affiche un historique factice plutôt que d'aller vers un
 * `/api/patterns/{id}/activity` qui répondrait 404 pour de vraies raisons.
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

/** `patternId` vide (écran Statistiques pas affiché) : aucun appel réseau. */
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
        // Serveur injoignable ou motif introuvable côté serveur (cache
        // hors-ligne, Lot 1) : rien à afficher plutôt qu'un historique
        // inventé pour un vrai motif.
      });
    return () => controller.abort();
  }, [patternId, isDemo]);

  return state;
}
