/**
 * Thème clair / sombre / système.
 *
 * Le choix est appliqué sur `<html data-theme>` : `index.css` fait le reste,
 * et le rendu canvas relit ses couleurs depuis les variables CSS, donc un
 * changement de thème n'a aucune valeur à dupliquer en JavaScript.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "csh.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function readStoredChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // Stockage indisponible : on suit le système, ce qui est le bon défaut.
  }
  return "system";
}

interface ThemeContextValue {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStoredChoice);
  const [systemDark, setSystemDark] = useState<boolean>(
    () => window.matchMedia(DARK_QUERY).matches,
  );

  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY);
    const onChange = (event: MediaQueryListEvent): void => setSystemDark(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const resolved: ResolvedTheme =
    choice === "system" ? (systemDark ? "dark" : "light") : choice;

  useEffect(() => {
    document.documentElement.dataset["theme"] = resolved;
    // Garde la couleur de barre d'état/chrome du navigateur synchronisée
    // avec le thème réellement appliqué — le script bloquant de
    // `index.html` ne couvre que le tout premier rendu, pas un changement
    // fait ensuite (bascule manuelle, ou préférence système qui change
    // pendant que l'app est ouverte).
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta !== null) meta.setAttribute("content", resolved === "dark" ? "#1f1d19" : "#f5ead8");
  }, [resolved]);

  const setChoice = useCallback((next: ThemeChoice) => {
    setChoiceState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Préférence non mémorisée : sans gravité.
    }
  }, []);

  const value = useMemo(
    () => ({ choice, resolved, setChoice }),
    [choice, resolved, setChoice],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (value === null) throw new Error("useTheme doit être utilisé dans <ThemeProvider>");
  return value;
}
