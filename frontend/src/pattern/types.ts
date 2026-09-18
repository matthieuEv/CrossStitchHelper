/** Types du noyau « motif ». */

export interface PaletteEntry {
  /** Code du fil dans la marque choisie (ex. « 3346 » pour DMC). */
  code: string;
  name: string;
  /** Couleur d'affichage, en hexadécimal `#rrggbb`. */
  hex: string;
  /** Symbole affiché dans la case au zoom élevé — repli textuel tant que
   * `symbolSvg` n'est pas disponible ou pas encore chargé. */
  symbol: string;
  /** Symbole réel découpé depuis le PDF source (Lot 4), un `<svg>` autonome
   * prêt à être affiché — voir `pattern/render.ts` pour le rendu et le
   * cache d'images. Absent pour une palette saisie à la main (Lot 2). */
  symbolSvg?: string;
}

/**
 * Un trait de point arrière (Lot 8), en coordonnées de **coins** de case :
 * (0, 0) est le coin haut-gauche de la case (0, 0), (1, 0) le coin
 * haut-droit de cette même case — jamais un pixel ni un centre de case, même
 * convention que `backend/app/schemas.py::BackstitchSegment`. `paletteIndex`
 * est 1-based, comme `Pattern.cells`.
 */
export interface BackstitchSegment {
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
  readonly paletteIndex: number;
}

/**
 * Un point de nœud (Lot 8), en coordonnées de **centre** de case : (0.5,
 * 0.5) est le centre de la case (0, 0) — jamais un coin (contrairement à
 * `BackstitchSegment`) ni un pixel. Même convention que
 * `backend/app/schemas.py::FrenchKnot`.
 */
export interface FrenchKnot {
  readonly x: number;
  readonly y: number;
  readonly paletteIndex: number;
}

/** Les cinq catégories de points suivies (Lot 8) — même énumération que
 * `backend/app/schemas.py::ProgressOp.layer`, jamais un espace d'index
 * partagé entre catégories (un index de grille pour `full`/`half`/`quarter`,
 * un index dans `Pattern.backstitch`/`frenchKnots` pour `backstitch`/`knot`). */
export type StitchLayer = "full" | "half" | "quarter" | "backstitch" | "knot";

/**
 * Une grille de motif.
 *
 * `cells` contient un index de palette par case (0 = case vide), rangée par
 * rangée. Un octet par case : un motif de 255 × 180 tient dans 45 Ko, ce qui
 * autorise à le garder entièrement en mémoire et à ne redessiner que la
 * portion visible.
 *
 * `cellsHalf`/`cellsQuarter` (Lot 8) suivent exactement la même convention
 * que `cells`, même taille — toujours présents (jamais `undefined`), remplis
 * de zéros quand le motif n'a aucun point 1/2 ou 1/4 : le rendu et le suivi
 * n'ont ainsi jamais besoin de cas particulier « couche absente ». Une case
 * peut porter une valeur non nulle dans plusieurs de ces couches à la fois
 * (§6.3 : ce sont des couches indépendantes, pas des variantes exclusives
 * d'une même case).
 */
export interface Pattern {
  readonly id: string;
  readonly name: string;
  readonly width: number;
  readonly height: number;
  readonly cells: Uint8Array;
  readonly cellsHalf: Uint8Array;
  readonly cellsQuarter: Uint8Array;
  readonly backstitch: readonly BackstitchSegment[];
  readonly frenchKnots: readonly FrenchKnot[];
  readonly palette: readonly PaletteEntry[];
}

/**
 * Progression des quatre catégories de points spéciaux (Lot 8), séparée de
 * `Progress` (point entier, ci-dessous) — volontairement, pour ne changer la
 * forme de `Progress` nulle part où elle est déjà consommée (statistiques,
 * bibliothèque, démonstration...) : `Progress` continue de ne représenter
 * que le point entier, seul comptant pour le pourcentage global (§7.1).
 *
 * `half`/`quarter` ont la même taille que `Pattern.cells` (1 octet 0/1 par
 * case, comme `Progress`) ; `backstitch`/`knot` ont la taille de
 * `Pattern.backstitch`/`frenchKnots` (1 octet 0/1 par élément, jamais par
 * case — ce ne sont pas des grilles).
 */
export interface SpecialProgress {
  half: Uint8Array;
  quarter: Uint8Array;
  backstitch: Uint8Array;
  knot: Uint8Array;
}

export function emptySpecialProgress(pattern: Pattern): SpecialProgress {
  return {
    half: new Uint8Array(pattern.width * pattern.height),
    quarter: new Uint8Array(pattern.width * pattern.height),
    backstitch: new Uint8Array(pattern.backstitch.length),
    knot: new Uint8Array(pattern.frenchKnots.length),
  };
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
