import { useMemo } from "react";

import { useI18n, type Language } from "../i18n";

/**
 * `Intl` locale tag for the interface language — never the browser's
 * (`undefined`): without it, an explicit language setting in the app
 * (Settings) has no effect on the `Intl` APIs if the browser locale differs
 * (weekdays and relative dates shown in the wrong language despite the
 * explicit choice — a bug found during the Lot 8 translation audit).
 */
function localeTag(language: Language): string {
  return language === "fr" ? "fr-FR" : "en-GB";
}

/**
 * Text comparison following the interface language (accents and case
 * ignored, digits compared as numbers: "Motif 2" before "Motif 10").
 */
export function useCompareText(): (a: string, b: string) => number {
  const { language } = useI18n();
  return useMemo(() => {
    const collator = new Intl.Collator(localeTag(language), { sensitivity: "base", numeric: true });
    return (a: string, b: string) => collator.compare(a, b);
  }, [language]);
}

/**
 * Number formatter following the interface language.
 *
 * Stitch counts are read in thousands: without a separator, "45900" takes a
 * reading effort that "45 900" does not.
 */
export function useNumberFormat(): (value: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.NumberFormat(localeTag(language));
    // Safari's narrow no-break space renders badly in some fonts: normalise
    // it to a regular no-break space.
    return (value: number) => formatter.format(value).replace(/ /g, " ");
  }, [language]);
}

export function percent(value: number): string {
  return `${value}%`;
}

/**
 * Formats an age ("12 min ago", "3 days ago"): minutes within the first
 * hour, then hours, days and months.
 *
 * The mockups showed hard-coded dates; a relative date stays correct without
 * depending on when you look at the screen, and translates itself.
 */
export function useRelativeTime(): (hoursAgo: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.RelativeTimeFormat(localeTag(language), { numeric: "auto" });
    return (hoursAgo: number) => {
      // Rounded before choosing the unit, so 59.7 minutes reads "1 hour ago",
      // never "60 minutes ago".
      const minutes = Math.round(hoursAgo * 60);
      if (minutes < 60) return formatter.format(-Math.max(1, minutes), "minute");
      const hours = Math.round(hoursAgo);
      if (hours < 24) return formatter.format(-hours, "hour");
      const days = Math.round(hoursAgo / 24);
      if (days < 30) return formatter.format(-days, "day");
      return formatter.format(-Math.round(days / 30), "month");
    };
  }, [language]);
}

/** Short weekday name ("lun."/"Mon") — `index`: 0 = Monday (ISO), same
 * convention as `ActivityDayOut.weekday` (specification §11). */
export function useWeekdayLabel(): (index: number) => string {
  const { language } = useI18n();
  return useMemo(() => {
    const formatter = new Intl.DateTimeFormat(localeTag(language), { weekday: "short" });
    return (index: number) =>
      // 2024-01-01 was a Monday: a stable offset whatever the locale.
      formatter.format(new Date(Date.UTC(2024, 0, 1 + index)));
  }, [language]);
}
