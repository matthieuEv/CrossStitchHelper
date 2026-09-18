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

// Repli hors-ligne (serveur injoignable) — tenu à jour avec
// `backend/app/__init__.py::__version__`, la source de vérité une fois le
// serveur joignable.
const FALLBACK_VERSION = "0.1.0 · Lot 4";

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
    entry.special ?? emptySpecialProgress(entry.pattern),
  );
  return <>{children(tracker)}</>;
}

export function App() {
  const t = useT();
  const wide = useWideLayout();
  const { screen, patternId: routePatternId, navigate } = useRouter();
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

  // L'URL (`/track/{id}`) est la source de vérité quand elle en porte un —
  // c'est ce qui permet à un rechargement de page de rouvrir le même motif
  // au lieu de retomber sur le premier de la liste (voir `lib/router.ts`).
  // `activeId` ne sert que de repli pour les raccourcis de la barre de
  // navigation, qui naviguent sans préciser de motif.
  const [activeId, setActiveId] = useState<string>(() => entries[0]?.pattern.id ?? "");
  const effectiveId = routePatternId ?? activeId;
  const activeEntry = entries.find((entry) => entry.pattern.id === effectiveId) ?? entries[0];

  // Un motif de démonstration n'existe pas côté serveur : son historique
  // reste factice plutôt que d'interroger un `/activity` qui répondrait 404
  // pour de vraies raisons (voir `usePatternActivity`). Récupéré uniquement
  // quand l'écran Statistiques est affiché — inutile de l'aller chercher en
  // arrière-plan pendant que l'utilisateur brode.
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
