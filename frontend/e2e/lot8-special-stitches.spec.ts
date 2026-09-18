import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 8 (docs/roadmap.md) : le rendu
 * affiche les quatre catégories de points spéciaux (1/2, 1/4, point arrière,
 * nœud) du motif de démonstration, et cocher un point de chaque catégorie
 * persiste après rechargement — contre un vrai backend, pas des mocks.
 *
 * Géométrie du petit motif décoratif de `backend/app/seed.py`
 * (`_build_special_stitches`), centré sur la case (127, 90) — coordonnées
 * reprises telles quelles plutôt que devinées, pour ne pas dépendre d'une
 * heuristique de détection à l'écran :
 * - point arrière : quatre segments en losange, coins (127,75) (142,90)
 *   (127,105) (112,90) ; les segments 0 et 1 sont déjà cochés au seed, le
 *   segment 2 (bas→gauche) ne l'est pas.
 * - nœuds : centres (127.5,70.5) (121.5,87.5) (132.5,88.5) (123.5,96.5)
 *   (133.5,97.5) (127.5,110.5) ; les index 0, 2, 4 sont déjà cochés, l'index
 *   1 ne l'est pas.
 * - point 1/2 (couleur 798) et 1/4 (couleur 816) : cases dispersées autour du
 *   centre — la case (117,104) porte un point 1/2 non coché, la case
 *   (109,95) un point 1/4 non coché (les plus proches du centre sont cochées
 *   au seed, voir le commentaire de `_build_special_stitches`).
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** `backend/app/seed.py` — identifiant stable, jamais régénéré. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

/** Centre du petit motif décoratif (`backend/app/seed.py::_CX, _CY`). */
const CENTER = { x: 127, y: 90 };

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Motif de démonstration introuvable en base");
  return demo;
}

type StitchLayer = "full" | "half" | "quarter" | "backstitch" | "knot";

/** Force un état absolu pour un élément d'une catégorie donnée — idempotent
 * côté serveur (§9), donc une base connue fiable quel que soit l'état laissé
 * par une exécution précédente du test (même principe que
 * lot1-persistence.spec.ts : « vider avant de remplir »). `base_version` n'a
 * pas besoin d'être exact : les opérations s'appliquent inconditionnellement
 * (voir `backend/app/api/patterns.py::sync_progress`), seul `missing_ops`
 * (ignoré ici) en dépend. */
async function setStitched(
  request: APIRequestContext,
  patternId: string,
  layer: StitchLayer,
  index: number,
  stitched: boolean,
): Promise<void> {
  const response = await request.post(`/api/patterns/${patternId}/progress`, {
    data: { base_version: 0, ops: [{ layer, index, stitched }] },
  });
  if (!response.ok()) {
    throw new Error(`Échec de la mise à jour de progression (${layer}#${index}) : ${response.status()}`);
  }
}

function bitSet(base64: string | null, index: number): boolean {
  if (base64 === null) return false;
  const byte = Buffer.from(base64, "base64")[index >> 3] ?? 0;
  return ((byte >> (index & 7)) & 1) === 1;
}

interface ProgressResponse {
  bitmap_half: string | null;
  bitmap_quarter: string | null;
  bitmap_backstitch: string | null;
  bitmap_knots: string | null;
}

async function fetchProgress(request: APIRequestContext, patternId: string): Promise<ProgressResponse> {
  const response = await request.get(`/api/patterns/${patternId}/progress`);
  return (await response.json()) as ProgressResponse;
}

interface View {
  x0: number;
  y0: number;
  cell: number;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Déplace la vue (outil « Déplacer ») d'un delta exact en pixels — le geste
 * de glissé applique `dx = (déplacement en pixels) / cell` à chaque
 * événement `pointermove` (voir `TrackScreen.tsx::onPointerMove`), donc la
 * somme télescope exactement vers le déplacement net quel que soit le
 * nombre d'étapes intermédiaires. Découpé en plusieurs gestes courts pour ne
 * jamais sortir la souris de la fenêtre de test.
 */
async function panByPixels(page: Page, box: Box, totalDx: number, totalDy: number): Promise<void> {
  const maxStep = 250;
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  let remainingX = totalDx;
  let remainingY = totalDy;
  while (Math.abs(remainingX) > 0.5 || Math.abs(remainingY) > 0.5) {
    const stepX = Math.max(-maxStep, Math.min(maxStep, remainingX));
    const stepY = Math.max(-maxStep, Math.min(maxStep, remainingY));
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + stepX, startY + stepY, { steps: 6 });
    await page.mouse.up();
    remainingX -= stepX;
    remainingY -= stepY;
  }
}

