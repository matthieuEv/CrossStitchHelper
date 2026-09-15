/** Conversion des réponses de l'API vers les types du noyau motif (`pattern/types.ts`). */

import type {
  ApiGrid,
  ApiImportPaletteEntry,
  ApiImportPreview,
  ApiPatternDetail,
  ApiProgress,
} from "./api";
import { base64ToBytes, decodeUint16Layer, unpackBitmap } from "./codec";
import type { PaletteEntry, Pattern, Progress } from "../pattern/types";

export function paletteFromApi(detail: ApiPatternDetail): PaletteEntry[] {
  return detail.palette.map((entry) => ({
    code: entry.code,
    name: entry.name,
    hex: entry.rgb_hex,
    symbol: entry.symbol_key,
  }));
}

function paletteFromImportEntries(entries: ApiImportPaletteEntry[]): PaletteEntry[] {
  return entries.map((entry) => ({
    code: entry.code,
    name: entry.name,
    hex: entry.rgb_hex,
    symbol: entry.symbol_key,
  }));
}

/**
 * Assemble un `Pattern` à partir de l'aperçu calculé par l'assistant d'import
 * (Lot 2) — même format compact que `patternFromApi`, pour que l'écran de
 * peinture par zone et le récapitulatif réutilisent tel quel le rendu canvas
 * du suivi (`pattern/render.ts`).
 */
export function patternFromImportPreview(preview: ApiImportPreview, name: string): Pattern {
  const layer = decodeUint16Layer(base64ToBytes(preview.layer_full));
  return {
    id: "import-preview",
    name,
    width: preview.width,
    height: preview.height,
    cells: Uint8Array.from(layer),
    palette: paletteFromImportEntries(preview.palette),
  };
}

/**
 * Assemble un `Pattern` à partir des métadonnées et de la grille.
 *
 * `layer_full` est un `Uint16Array` côté serveur (§6.3, pour accueillir de
 * futures palettes de plus de 255 couleurs) ; le rendu canvas travaille en
 * `Uint8Array` — le rétrécissement est sûr tant qu'un motif reste sous 256
 * couleurs, ce qui couvre très largement tout motif de point de croix réel.
 */
export function patternFromApi(detail: ApiPatternDetail, grid: ApiGrid): Pattern {
  const layer = decodeUint16Layer(base64ToBytes(grid.layer_full));
  return {
    id: detail.id,
    name: detail.name,
    width: detail.width,
    height: detail.height,
    cells: Uint8Array.from(layer),
    palette: paletteFromApi(detail),
  };
}

export function progressFromApi(progress: ApiProgress): Progress {
  return unpackBitmap(base64ToBytes(progress.bitmap), progress.cell_count);
}
