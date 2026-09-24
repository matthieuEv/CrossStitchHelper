import { useNumberFormat } from "../lib/format";
import { useT } from "../i18n";
import type { ColorCount } from "../pattern/counts";

interface ColorListProps {
  counts: readonly ColorCount[];
  highlight: number;
  onToggle: (index: number) => void;
  /** Hides fully stitched colours: there is nothing left to do on them. */
  hideFinished?: boolean;
}

/**
 * List of the pattern's threads, with the number of remaining stitches.
 *
 * Shared by the permanent panel (wide screen) and the drawer (narrow screen):
 * the same information, presented at the same place in the visual hierarchy.
 */
export function ColorList({ counts, highlight, onToggle, hideFinished = false }: ColorListProps) {
  const t = useT();
  const formatNumber = useNumberFormat();
  const visible = hideFinished ? counts.filter((count) => count.remaining > 0) : counts;

  return (
    <>
      {visible.map((count) => (
        <button
          key={count.index}
          type="button"
          className="color-row"
          aria-pressed={highlight === count.index}
          onClick={() => onToggle(count.index)}
        >
          <span
            className="swatch"
            style={{ width: 32, height: 32, background: count.hex }}
          />
          <span style={{ flex: "none", width: 22, textAlign: "center", opacity: 0.75 }}>
            {count.symbolSvg !== undefined ? (
              // Real symbol cut out of the PDF (Lot 4) — see `pattern/render.ts`
              // for the same principle on the canvas side (falls back to
              // `count.symbol` while no real symbol is available).
              <img
                src={`data:image/svg+xml;base64,${btoa(count.symbolSvg)}`}
                alt={count.symbol}
                style={{ width: 18, height: 18, verticalAlign: "middle" }}
              />
            ) : (
              count.symbol
            )}
          </span>
          {/* `overflow: hidden` here too, not just on each row: without it, a
              long thread name (the real DMC legends of Lot 4 are much longer
              than the demo names) can push this block to a negative width once
              the neighbouring columns (swatch, symbol, counter) are counted —
              the text then overflowed without an ellipsis until it was cut off
              sharply by the panel's scrolling container, several levels up. */}
          <span style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
            <span
              style={{
                display: "block",
                fontSize: 14,
                fontWeight: 600,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              DMC {count.code}
            </span>
            <span
              className="text-muted"
              style={{
                display: "block",
                fontSize: 12,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {count.name}
            </span>
          </span>
          <span style={{ flex: "none", textAlign: "right" }}>
            <span className="num" style={{ display: "block", fontSize: 14 }}>
              {formatNumber(count.remaining)}
            </span>
            <span className="text-faint" style={{ display: "block", fontSize: 11 }}>
              {t("track.remainingLabel")}
            </span>
          </span>
        </button>
      ))}
    </>
  );
}
