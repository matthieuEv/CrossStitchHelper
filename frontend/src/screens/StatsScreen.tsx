import { useT } from "../i18n";
import { useNumberFormat } from "../lib/format";
import { STITCHES_PER_SKEIN, type ColorCount, type PatternTotals } from "../pattern/counts";
import type { Pattern } from "../pattern/types";

export interface ActivityDay {
  /** Jour de la semaine, 0 = lundi. */
  weekday: number;
  stitches: number;
}

export interface ActivitySession {
  hoursAgo: number;
  stitches: number;
  minutes: number;
}

interface StatsScreenProps {
  pattern: Pattern;
  counts: readonly ColorCount[];
  totals: PatternTotals;
  activity: readonly ActivityDay[];
  sessions: readonly ActivitySession[];
}

export function StatsScreen({ pattern, counts, totals, activity, sessions }: StatsScreenProps) {
  const t = useT();
  const formatNumber = useNumberFormat();

  const peak = activity.reduce((max, day) => Math.max(max, day.stitches), 0);
  const weekdayNames = new Intl.DateTimeFormat(undefined, { weekday: "short" });
  const weekdayLabel = (index: number): string => {
    // 2024-01-01 était un lundi : décalage stable quelle que soit la locale.
    const date = new Date(Date.UTC(2024, 0, 1 + index));
    return weekdayNames.format(date);
  };

  return (
    <div className="screen">
      <h2 style={{ margin: "0 0 4px" }}>{t("stats.title")}</h2>
      <div className="text-muted" style={{ fontSize: 13, marginBottom: 18 }}>
        {pattern.name} · {pattern.width} × {pattern.height}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <div style={{ padding: 20, borderRadius: 26, background: "var(--color-surface)" }}>
          <div
            className="text-muted"
            style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}
          >
            {t("stats.progress")}
          </div>
          <div
            className="num"
            style={{
              fontFamily: "var(--font-heading)",
              fontWeight: "var(--font-heading-weight)" as never,
              fontSize: 56,
              lineHeight: 1,
            }}
          >
            {totals.percent}%
          </div>
          <div className="bar" style={{ height: 10, margin: "14px 0 10px" }}>
            <span style={{ width: `${totals.percent}%` }} />
          </div>
          <div className="text-muted" style={{ fontSize: 13 }}>
            {t("stats.doneOf", {
              done: formatNumber(totals.done),
              total: formatNumber(totals.total),
            })}
          </div>
        </div>

        <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <div className="stat-tile">
            <span style={{ fontSize: 13 }}>{t("stats.remaining")}</span>
            <span className="stat-value num">{formatNumber(totals.remaining)}</span>
          </div>
          <div className="stat-tile">
            <span style={{ fontSize: 13 }}>{t("stats.skeins")}</span>
            <span className="stat-value num">{totals.skeinsRemaining}</span>
          </div>
          <div className="stat-tile">
            <span style={{ fontSize: 13 }}>{t("stats.time")}</span>
            <span className="stat-value num">{t("stats.hours", { count: totals.hoursRemaining })}</span>
          </div>
          <div className="text-faint" style={{ fontSize: 11, lineHeight: 1.5, padding: "0 4px" }}>
            {t("stats.basis")}
          </div>
        </div>
      </div>

      <h4 style={{ margin: "22px 0 10px" }}>{t("stats.byColor")}</h4>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: "6px 24px",
        }}
      >
        {counts.map((count) => (
          <div key={count.index} style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 48 }}>
            <span className="swatch" style={{ width: 26, height: 26, background: count.hex }} />
            <span className="num" style={{ flex: "none", width: 74, fontSize: 13 }}>
              DMC {count.code}
            </span>
            <span className="bar" style={{ flex: 1, minWidth: 40, height: 10 }}>
              <span style={{ width: `${Math.round(count.ratio * 100)}%`, background: count.hex }} />
            </span>
            <span className="text-muted num" style={{ flex: "none", width: 58, textAlign: "right", fontSize: 12 }}>
              {Math.round(count.ratio * 100)}%
            </span>
            <span className="num" style={{ flex: "none", width: 60, textAlign: "right", fontSize: 12 }}>
              {t("stats.skeinsShort", {
                count: Math.ceil(count.remaining / STITCHES_PER_SKEIN),
              })}
            </span>
          </div>
        ))}
      </div>

      <h4 style={{ margin: "26px 0 10px" }}>{t("stats.activity")}</h4>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: 8,
          height: 96,
          padding: "12px 16px",
          borderRadius: 22,
          background: "var(--color-surface)",
        }}
      >
        {activity.map((day) => {
          const ratio = peak === 0 ? 0 : day.stitches / peak;
          return (
            <div
              key={day.weekday}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-end",
                alignItems: "center",
                gap: 6,
                height: "100%",
              }}
            >
              <div
                style={{
                  width: "100%",
                  borderRadius: "8px 8px 3px 3px",
                  height: `${Math.max(4, ratio * 100)}%`,
                  background:
                    ratio > 0.7
                      ? "var(--color-accent)"
                      : "color-mix(in srgb, var(--color-accent) 45%, transparent)",
                }}
              />
              <div className="text-muted" style={{ fontSize: 10 }}>
                {weekdayLabel(day.weekday)}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 10 }}>
        {sessions.map((session) => (
          <div
            key={session.hoursAgo}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              minHeight: 48,
              padding: "0 4px",
              borderBottom: "1px solid color-mix(in srgb, var(--color-text) 8%, transparent)",
            }}
          >
            <span style={{ fontSize: 13 }}>
              {new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
                -Math.round(session.hoursAgo / 24) || -1,
                Math.round(session.hoursAgo / 24) >= 1 ? "day" : "hour",
              )}
            </span>
            <span className="text-muted num" style={{ fontSize: 13 }}>
              {formatNumber(session.stitches)} · {session.minutes} min
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
