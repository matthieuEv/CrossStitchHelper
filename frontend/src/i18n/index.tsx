/**
 * Internationalisation minimale et typée.
 *
 * Volontairement écrite à la main plutôt qu'avec i18next : l'application n'a
 * besoin ni de pluriels complexes, ni de chargement à la demande, ni de
 * détection de locale évoluée, et une instance auto-hébergée gagne à ne pas
 * traîner de dépendance superflue (cahier des charges §3).
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
    // Safari en navigation privée refuse localStorage : on retombe sur la
    // langue du navigateur plutôt que de planter au démarrage.
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
      // Préférence non mémorisée : sans gravité, l'interface reste correcte.
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
  if (value === null) throw new Error("useI18n doit être utilisé dans <I18nProvider>");
  return value;
}

/** Raccourci pour les composants qui n'ont besoin que de traduire. */
export function useT(): Translate {
  return useI18n().t;
}
