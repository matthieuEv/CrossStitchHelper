import { useMemo, useState, type ReactNode } from "react";

import { AppShell } from "./components/AppShell";
import { createDemoPattern, createDemoProgress } from "./demo/lavender";
import { createDemoVariants } from "./demo/variants";
import { useT } from "./i18n";
import { useServerHealth } from "./lib/api";
import { useWideLayout } from "./lib/hooks";
import { useRouter } from "./lib/router";
import { emptySpecialProgress } from "./pattern/types";
import { ImportScreen } from "./screens/ImportScreen";
import { LibraryScreen, type LibraryEntry } from "./screens/LibraryScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { StatsScreen } from "./screens/StatsScreen";
import { TrackScreen } from "./screens/TrackScreen";
import { usePatternActivity } from "./state/usePatternActivity";
import { usePatternLibrary } from "./state/usePatternLibrary";
import { useSyncedTracker, type SyncedTracker } from "./state/useSyncedTracker";

// Offline fallback (server unreachable): same default value as
// `backend/app/config.py::Settings.app_version`, the source of truth once the
// server is reachable.
const FALLBACK_VERSION = "v0.0.0-dev";

/**
 * Holds a pattern's tracking state and lends it to the screens that need it.
 *
 * Mounted with a `key` equal to the pattern id: switching patterns cleanly
 * resets progress, the undo stack and the view, without any screen having to
 * care about it.
 *
 * `useSyncedTracker` (rather than `useTracker` directly) adds server
 * synchronisation by versioned deltas (Lot 1): for a purely local demo
 * pattern, sync attempts fail silently (the pattern does not exist on the
 * server), which cleanly degrades to the local behaviour from before Lot 1.
 */
function PatternSession({
  entry,
  children,
}: {
  entry: LibraryEntry;
  children: (tracker: SyncedTracker) => ReactNode;
}) {
  const tracker = useSyncedTracker(
    entry.pattern.id,
    entry.pattern,
    entry.progress,
    entry.version ?? 0,
    entry.special ?? emptySpecialProgress(entry.pattern),
  );
  return <>{children(tracker)}</>;
}

export function App() {
  const t = useT();
  const wide = useWideLayout();
  const { screen, patternId: routePatternId, navigate } = useRouter();
  const { state: serverState, health } = useServerHealth();

  // Demo library, used as long as the server has returned no pattern
  // (loading, server unreachable and nothing cached, or no backend instance
  // in development). Built only once: generation rasterises text on a
  // canvas, which is not free.
  const demoEntries = useMemo<LibraryEntry[]>(() => {
    const pattern = createDemoPattern();
    const main: LibraryEntry = {
      pattern,
      progress: createDemoProgress(pattern),
      hoursAgo: 14,
    };
    return [main, ...createDemoVariants()];
  }, []);

  const library = usePatternLibrary();
  const entries: LibraryEntry[] = library.entries ?? demoEntries;

  // The URL (`/track/{id}`) is the source of truth when it carries one —
  // that is what lets a page reload reopen the same pattern instead of
  // falling back to the first one in the list (see `lib/router.ts`).
  // `activeId` is only a fallback for the navigation bar shortcuts, which
  // navigate without specifying a pattern.
  const [activeId, setActiveId] = useState<string>(() => entries[0]?.pattern.id ?? "");
  const effectiveId = routePatternId ?? activeId;
  const activeEntry = entries.find((entry) => entry.pattern.id === effectiveId) ?? entries[0];

  // A demo pattern does not exist on the server: its history stays fake
  // rather than querying an `/activity` that would answer 404 for genuine
  // reasons (see `usePatternActivity`). Only fetched when the Statistics
  // screen is shown — no point fetching it in the background while the user
  // is stitching.
  const statsPatternId = screen === "stats" && activeEntry !== undefined ? activeEntry.pattern.id : "";
  const patternActivity = usePatternActivity(statsPatternId, library.entries === null);

  const version = health?.version ?? FALLBACK_VERSION;

  const openPattern = (patternId: string): void => {
    setActiveId(patternId);
    navigate("track", patternId);
  };

  return (
    <AppShell screen={screen} navigate={navigate} wide={wide} version={version}>
      {serverState === "unreachable" && (
        <div
          role="status"
          className="tag tag-accent"
          style={{ margin: "10px 20px 0", padding: "8px 14px", fontSize: 12 }}
        >
          {t("server.unreachable")}
        </div>
      )}

      {screen === "library" && (
        <LibraryScreen
          entries={entries}
          wide={wide}
          onOpen={openPattern}
          onImport={() => navigate("import")}
        />
      )}

      {screen === "import" && (
        <ImportScreen
          onCancel={() => navigate("library")}
          onFinish={(patternId) => {
            void library.refresh().then(() => {
              setActiveId(patternId);
              navigate("track", patternId);
            });
          }}
        />
      )}

      {(screen === "track" || screen === "stats") && activeEntry !== undefined && (
        <PatternSession key={activeEntry.pattern.id} entry={activeEntry}>
          {(tracker) =>
            screen === "track" ? (
              <TrackScreen tracker={tracker} wide={wide} onBack={() => navigate("library")} />
            ) : (
              <StatsScreen
                pattern={tracker.pattern}
                counts={tracker.counts}
                totals={tracker.totals}
                activity={patternActivity.activity}
                sessions={patternActivity.sessions}
              />
            )
          }
        </PatternSession>
      )}

      {screen === "settings" && <SettingsScreen version={version} />}
    </AppShell>
  );
}
