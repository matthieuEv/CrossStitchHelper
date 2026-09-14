/**
 * Motif de démonstration — « Bouquet de lavande », 140 × 100, 16 couleurs DMC.
 *
 * Généré de façon déterministe : le même dessin à chaque chargement. Sert à
 * développer et à mesurer le rendu tant que le moteur d'extraction (Lots 4 à
 * 7) n'existe pas. **Rien ici ne doit survivre à l'arrivée de l'import réel**
 * autre que comme jeu de démonstration.
 */

import type { PaletteEntry, Pattern, Progress } from "../pattern/types";

export const DEMO_WIDTH = 140;
export const DEMO_HEIGHT = 100;

export const DEMO_PALETTE: readonly PaletteEntry[] = [
  { code: "3743", name: "Lavande très clair", hex: "#dcd0e0", symbol: "·" },
  { code: "211", name: "Lavande clair", hex: "#d3bfd8", symbol: ":" },
  { code: "210", name: "Lavande moyen", hex: "#bfa2cb", symbol: "o" },
  { code: "209", name: "Lavande foncé", hex: "#a07cb0", symbol: "x" },
  { code: "208", name: "Lavande très foncé", hex: "#855b9b", symbol: "▲" },
  { code: "3835", name: "Violet raisin moyen", hex: "#7a5c8f", symbol: "■" },
  { code: "3834", name: "Violet raisin foncé", hex: "#5c3a66", symbol: "◆" },
  { code: "340", name: "Bleu myosotis", hex: "#b3b0d8", symbol: "∨" },
  { code: "3746", name: "Violet bleuté foncé", hex: "#6a5f9e", symbol: "≡" },
  { code: "524", name: "Vert fougère clair", hex: "#b9c2a8", symbol: "/" },
  { code: "522", name: "Vert fougère", hex: "#a3ae90", symbol: "\\" },
  { code: "3052", name: "Vert gris moyen", hex: "#929a7b", symbol: "+" },
  { code: "3051", name: "Vert gris foncé", hex: "#5d6647", symbol: "★" },
  { code: "3013", name: "Vert kaki clair", hex: "#b5b393", symbol: "−" },
  { code: "3364", name: "Vert pin", hex: "#8a9a6a", symbol: "=" },
  { code: "3041", name: "Mauve gris moyen", hex: "#8a6f88", symbol: "♦" },
];

/** Générateur pseudo-aléatoire à graine, pour un motif reproductible. */
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

/** Rasterise du texte en cases, pour l'inscription cursive du bas du motif. */
function rasterText(text: string, font: string, width: number, height: number): Array<[number, number]> {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const g = canvas.getContext("2d");
  if (g === null) return [];

  g.clearRect(0, 0, width, height);
  g.fillStyle = "#000";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = font;
  g.fillText(text, width / 2, height / 2);

  const pixels = g.getImageData(0, 0, width, height).data;
  const cells: Array<[number, number]> = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if ((pixels[(y * width + x) * 4 + 3] ?? 0) > 110) cells.push([x, y]);
    }
  }
  return cells;
}

function buildCells(): Uint8Array {
  const cells = new Uint8Array(DEMO_WIDTH * DEMO_HEIGHT);
  const set = (x: number, y: number, value: number): void => {
    const cx = Math.round(x);
    const cy = Math.round(y);
    if (cx >= 0 && cx < DEMO_WIDTH && cy >= 0 && cy < DEMO_HEIGHT) {
      cells[cy * DEMO_WIDTH + cx] = value;
    }
  };
  const random = seededRandom(20260913);

  const stalks = [
    { baseX: 40, top: 30, lean: -7 },
    { baseX: 52, top: 20, lean: -4 },
    { baseX: 63, top: 13, lean: -1 },
    { baseX: 74, top: 16, lean: 2 },
    { baseX: 85, top: 24, lean: 5 },
    { baseX: 96, top: 34, lean: 8 },
    { baseX: 70, top: 40, lean: 0 },
  ];
  const baseY = 78;
  const greens = [10, 11, 12, 13, 15];

  stalks.forEach((stalk, i) => {
    const stemColor = greens[i % greens.length] ?? 11;
    const xAt = (y: number): number => {
      const t = (baseY - y) / (baseY - stalk.top);
      return stalk.baseX + stalk.lean * t * t + Math.sin(t * 3.1 + i) * 1.6;
    };

    for (let y = baseY; y >= stalk.top; y--) {
      const x = xAt(y);
      set(x, y, stemColor);
      if (y % 2 === 0) set(x + 1, y, y > stalk.top + 26 ? stemColor : 12);
    }

    for (let k = 0; k < 3; k++) {
      const leafY = stalk.top + 30 + k * 13;
      if (leafY > baseY - 3) continue;
      const direction = (k + i) % 2 ? 1 : -1;
      const leafColor = greens[(i + k + 1) % greens.length] ?? 10;
      const length = 7 + Math.floor(random() * 5);
      for (let t = 1; t <= length; t++) {
        const lx = xAt(leafY) + direction * t;
        const ly = leafY - t * 0.55;
        set(lx, ly, leafColor);
        if (t > 1 && t < length - 1) set(lx, ly + 1, t < length / 2 ? 14 : leafColor);
      }
    }

    const spikeHeight = 26;
    for (let t = 0; t < spikeHeight; t++) {
      const y = stalk.top + t;
      const profile = Math.sin(Math.PI * (t / spikeHeight) ** 0.75) * 4.2 + 1;
      for (let dx = -Math.round(profile); dx <= Math.round(profile); dx++) {
        const ratio = Math.abs(dx) / (profile + 0.001);
        const jitter = random();
        let color: number;
        if (ratio > 0.72) color = jitter > 0.5 ? 1 : 2;
        else if (ratio > 0.45) color = jitter > 0.45 ? 3 : 8;
        else if (ratio > 0.2) color = jitter > 0.5 ? 4 : 5;
        else color = jitter > 0.62 ? 7 : jitter > 0.3 ? 6 : 9;
        if (t < 3 && ratio > 0.5) continue;
        set(xAt(y) + dx, y, color);
      }
    }
  });

  // Lien du bouquet.
  for (let y = 72; y <= 76; y++) {
    for (let x = 58; x <= 84; x++) {
      if ((x + y) % 3 !== 0) set(x, y, y % 2 ? 16 : 3);
    }
  }

  const script = 'italic 700 19px "Snell Roundhand","Brush Script MT","Segoe Script",cursive';
  for (const [x, y] of rasterText("Provence", script, DEMO_WIDTH, 22)) {
    set(x, y + 82, 16);
  }

  return cells;
}

export function createDemoPattern(): Pattern {
  return {
    id: "demo-lavender",
    name: "Bouquet de lavande",
    width: DEMO_WIDTH,
    height: DEMO_HEIGHT,
    cells: buildCells(),
    palette: DEMO_PALETTE,
  };
}

/** Progression de départ : le bas du motif déjà brodé, convention courante. */
export function createDemoProgress(pattern: Pattern): Progress {
  const done = new Uint8Array(pattern.width * pattern.height);
  for (let y = 62; y < pattern.height; y++) {
    for (let x = 0; x < pattern.width; x++) {
      const index = y * pattern.width + x;
      if (pattern.cells[index] && (y < 70 ? x < 104 : true)) done[index] = 1;
    }
  }
  return done;
}
