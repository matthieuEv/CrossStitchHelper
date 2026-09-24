/**
 * Adds server synchronisation by versioned deltas (specification §9) on top
 * of `useTracker`.
 *
 * Each checked cell is queued in IndexedDB (survives a page reload or a
 * network outage), then sent to the server after a short idle period.
 * Changes made meanwhile by another device come back in `missing_ops` and
 * are replayed locally via `tracker.applyRemote`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { syncProgress } from "../lib/api";
import { cacheProgress, clearPendingOps, enqueueOps, getPendingOps } from "../lib/db";
import { emptySpecialProgress, type Pattern, type Progress, type SpecialProgress } from "../pattern/types";
import { useTracker, type CellChange, type Tracker } from "./useTracker";

const FLUSH_DEBOUNCE_MS = 1200;

export type SyncState = "synced" | "pending" | "syncing" | "offline";

export interface SyncedTracker extends Tracker {
  /** Synchronisation state with the server — informative, not blocking. */
  syncState: SyncState;
}

export function useSyncedTracker(
  patternId: string,
  pattern: Pattern,
  initialProgress: Progress,
  initialVersion: number,
  initialSpecial: SpecialProgress = emptySpecialProgress(pattern),
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
      // Best effort: the IndexedDB transaction finishes well before the delay
      // below expires, no need to wait here — that would force
      // `toggleCell`/`toggleAtPoint` to become asynchronous all the way up to
      // the touch gesture.
      void enqueueOps(
        patternId,
        changes.map((change) => ({
          layer: change.layer,
          index: change.index,
          stitched: change.stitched === 1,
        })),
      );
      setSyncState((current) => (current === "syncing" ? current : "pending"));
      scheduleFlush(FLUSH_DEBOUNCE_MS);
    },
    [patternId, scheduleFlush],
  );

  const tracker = useTracker(pattern, initialProgress, initialSpecial, onChange);
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
        // An operation queued before Lot 8 has no `layer`: it can only be a
        // full stitch (the only category that existed then), same default as
        // on the server (`ProgressOp.layer`).
        pending.map((op) => ({ layer: op.layer ?? "full", index: op.index, stitched: op.stitched })),
      );
      const ids = pending
        .map((op) => op.id)
        .filter((id): id is number => id !== undefined);
      await clearPendingOps(ids);
      versionRef.current = response.version;

      if (response.missing_ops.length > 0) {
        trackerRef.current?.applyRemote(
          response.missing_ops.map((op) => ({
            layer: op.layer,
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
          trackerRef.current.special,
        );
      }
      setSyncState("synced");
    } catch {
      // Offline or server unreachable: operations stay queued, we will retry
      // on the next change or when the network returns — never an error
      // surfaced to the user, tracking must stay usable.
      setSyncState("offline");
    } finally {
      flushingRef.current = false;
    }
  }, [patternId]);
  flushRef.current = () => void flush();

  useEffect(() => {
    const handleOnline = (): void => scheduleFlush(0);
    window.addEventListener("online", handleOnline);
    // On mount, catch up on operations left queued by a previous session
    // (reload during a network outage, tab closed before the sync delay
    // ended).
    scheduleFlush(0);
    return () => {
      window.removeEventListener("online", handleOnline);
      if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
    };
  }, [scheduleFlush]);

  return { ...tracker, syncState };
}
