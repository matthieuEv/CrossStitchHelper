/**
 * Secondary demo patterns, to give the library its real shape (several
 * cards, several sizes, several progress states). Removable without
 * consequence once real import exists.
 */

import type { PaletteEntry, Pattern, Progress } from "../pattern/types";

type VariantKind = "herbarium" | "chart" | "alphabet";

const VARIANT_PALETTES: Record<VariantKind, readonly string[]> = {
  herbarium: ["#b5763c", "#8a5a2b", "#c9903f", "#8a9a6a", "#5d6647", "#a3ae90"],
  chart: ["#4a6d8c", "#7d9bb5", "#b8cbd8", "#2e4a63", "#c9b590"],
  alphabet: ["#5c3a66", "#8a6f88", "#2e2b25", "#a19786"],
};

const VARIANT_SIZES: Record<VariantKind, [number, number]> = {
  herbarium: [96, 120],
  chart: [200, 140],
  alphabet: [80, 80],
};

const SYMBOLS = ["·", ":", "o", "x", "▲", "■"];

function paletteFor(kind: VariantKind): PaletteEntry[] {
  return (VARIANT_PALETTES[kind] ?? []).map((hex, i) => ({
    code: `—`,
    name: "",
    hex,
    symbol: SYMBOLS[i] ?? "·",
  }));
}

function seededRandom(seed: number): () => number {
  let state = seed;
  return () => {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildVariant(kind: VariantKind): { cells: Uint8Array; width: number; height: number } {
  const [width, height] = VARIANT_SIZES[kind];
  const cells = new Uint8Array(width * height);
  const set = (x: number, y: number, value: number): void => {
    const cx = Math.round(x);
    const cy = Math.round(y);
    if (cx >= 0 && cx < width && cy >= 0 && cy < height) cells[cy * width + cx] = value;
  };
  const random = seededRandom(kind.length * 7919 + 13);

  if (kind === "herbarium") {
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 2; c++) {
        const cx = 24 + c * 48;
        const baseY = 34 + r * 38;
        const stem = 4 + ((r + c) % 2);
        for (let y = baseY; y > baseY - 26; y--) {
          set(cx + Math.sin((baseY - y) * 0.2) * 1.5, y, stem);
        }
        for (let k = 0; k < 5; k++) {
          const leafY = baseY - 4 - k * 4.6;
          const length = 9 - k;
          const colour = 1 + ((k + r + c) % 3);
          for (let d = -1; d <= 1; d += 2) {
            for (let t = 1; t <= length; t++) {
              set(cx + d * t, leafY - t * 0.45, t > length - 3 ? colour + 2 : colour);
              if (t < length - 2) set(cx + d * t, leafY - t * 0.45 + 1, colour);
            }
          }
        }
        for (let t = 0; t < 4; t++) set(cx, baseY - 28 - t, 3);
      }
    }
  }

  if (kind === "chart") {
    for (let x = 6; x < width - 6; x++) {
      set(x, 6, 4);
      set(x, height - 7, 4);
      if (x % 4) {
        set(x, 9, 3);
        set(x, height - 10, 3);
      }
    }
    for (let y = 6; y < height - 6; y++) {
      set(6, y, 4);
      set(width - 7, y, 4);
      if (y % 4) {
        set(9, y, 3);
        set(width - 10, y, 3);
      }
    }
    for (let x = 20; x < width - 20; x++) {
      const y = 74 + Math.sin(x * 0.11) * 16 + Math.sin(x * 0.31) * 5;
      for (let t = 0; t < 3; t++) set(x, y + t, t === 0 ? 1 : 2);
      if (x % 7 === 0) for (let t = 3; t < 8; t++) set(x, y + t, 3);
    }
    for (let i = 0; i < 5; i++) {
      const ix = 30 + random() * (width - 60);
      const iy = 28 + random() * 24;
      const radius = 3 + random() * 5;
      for (let a = 0; a < 360; a += 6) {
        for (let q = 0; q < radius; q++) {
          set(
            ix + Math.cos(a / 57.3) * q,
            iy + Math.sin(a / 57.3) * q * 0.7,
            q > radius - 2 ? 1 : 5,
          );
        }
      }
    }
    const rx = width - 36;
    const ry = height - 40;
    for (let t = -13; t <= 13; t++) {
      set(rx + t, ry, 4);
      set(rx, ry + t, 4);
      if (Math.abs(t) < 9) {
        set(rx + t, ry + t, 2);
        set(rx + t, ry - t, 2);
      }
    }
  }

  if (kind === "alphabet") {
    for (let x = 8; x < width - 8; x++) {
      set(x, 30, 4);
      set(x, 72, 4);
    }
    for (let block = 0; block < 3; block++) {
      for (let i = 0; i < 3; i++) {
        const ox = 12 + i * 22;
        const oy = 8 + block * 26;
        for (let y = 0; y < 14; y++) {
          set(ox, oy + y, 1 + (block % 3));
          set(ox + 10, oy + y, 1 + (block % 3));
        }
        for (let x = 0; x <= 10; x++) set(ox + x, oy + 7, 2);
      }
    }
  }

  return { cells, width, height };
}

export interface DemoLibraryEntry {
  pattern: Pattern;
  progress: Progress;
  /** Age of the last session, in hours. */
  hoursAgo: number;
}

function progressFromFraction(
  cells: Uint8Array,
  width: number,
  height: number,
  fraction: number,
): Progress {
  const done = new Uint8Array(width * height);
  const cut = Math.round(height * (1 - fraction));
  for (let y = cut; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const index = y * width + x;
      if (cells[index]) done[index] = 1;
    }
  }
  return done;
}

export function createDemoVariants(): DemoLibraryEntry[] {
  const definitions: Array<{ kind: VariantKind; id: string; name: string; fraction: number; hoursAgo: number }> = [
    { kind: "herbarium", id: "demo-herbarium", name: "Herbier d'automne", fraction: 0.71, hoursAgo: 72 },
    { kind: "chart", id: "demo-chart", name: "Carte marine, Bréhat", fraction: 0.12, hoursAgo: 336 },
    { kind: "alphabet", id: "demo-alphabet", name: "Alphabet ancien", fraction: 1, hoursAgo: 2160 },
  ];

  return definitions.map((definition) => {
    const built = buildVariant(definition.kind);
    const pattern: Pattern = {
      id: definition.id,
      name: definition.name,
      width: built.width,
      height: built.height,
      cells: built.cells,
      // Purely local demo patterns: no special stitch (Lot 8) — see
      // `demo/lavender.ts::createDemoPattern` for the same note.
      cellsHalf: new Uint8Array(built.width * built.height),
      cellsQuarter: new Uint8Array(built.width * built.height),
      backstitch: [],
      frenchKnots: [],
      palette: paletteFor(definition.kind),
    };
    return {
      pattern,
      progress: progressFromFraction(built.cells, built.width, built.height, definition.fraction),
      hoursAgo: definition.hoursAgo,
    };
  });
}
