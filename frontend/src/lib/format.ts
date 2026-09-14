import { useMemo } from "react";

import { useI18n } from "../i18n";

/**
 * Formateur de nombres suivant la langue de l'interface.
 *
 * Les comptages de points se lisent par milliers : sans séparateur, « 45900 »
 * demande un effort de lecture que « 45 900 » n'exige pas.
 */
export function useNumberFormat(): (value: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.NumberFormat(language === "fr" ? "fr-FR" : "en-GB");
    // L'espace fine insécable de Safari passe mal dans certaines polices :
    // on la normalise en espace insécable ordinaire.
    return (value: number) => formatter.format(value).replace(/ /g, " ");
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
    const formatter = new Intl.RelativeTimeFormat(language === "fr" ? "fr-FR" : "en-GB", {
      numeric: "auto",
    });
    return (hoursAgo: number) => {
      if (hoursAgo < 24) return formatter.format(-Math.max(1, Math.round(hoursAgo)), "hour");
      const days = Math.round(hoursAgo / 24);
      if (days < 30) return formatter.format(-days, "day");
      return formatter.format(-Math.round(days / 30), "month");
    };
  }, [language]);
}
