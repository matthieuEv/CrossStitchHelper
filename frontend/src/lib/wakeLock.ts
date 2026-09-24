/**
 * Keeps the screen on while stitching.
 *
 * You stitch with your hands busy, without touching the screen for several
 * minutes: without this lock, the device goes to sleep in the middle of a row.
 * The API is not available everywhere (Safari only has it since iOS 16.4), and
 * the lock is released by the system as soon as the tab goes to the
 * background — so it must be re-acquired on return.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface WakeLock {
  supported: boolean;
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

export function useWakeLock(): WakeLock {
  const supported = typeof navigator !== "undefined" && "wakeLock" in navigator;
  const [enabled, setEnabled] = useState(false);
  const sentinelRef = useRef<WakeLockSentinel | null>(null);

  const release = useCallback(() => {
    const sentinel = sentinelRef.current;
    sentinelRef.current = null;
    if (sentinel !== null) void sentinel.release().catch(() => undefined);
  }, []);

  const acquire = useCallback(async () => {
    if (!supported || sentinelRef.current !== null) return;
    try {
      sentinelRef.current = await navigator.wakeLock.request("screen");
    } catch {
      // Refused by the system (low battery, hidden tab): don't insist, the
      // user simply keeps the default behaviour.
    }
  }, [supported]);

  useEffect(() => {
    if (enabled) void acquire();
    else release();
    return release;
  }, [enabled, acquire, release]);

  useEffect(() => {
    if (!enabled) return;
    const onVisibility = (): void => {
      if (document.visibilityState === "visible") void acquire();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [enabled, acquire]);

  return { supported, enabled, setEnabled };
}
