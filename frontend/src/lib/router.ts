/**
 * Routage minimal fondé sur l'History API.
 *
 * Cinq écrans et aucun paramètre d'URL pour l'instant : une dépendance de
 * routage complète ne se justifie pas. De vraies URL (et non un fragment) sont
 * indispensables pour qu'un motif ouvert puisse être mis en favori, et c'est ce
 * que sert le repli SPA du backend.
 */

import { useCallback, useEffect, useState } from "react";

export const SCREENS = ["library", "import", "track", "stats", "settings"] as const;
export type Screen = (typeof SCREENS)[number];

const PATHS: Record<Screen, string> = {
  library: "/",
  import: "/import",
  track: "/track",
  stats: "/stats",
  settings: "/settings",
};

function screenFromPath(pathname: string): Screen {
  const entry = (Object.entries(PATHS) as Array<[Screen, string]>).find(
    ([, path]) => path === pathname,
  );
  return entry?.[0] ?? "library";
}

export function useRouter(): { screen: Screen; navigate: (screen: Screen) => void } {
  const [screen, setScreen] = useState<Screen>(() => screenFromPath(window.location.pathname));

  useEffect(() => {
    const onPopState = (): void => setScreen(screenFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((next: Screen) => {
    const path = PATHS[next];
    if (window.location.pathname !== path) window.history.pushState(null, "", path);
    setScreen(next);
  }, []);

  return { screen, navigate };
}
