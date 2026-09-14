import { useMemo, useState, type ReactNode } from "react";

import { AppShell } from "./components/AppShell";
import { createDemoPattern, createDemoProgress } from "./demo/lavender";
import { createDemoVariants } from "./demo/variants";
import { useT } from "./i18n";
import { useServerHealth } from "./lib/api";
import { useWideLayout } from "./lib/hooks";
import { useRouter } from "./lib/router";
import { ImportScreen } from "./screens/ImportScreen";
import { LibraryScreen, type LibraryEntry } from "./screens/LibraryScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { StatsScreen, type ActivityDay, type ActivitySession } from "./screens/StatsScreen";
import { TrackScreen } from "./screens/TrackScreen";
import { usePatternLibrary } from "./state/usePatternLibrary";
import { useSyncedTracker, type SyncedTracker } from "./state/useSyncedTracker";

const FALLBACK_VERSION = "0.1.0";

/** Historique de séances de démonstration, remplacé par `progress_events` au Lot 1. */
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

/**
 * Détient l'état de suivi d'un motif et le prête aux écrans qui en ont besoin.
 *
 * Monté avec une `key` égale à l'identifiant du motif : changer de motif
 * réinitialise proprement la progression, la pile d'annulation et la vue, sans
 * qu'aucun écran ait à s'en préoccuper.
 *
 * `useSyncedTracker` (plutôt que `useTracker` directement) ajoute la
 * synchronisation serveur par deltas versionnés (Lot 1) : pour un motif de
 * démonstration purement local, les tentatives de synchronisation échouent
 * silencieusement (le motif n'existe pas côté serveur), ce qui dégrade
 * proprement vers le comportement local d'avant le Lot 1.
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
  );
  return <>{children(tracker)}</>;
}

export function App() {
  const t = useT();
  const wide = useWideLayout();
  const { screen, navigate } = useRouter();
  const { state: serverState, health } = useServerHealth();

  // Bibliothèque de démonstration, utilisée tant que le serveur n'a rendu
  // aucun motif (chargement en cours, serveur injoignable et rien en cache,
  // ou instance backend absente en développement). Construite une seule
  // fois : la génération rasterise du texte sur un canvas, ce n'est pas
  // gratuit.
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

  const [activeId, setActiveId] = useState<string>(() => entries[0]?.pattern.id ?? "");
  const activeEntry = entries.find((entry) => entry.pattern.id === activeId) ?? entries[0];

  const version = health?.version ?? FALLBACK_VERSION;

  const openPattern = (patternId: string): void => {
    setActiveId(patternId);
    navigate("track");
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
              navigate("track");
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
                activity={DEMO_ACTIVITY}
                sessions={DEMO_SESSIONS}
              />
            )
          }
        </PatternSession>
      )}

      {screen === "settings" && <SettingsScreen version={version} />}
    </AppShell>
  );
}
