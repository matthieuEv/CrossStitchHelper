/**
 * Routage minimal fondé sur l'History API.
 *
 * `track` et `stats` portent l'identifiant du motif dans l'URL
 * (`/track/{id}`) : c'est ce qui permet à un rechargement de page — ou à un
 * lien partagé — de rouvrir le même motif plutôt que de retomber sur le
 * premier de la liste. Avant le Lot 2, un seul motif existait jamais
 * réellement en base, donc rien ne distinguait un rechargement correct d'un
 * rechargement qui retombait par coïncidence sur le bon motif.
 */

import { useCallback, useEffect, useState } from "react";

export const SCREENS = ["library", "import", "track", "stats", "settings"] as const;
export type Screen = (typeof SCREENS)[number];

/** Écrans qui portent un identifiant de motif dans leur URL. */
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
  /** Motif porté par l'URL courante ; toujours `null` hors `track`/`stats`. */
  patternId: string | null;
  /** `patternId` n'est nécessaire que pour `track` et `stats`. */
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
