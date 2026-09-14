/**
 * Maintien de l'écran allumé pendant la broderie.
 *
 * On brode les mains occupées, sans toucher l'écran pendant plusieurs minutes :
 * sans ce verrou, l'appareil s'éteint en plein milieu d'une rangée. L'API n'est
 * pas disponible partout (Safari ne l'a que depuis iOS 16.4), et le verrou est
 * relâché par le système dès que l'onglet passe en arrière-plan — il faut donc
 * le reprendre au retour.
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
      // Refus du système (batterie faible, onglet masqué) : on n'insiste pas,
      // l'utilisateur garde simplement le comportement par défaut.
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