/**
 * Pan exact pour amener le point de grille `(gx, gy)` au centre du canvas,
 * en repartant d'une vue connue (`view`) — voir le commentaire de
 * `panByPixels`. Renvoie la nouvelle vue, à réutiliser pour l'appel suivant.
 */
async function centerOn(page: Page, box: Box, view: View, gx: number, gy: number): Promise<View> {
  await page.getByRole("button", { name: "Déplacer" }).click();
  const desiredX0 = gx - box.width / 2 / view.cell;
  const desiredY0 = gy - box.height / 2 / view.cell;
  const movedX = (view.x0 - desiredX0) * view.cell;
  const movedY = (view.y0 - desiredY0) * view.cell;
  await panByPixels(page, box, movedX, movedY);
  return { x0: desiredX0, y0: desiredY0, cell: view.cell };
}

/** Tap au centre du canvas — un unique point d'appui, sans déplacement, pour
 * rester sous `DRAG_THRESHOLD` et être traité comme un cochage, pas un
 * glissé (voir `TrackScreen.tsx`). */
async function tapCenter(page: Page, box: Box): Promise<void> {
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.up();
}

async function openTrackScreen(page: Page, patternName: string): Promise<Locator> {
  await page.goto("/");
  await page.getByText(patternName).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  return canvas;
}

test("le rendu affiche les points spéciaux du motif de démonstration", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  const canvas = await openTrackScreen(page, pattern.name);

  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");

  // Vue initiale connue (`useTracker.ts`, motif 255×180) : x0=30, y0=24,
  // cell=16 — sans avoir touché ni au zoom ni au déplacement. Cell=16 est
  // déjà au-dessus de `SYMBOL_MIN_CELL` (15) : point arrière et nœuds sont
  // donc bien rendus (voir `pattern/render.ts`).
  const initialView: View = { x0: 30, y0: 24, cell: 16 };
  const view = await centerOn(page, box, initialView, CENTER.x, CENTER.y);

  const fabric = await page.evaluate(() =>
    getComputedStyle(document.querySelector("canvas.track-canvas")!)
      .getPropertyValue("--canvas-fabric")
      .trim(),
  );
  const fabricRgb = await page.evaluate((hex) => {
    const clean = hex.replace("#", "");
    return [0, 2, 4].map((i) => Number.parseInt(clean.slice(i, i + 2), 16));
  }, fabric);

  const sample = (gx: number, gy: number): Promise<[number, number, number]> =>
    canvas.evaluate(
      (element, [x, y]) => {
        const el = element as HTMLCanvasElement;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const ctx = el.getContext("2d");
        if (ctx === null) throw new Error("pas de contexte 2d");
        const data = ctx.getImageData(Math.round(x * ratio), Math.round(y * ratio), 1, 1).data;
        return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0] as [number, number, number];
      },
      [gx, gy] as [number, number],
    );

  // Coordonnées **relatives au canvas** (jamais à la page) : `getImageData`
  // adresse toujours le tampon de pixels du canvas lui-même, pas la fenêtre —
  // contrairement aux coordonnées de souris utilisées ailleurs dans ce
  // fichier (`panByPixels`/`tapCenter`), qui doivent inclure `box.x`/`box.y`.
  const toLocalPixel = (gx: number, gy: number): [number, number] => [
    (gx - view.x0) * view.cell,
    (gy - view.y0) * view.cell,
  ];

  const distance = (rgb: [number, number, number]): number =>
    Math.hypot(rgb[0] - (fabricRgb[0] ?? 0), rgb[1] - (fabricRgb[1] ?? 0), rgb[2] - (fabricRgb[2] ?? 0));

  // Point 1/4 (case (109,95), coin haut-gauche du triangle — voir
  // `fillQuarterTriangle`).
  {
    const [px, py] = toLocalPixel(109 + 0.15, 95 + 0.15);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }

  // Point 1/2 (case (117,104), triangle diagonal haut-gauche).
  {
    const [px, py] = toLocalPixel(117 + 0.25, 104 + 0.25);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }

  // Point arrière (segment bas→gauche, son milieu).
  {
    const [px, py] = toLocalPixel((127 + 112) / 2, (105 + 90) / 2);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }

  // Nœud (centre du nœud d'index 1, non coché).
  {
    const [px, py] = toLocalPixel(121.5, 87.5);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }
});

