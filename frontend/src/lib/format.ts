import { useMemo } from "react";

import { useI18n, type Language } from "../i18n";

/**
 * Balise de locale `Intl` pour la langue de l'interface — jamais celle du
 * navigateur (`undefined`) : sans ça, un réglage de langue explicite dans
 * l'appli (Réglages) n'a aucun effet sur les API `Intl` si la locale du
 * navigateur diffère (jours de la semaine, dates relatives affichés dans la
 * mauvaise langue malgré le choix explicite — bug trouvé lors de l'audit des
 * traductions du Lot 8).
 */
function localeTag(language: Language): string {
  return language === "fr" ? "fr-FR" : "en-GB";
}

/**
 * Formateur de nombres suivant la langue de l'interface.
 *
 * Les comptages de points se lisent par milliers : sans séparateur, « 45900 »
 * demande un effort de lecture que « 45 900 » n'exige pas.
 */
export function useNumberFormat(): (value: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.NumberFormat(localeTag(language));
    // L'espace fine insécable de Safari passe mal dans certaines polices :
    // on la normalise en espace insécable ordinaire.
    return (value: number) => formatter.format(value).replace(/ /g, " ");
  }, [language]);
}

export function percent(value: number): string {
  return `${value}%`;
}

/**
 * Formate une ancienneté (« il y a 3 jours »).
 *
 * Les maquettes affichaient des dates écrites en dur ; une date relative reste
 * juste sans dépendre du moment où l'on regarde l'écran, et se traduit seule.
 */
export function useRelativeTime(): (hoursAgo: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.RelativeTimeFormat(localeTag(language), { numeric: "auto" });
    return (hoursAgo: number) => {
      if (hoursAgo < 24) return formatter.format(-Math.max(1, Math.round(hoursAgo)), "hour");
      const days = Math.round(hoursAgo / 24);
      if (days < 30) return formatter.format(-days, "day");
      return formatter.format(-Math.round(days / 30), "month");
    };
  }, [language]);
}

/** Nom court d'un jour de la semaine (« lun. »/« Mon ») — `index` : 0 = lundi
 * (ISO), même convention que `ActivityDayOut.weekday` (cahier des charges
 * §11). */
export function useWeekdayLabel(): (index: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.DateTimeFormat(localeTag(language), { weekday: "short" });
    return (index: number) =>
      // 2024-01-01 était un lundi : décalage stable quelle que soit la locale.
      formatter.format(new Date(Date.UTC(2024, 0, 1 + index)));
  }, [language]);
}

/**
 * Ancienneté d'une séance de broderie (« il y a 12 min ») — granularité plus
 * fine que `useRelativeTime` (minutes dès la première heure), utile pour une
 * séance qui vient tout juste de se terminer ; distinct exprès de
 * `useRelativeTime`, qui commence à l'heure pour un historique plus large.
 */
export function useSessionRelativeTime(): (hoursAgo: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.RelativeTimeFormat(localeTag(language), { numeric: "auto" });
    return (hoursAgo: number) => {
      if (hoursAgo < 1) return formatter.format(-Math.max(1, Math.round(hoursAgo * 60)), "minute");
      if (hoursAgo < 24) return formatter.format(-Math.round(hoursAgo), "hour");
      return formatter.format(-Math.round(hoursAgo / 24), "day");
    };
  }, [language]);
}
