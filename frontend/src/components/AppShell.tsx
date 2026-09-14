import type { ReactNode } from "react";

import { useT } from "../i18n";
import type { Screen } from "../lib/router";
import { GridIcon, PlusIcon, SettingsIcon, StatsIcon, TrackIcon } from "./Icons";

interface AppShellProps {
  screen: Screen;
  navigate: (screen: Screen) => void;
  wide: boolean;
  version: string;
  children: ReactNode;
}

const NAV_ITEMS = ["library", "track", "stats", "settings"] as const;

/**
 * Coquille de navigation.
 *
 * Deux dispositions, un seul arbre de composants : barre latérale permanente
 * quand la largeur le permet, barre d'onglets en bas sinon. La bascule suit la
 * largeur disponible et non le modèle d'appareil, pour que le Split View d'un
 * iPad soit traité comme ce qu'il est — un écran étroit.
 */
export function AppShell({ screen, navigate, wide, version, children }: AppShellProps) {
  const t = useT();

  const label = (item: (typeof NAV_ITEMS)[number], short: boolean): string => {
    switch (item) {
      case "library":
        return short ? t("nav.libraryShort") : t("nav.library");
      case "track":
        return t("nav.track");
      case "stats":
        return short ? t("nav.statsShort") : t("nav.stats");
      case "settings":
        return t("nav.settings");
    }
  };

  const icon = (item: (typeof NAV_ITEMS)[number], size: number): ReactNode => {
    switch (item) {
      case "library":
        return <GridIcon size={size} />;
      case "track":
        return <TrackIcon size={size} />;
      case "stats":
        return <StatsIcon size={size} />;
      case "settings":
        return <SettingsIcon size={size} />;
    }
  };

  return (
    <div className="app">
      {!wide && <div className="status-bar-spacer" />}

      <div className="app-body">
        {wide && (
          <nav className="sidebar" aria-label={t("app.name")}>
            <div className="sidebar-brand">
              CrossStitch
              <br />
              Helper
            </div>
            <button
              type="button"
              className="btn btn-primary"
              style={{ minHeight: 48, fontSize: 15, gap: 10 }}
              onClick={() => navigate("import")}
            >
              <PlusIcon size={20} />
              {t("nav.import")}
            </button>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {NAV_ITEMS.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="sidebar-link"
                  aria-current={screen === item ? "page" : undefined}
                  onClick={() => navigate(item)}
                >
                  {icon(item, 21)}
                  {label(item, false)}
                </button>
              ))}
            </div>
            <div className="text-faint" style={{ marginTop: "auto", padding: "0 10px", fontSize: 11, lineHeight: 1.5 }}>
              {t("app.tagline")}
              <br />
              {version}
            </div>
          </nav>
        )}

        <div className="app-main">{children}</div>
      </div>

      {!wide && (
        <nav className="tabbar" aria-label={t("app.name")}>
          {NAV_ITEMS.map((item) => (
            <button
              key={item}
              type="button"
              aria-current={screen === item ? "page" : undefined}
              onClick={() => navigate(item)}
            >
              {icon(item, 24)}
              {label(item, true)}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
