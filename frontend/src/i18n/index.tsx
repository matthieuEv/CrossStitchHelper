/**
 * Minimal, typed internationalisation.
 *
 * Deliberately hand-written rather than using i18next: the application needs
 * neither complex plurals, nor on-demand loading, nor advanced locale
 * detection, and a self-hosted instance is better off without a superfluous
 * dependency (specification §3).
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

import { en } from "./en";
import { fr, type TranslationKey } from "./fr";

export const LANGUAGES = ["fr", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

const DICTIONARIES: Record<Language, Record<TranslationKey, string>> = { fr, en };
const STORAGE_KEY = "csh.language";

export type TranslateValues = Record<string, string | number>;
export type Translate = (key: TranslationKey, values?: TranslateValues) => string;

function interpolate(template: string, values: TranslateValues | undefined): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = values[name];
    return value === undefined ? match : String(value);
  });
}

function isLanguage(value: string | null): value is Language {
  return value !== null && (LANGUAGES as readonly string[]).includes(value);
}

function detectLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // Safari in private browsing refuses localStorage: fall back to the
    // browser language rather than crashing at startup.
  }
  return navigator.language.toLowerCase().startsWith("fr") ? "fr" : "en";
}

interface I18nContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translate;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(detectLanguage);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Preference not remembered: harmless, the interface stays correct.
    }
  }, []);

  const t = useCallback<Translate>(
    (key, values) => interpolate(DICTIONARIES[language][key], values),
    [language],
  );

  const value = useMemo(
    () => ({ language, setLanguage, t }),
    [language, setLanguage, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (value === null) throw new Error("useI18n must be used within <I18nProvider>");
  return value;
}

/** Shortcut for components that only need to translate. */
export function useT(): Translate {
  return useI18n().t;
}
