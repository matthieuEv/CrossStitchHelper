/**
 * Ajoute la synchronisation serveur par deltas versionnés (cahier des
 * charges §9) par-dessus `useTracker`.
 *
 * Chaque case cochée est mise en file dans IndexedDB (survit à un
 * rechargement de page ou une coupure réseau), puis envoyée au serveur après
 * un court silence. Les changements faits entre-temps par un autre appareil
 * reviennent dans `missing_ops` et sont rejoués localement via
 * `tracker.applyRemote`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { syncProgress } from "../lib/api";
import { cacheProgress, clearPendingOps, enqueueOps, getPendingOps } from "../lib/db";
import type { Pattern, Progress } from "../pattern/types";
import { useTracker, type CellChange, type Tracker } from "./useTracker";

const FLUSH_DEBOUNCE_MS = 1200;

export type SyncState = "synced" | "pending" | "syncing" | "offline";

export interface SyncedTracker extends Tracker {
  /** État de la synchronisation avec le serveur — informatif, pas bloquant. */
  syncState: SyncState;
}

export function useSyncedTracker(
  patternId: string,
  pattern: Pattern,
  initialProgress: Progress,
  initialVersion: number,
): SyncedTracker {
  const versionRef = useRef(initialVersion);
  const flushTimerRef = useRef<number | null>(null);
  const flushingRef = useRef(false);
  const flushRef = useRef<() => void>(() => {});
  const trackerRef = useRef<Tracker | null>(null);
  const [syncState, setSyncState] = useState<SyncState>("synced");

  const scheduleFlush = useCallback((delay: number) => {
    if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
    flushTimerRef.current = window.setTimeout(() => flushRef.current(), delay);
  }, []);

  const onChange = useCallback(
    (changes: CellChange[]) => {
      // Best-effort : la transaction IndexedDB se termine largement avant
      // l'expiration du délai ci-dessous, pas besoin d'attendre ici — cela
      // forcerait `toggleCell` à devenir asynchrone jusqu'au geste tactile.
      void enqueueOps(
        patternId,
        changes.map((change) => ({ index: change.index, stitched: change.stitched === 1 })),
      );
      setSyncState((current) => (current === "syncing" ? current : "pending"));
      scheduleFlush(FLUSH_DEBOUNCE_MS);
    },
    [patternId, scheduleFlush],
  );

  const tracker = useTracker(pattern, initialProgress, onChange);
  trackerRef.current = tracker;

  const flush = useCallback(async () => {
    if (flushingRef.current) return;
    flushingRef.current = true;
    try {
      const pending = await getPendingOps(patternId);
      if (pending.length === 0) {
        setSyncState("synced");
        return;
      }
      setSyncState("syncing");
      const response = await syncProgress(
        patternId,
        versionRef.current,
        pending.map((op) => ({ index: op.index, stitched: op.stitched })),
      );
      const ids = pending
        .map((op) => op.id)
        .filter((id): id is number => id !== undefined);
      await clearPendingOps(ids);
      versionRef.current = response.version;

      if (response.missing_ops.length > 0) {
        trackerRef.current?.applyRemote(
          response.missing_ops.map((op) => ({
            index: op.index,
            stitched: op.stitched ? 1 : 0,
          })),
        );
      }
      if (trackerRef.current !== null) {
        await cacheProgress(
          patternId,
          trackerRef.current.done,
          response.version,
          response.stitched_count,
        );
      }
      setSyncState("synced");
    } catch {
      // Hors ligne ou serveur injoignable : les opérations restent en file,
      // on retentera au prochain changement ou au retour du réseau — jamais
      // d'erreur remontée à l'utilisateur, le suivi doit rester utilisable.
      setSyncState("offline");
    } finally {
      flushingRef.current = false;
    }
  }, [patternId]);
  flushRef.current = () => void flush();

  useEffect(() => {
    const handleOnline = (): void => scheduleFlush(0);
    window.addEventListener("online", handleOnline);
    // Rattrape au montage les opérations laissées en file par une session
    // précédente (rechargement pendant une coupure réseau, onglet fermé
    // avant la fin du délai de synchronisation).
    scheduleFlush(0);
    return () => {
      window.removeEventListener("online", handleOnline);
      if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
    };
  }, [scheduleFlush]);

  return { ...tracker, syncState };
}
