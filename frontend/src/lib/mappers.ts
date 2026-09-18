/** Conversion des réponses de l'API vers les types du noyau motif (`pattern/types.ts`). */

import type {
  ApiGrid,
  ApiImportPaletteEntry,
  ApiImportPreview,
  ApiPatternDetail,
  ApiProgress,
} from "./api";
import { base64ToBytes, decodeUint16Layer, unpackBitmap } from "./codec";
import type { PaletteEntry, Pattern, Progress, SpecialProgress } from "../pattern/types";

export function paletteFromApi(detail: ApiPatternDetail): PaletteEntry[] {
  return detail.palette.map((entry) => ({
    code: entry.code,
    name: entry.name,
    hex: entry.rgb_hex,
    symbol: entry.symbol_key,
    ...(entry.symbol_svg !== null && { symbolSvg: entry.symbol_svg }),
  }));
}

function paletteFromImportEntries(entries: ApiImportPaletteEntry[]): PaletteEntry[] {
  return entries.map((entry) => ({
    code: entry.code,
    name: entry.name,
    hex: entry.rgb_hex,
    symbol: entry.symbol_key,
    ...(entry.symbol_svg !== null &&
      entry.symbol_svg !== undefined && { symbolSvg: entry.symbol_svg }),
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
  const cellCount = preview.width * preview.height;
  return {
    id: "import-preview",
    name,
    width: preview.width,
    height: preview.height,
    cells: Uint8Array.from(layer),
    // L'assistant d'import (Lots 2, 4, 5) ne produit que le point entier —
    // le point arrière/nœuds/1-2/1-4 restent le périmètre du Lot 9, pas
    // encore construit : couches toujours présentes mais vides ici, jamais
    // `undefined` (voir `Pattern.cellsHalf`).
    cellsHalf: new Uint8Array(cellCount),
    cellsQuarter: new Uint8Array(cellCount),
    backstitch: [],
    frenchKnots: [],
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
  const cellCount = grid.width * grid.height;
  const half = grid.layer_half !== null ? decodeUint16Layer(base64ToBytes(grid.layer_half)) : null;
  const quarter =
    grid.layer_quarter !== null ? decodeUint16Layer(base64ToBytes(grid.layer_quarter)) : null;
  return {
    id: detail.id,
    name: detail.name,
    width: detail.width,
    height: detail.height,
    cells: Uint8Array.from(layer),
    // Toujours présentes (même vides) — voir `Pattern.cellsHalf` : le rendu
    // et le suivi n'ont ainsi jamais de cas particulier « couche absente ».
    cellsHalf: half !== null ? Uint8Array.from(half) : new Uint8Array(cellCount),
    cellsQuarter: quarter !== null ? Uint8Array.from(quarter) : new Uint8Array(cellCount),
    backstitch: grid.backstitch.map((segment) => ({
      x1: segment.x1,
      y1: segment.y1,
      x2: segment.x2,
      y2: segment.y2,
      paletteIndex: segment.palette_index,
    })),
    frenchKnots: grid.french_knots.map((knot) => ({
      x: knot.x,
      y: knot.y,
      paletteIndex: knot.palette_index,
    })),
    palette: paletteFromApi(detail),
  };
}

export function progressFromApi(progress: ApiProgress): Progress {
  return unpackBitmap(base64ToBytes(progress.bitmap), progress.cell_count);
}

/**
 * Assemble la progression des quatre catégories de points spéciaux (Lot 8) à
 * partir de `GET /grid` (tailles) et `GET /progress` (bitmaps) — séparé de
 * `progressFromApi` (point entier) pour ne pas changer sa forme, voir
 * `SpecialProgress`.
 */
export function specialProgressFromApi(grid: ApiGrid, progress: ApiProgress): SpecialProgress {
  const cellCount = grid.width * grid.height;
  const backstitchCount = grid.backstitch.length;
  const knotCount = grid.french_knots.length;
  return {
    half:
      progress.bitmap_half !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_half), cellCount)
        : new Uint8Array(cellCount),
    quarter:
      progress.bitmap_quarter !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_quarter), cellCount)
        : new Uint8Array(cellCount),
    backstitch:
      progress.bitmap_backstitch !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_backstitch), backstitchCount)
        : new Uint8Array(backstitchCount),
    knot:
      progress.bitmap_knots !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_knots), knotCount)
        : new Uint8Array(knotCount),
  };
}
