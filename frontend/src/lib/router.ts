/**
 * Minimal routing based on the History API.
 *
 * `track` and `stats` carry the pattern id in the URL (`/track/{id}`): that
 * is what lets a page reload — or a shared link — reopen the same pattern
 * rather than falling back to the first one in the list. Before Lot 2, only
 * one pattern ever really existed in the database, so nothing distinguished a
 * correct reload from one that happened to land on the right pattern by
 * coincidence.
 */

import { useCallback, useEffect, useState } from "react";

export const SCREENS = ["library", "import", "track", "stats", "settings"] as const;
export type Screen = (typeof SCREENS)[number];

/** Screens that carry a pattern id in their URL. */
const SCREENS_WITH_PATTERN: readonly Screen[] = ["track", "stats"];

const BASE_PATHS: Record<Screen, string> = {
  library: "/",
  import: "/import",
  track: "/track",
  stats: "/stats",
  settings: "/settings",
};

interface Route {
  screen: Screen;
  patternId: string | null;
}

function routeFromPath(pathname: string): Route {
  for (const screen of SCREENS_WITH_PATTERN) {
    const prefix = `${BASE_PATHS[screen]}/`;
    if (pathname.startsWith(prefix)) {
      const patternId = decodeURIComponent(pathname.slice(prefix.length));
      return { screen, patternId: patternId === "" ? null : patternId };
    }
  }
  const entry = (Object.entries(BASE_PATHS) as Array<[Screen, string]>).find(
    ([, path]) => path === pathname,
  );
  return { screen: entry?.[0] ?? "library", patternId: null };
}

function pathFor(screen: Screen, patternId: string | null): string {
  if (SCREENS_WITH_PATTERN.includes(screen) && patternId !== null) {
    return `${BASE_PATHS[screen]}/${encodeURIComponent(patternId)}`;
  }
  return BASE_PATHS[screen];
}

export function useRouter(): {
  screen: Screen;
  /** Pattern carried by the current URL; always `null` outside `track`/`stats`. */
  patternId: string | null;
  /** `patternId` is only needed for `track` and `stats`. */
  navigate: (screen: Screen, patternId?: string) => void;
} {
  const [route, setRoute] = useState<Route>(() => routeFromPath(window.location.pathname));

  useEffect(() => {
    const onPopState = (): void => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((next: Screen, patternId?: string) => {
    const nextPatternId = patternId ?? null;
    const path = pathFor(next, nextPatternId);
    if (window.location.pathname !== path) window.history.pushState(null, "", path);
    setRoute({ screen: next, patternId: nextPatternId });
  }, []);

  return { screen: route.screen, patternId: route.patternId, navigate };
}
