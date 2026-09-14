/** Types du noyau « motif ». */

export interface PaletteEntry {
  /** Code du fil dans la marque choisie (ex. « 3346 » pour DMC). */
  code: string;
  name: string;
  /** Couleur d'affichage, en hexadécimal `#rrggbb`. */
  hex: string;
  /** Symbole affiché dans la case au zoom élevé. */
  symbol: string;
}

/**
 * Une grille de motif.
 *
 * `cells` contient un index de palette par case (0 = case vide), rangée par
 * rangée. Un octet par case : un motif de 255 × 180 tient dans 45 Ko, ce qui
 * autorise à le garder entièrement en mémoire et à ne redessiner que la
 * portion visible.
 */
export interface Pattern {
  readonly id: string;
  readonly name: string;
  readonly width: number;
  readonly height: number;
  readonly cells: Uint8Array;
  readonly palette: readonly PaletteEntry[];
}

/**
 * Progression de broderie.
 *
 * Stockée **séparément** de la grille (contrainte structurante du cahier des
 * charges) : un ré-import du PDF source remplace `Pattern`, jamais `done`.
 * Même indexation que `Pattern.cells` ; 1 signifie « case brodée ».
 */
export type Progress = Uint8Array;

export function emptyProgress(pattern: Pattern): Progress {
  return new Uint8Array(pattern.width * pattern.height);
}

export function cellIndex(pattern: Pattern, x: number, y: number): number {
  return y * pattern.width + x;
}

export function isInside(pattern: Pattern, x: number, y: number): boolean {
  return x >= 0 && x < pattern.width && y >= 0 && y < pattern.height;
}