test("cocher un point 1/2, 1/4, arrière et nœud persiste après rechargement", async ({
  page,
  request,
}) => {
  const pattern = await fetchDemoPattern(request);

  // Base connue, quelle que soit l'exécution précédente : les quatre
  // éléments visés démarrent non cochés.
  const QUARTER_INDEX = 95 * 255 + 109; // case (109, 95)
  const HALF_INDEX = 104 * 255 + 117; // case (117, 104)
  const BACKSTITCH_INDEX = 2; // segment bas→gauche
  const KNOT_INDEX = 1; // nœud (121.5, 87.5)

  await setStitched(request, pattern.id, "quarter", QUARTER_INDEX, false);
  await setStitched(request, pattern.id, "half", HALF_INDEX, false);
  await setStitched(request, pattern.id, "backstitch", BACKSTITCH_INDEX, false);
  await setStitched(request, pattern.id, "knot", KNOT_INDEX, false);

  const before = await fetchProgress(request, pattern.id);
  expect(bitSet(before.bitmap_quarter, QUARTER_INDEX)).toBe(false);
  expect(bitSet(before.bitmap_half, HALF_INDEX)).toBe(false);
  expect(bitSet(before.bitmap_backstitch, BACKSTITCH_INDEX)).toBe(false);
  expect(bitSet(before.bitmap_knots, KNOT_INDEX)).toBe(false);

  const canvas = await openTrackScreen(page, pattern.name);
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");

  // Zoom au maximum (boutons, pas la molette : `zoomIn` arrondit à un entier
  // exact, contrairement au pincement/trackpad — nécessaire pour que le
  // calcul de centrage ci-dessous reste exact). Trois clics suffisent pour
  // atteindre MAX_CELL (16 → 23 → 33 → 34) ; le zoom ne modifie jamais
  // `x0`/`y0` (voir `useTracker.ts::zoomIn`).
  const zoomInButton = page.getByRole("button", { name: "Zoomer", exact: true });
  for (let i = 0; i < 3; i++) await zoomInButton.click();
  let view: View = { x0: 30, y0: 24, cell: 34 };

  // Point 1/4.
  view = await centerOn(page, box, view, 109.5, 95.5);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  await page.getByRole("button", { name: "Point 1/4" }).click();
  await tapCenter(page, box);

  // Point 1/2.
  view = await centerOn(page, box, view, 117.5, 104.5);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  await page.getByRole("button", { name: "Point 1/2" }).click();
  await tapCenter(page, box);

  // Point arrière (milieu du segment bas→gauche : (127,105)-(112,90)).
  view = await centerOn(page, box, view, (127 + 112) / 2, (105 + 90) / 2);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  const backstitchButton = page.getByRole("button", { name: "Point arrière" });
  await expect(backstitchButton).toBeEnabled();
  await backstitchButton.click();
  await tapCenter(page, box);

  // Nœud (centre (121.5, 87.5)).
  view = await centerOn(page, box, view, 121.5, 87.5);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  const knotButton = page.getByRole("button", { name: "Nœud" });
  await expect(knotButton).toBeEnabled();
  await knotButton.click();
  await tapCenter(page, box);

  // La synchronisation est asynchrone (file IndexedDB + envoi débounced,
  // voir lot1-persistence.spec.ts) : laisser le temps à `useSyncedTracker`
  // de confirmer avant d'interroger le serveur ou de recharger.
  await expect
    .poll(async () => {
      const progress = await fetchProgress(request, pattern.id);
      return [
        bitSet(progress.bitmap_quarter, QUARTER_INDEX),
        bitSet(progress.bitmap_half, HALF_INDEX),
        bitSet(progress.bitmap_backstitch, BACKSTITCH_INDEX),
        bitSet(progress.bitmap_knots, KNOT_INDEX),
      ];
    }, { timeout: 10_000 })
    .toEqual([true, true, true, true]);

  await page.reload();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  const after = await fetchProgress(request, pattern.id);
  expect(bitSet(after.bitmap_quarter, QUARTER_INDEX)).toBe(true);
  expect(bitSet(after.bitmap_half, HALF_INDEX)).toBe(true);
  expect(bitSet(after.bitmap_backstitch, BACKSTITCH_INDEX)).toBe(true);
  expect(bitSet(after.bitmap_knots, KNOT_INDEX)).toBe(true);
});
