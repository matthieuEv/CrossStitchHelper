import { useNumberFormat } from "../lib/format";
import { useT } from "../i18n";
import type { ColorCount } from "../pattern/counts";

interface ColorListProps {
  counts: readonly ColorCount[];
  highlight: number;
  onToggle: (index: number) => void;
  /** Masque les couleurs entièrement brodées : il n'y a plus rien à y faire. */
  hideFinished?: boolean;
}

/**
 * Liste des fils du motif, avec le nombre de points restants.
 *
 * Partagée par le panneau permanent (écran large) et le tiroir (écran étroit) :
 * la même information, présentée au même endroit dans la hiérarchie visuelle.
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
              // Symbole réel découpé du PDF (Lot 4) — voir `pattern/render.ts`
              // pour le même principe côté canvas (repli sur `count.symbol`
              // tant qu'aucun symbole réel n'est disponible).
              <img
                src={`data:image/svg+xml;base64,${btoa(count.symbolSvg)}`}
                alt={count.symbol}
                style={{ width: 18, height: 18, verticalAlign: "middle" }}
              />
            ) : (
              count.symbol
            )}
          </span>
          {/* `overflow: hidden` ici aussi, pas seulement sur chaque ligne : sans
              ça, un nom de fil long (les vraies légendes DMC du Lot 4 sont bien
              plus longues que les noms de démonstration) peut pousser ce bloc à
              une largeur négative une fois les colonnes voisines (pastille,
              symbole, compteur) comptées — le texte débordait alors sans points
              de suspension jusqu'à être coupé net par le conteneur défilant du
              panneau, plusieurs niveaux plus haut. */}
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
