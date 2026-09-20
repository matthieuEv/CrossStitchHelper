import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Retour utilisateur direct après usage réel : sur un vrai diagramme papier,
 * les traits de point arrière restent visibles même sur une vue d'ensemble
 * de la grille — l'application les masquait entièrement en dessous du même
 * seuil de zoom que les symboles (`SYMBOL_MIN_CELL`, `pattern/render.ts`),
 * ce qui ne correspond à aucune référence papier. Corrigé en découplant le
 * rendu du point arrière/des nœuds de ce seuil — l'interaction (cocher),
 * elle, reste réservée au zoom rapproché (`state/useTracker.ts`), pas
 * couverte ici.
 *
 * Géométrie et point d'échantillonnage repris tels quels de
 * lot8-special-stitches.spec.ts (issus de
 * `backend/app/seed.py::_build_special_stitches`) — le milieu du segment
 * bas→gauche du losange de point arrière, déjà vérifié empiriquement par ce
 * test-là comme tombant sur une case vide du point entier (sans quoi la
 * comparaison à la couleur de toile n'aurait aucun sens).
 */

const DEMO_PATTERN_ID = "demo-perf-255x180";
// En dessous de `SYMBOL_MIN_CELL` (15, `pattern/render.ts`) : c'est
// exactement le niveau de zoom où le bug se manifestait.
const BELOW_SYMBOL_THRESHOLD = 15;

interface PatternSummary {
  id: string;
  name: string;
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

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Motif de démonstration introuvable en base");
  return demo;
}

/** Repris de lot8-special-stitches.spec.ts — voir ce fichier pour le détail
 * du raisonnement (le glissé applique `dx = pixels / cell` par évènement). */
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

async function centerOn(page: Page, box: Box, view: View, gx: number, gy: number): Promise<View> {
  await page.getByRole("button", { name: "Déplacer" }).click();
  const desiredX0 = gx - box.width / 2 / view.cell;
  const desiredY0 = gy - box.height / 2 / view.cell;
  const movedX = (view.x0 - desiredX0) * view.cell;
  const movedY = (view.y0 - desiredY0) * view.cell;
  await panByPixels(page, box, movedX, movedY);
  return { x0: desiredX0, y0: desiredY0, cell: view.cell };
}

async function zoomBadgeSize(page: Page): Promise<number> {
  const text = await page.locator(".track-badges .badge").first().textContent();
  const match = text?.match(/(\d+)\s*px\/case/);
  if (match?.[1] === undefined) throw new Error(`Badge de zoom introuvable dans : ${text}`);
  return Number(match[1]);
}

test("le point arrière reste visible bien en dessous du seuil d'apparition des symboles", async ({
  page,
  request,
}) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");

  // Vue initiale connue (`useTracker.ts`, motif 255×180) — même valeur que
  // lot8-special-stitches.spec.ts. On centre sur le losange de point arrière
  // (`_CX, _CY` de `seed.py`) pendant qu'on est encore au-dessus du seuil,
  // le glissé de recentrage étant plus simple à raisonner à ce zoom déjà
  // vérifié par l'autre test.
  const initialView: View = { x0: 30, y0: 24, cell: 16 };
  await centerOn(page, box, initialView, 127, 90);

  // Le curseur est maintenant exactement au centre du canvas, et ce point
  // écran correspond exactement à la case (127, 90) du motif. Un dézoom à la
  // molette recentré sur le curseur (voir wheel-zoom.spec.ts) garde ce même
  // point de grille au centre de l'écran quel que soit le nombre de crans,
  // ce qui évite d'avoir à recalculer x0/y0 après coup — seul `cell` change.
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);

  let cell = await zoomBadgeSize(page);
  let guard = 0;
  while (cell >= BELOW_SYMBOL_THRESHOLD && guard < 30) {
    await page.mouse.wheel(0, 200);
    cell = await zoomBadgeSize(page);
    guard += 1;
  }
  expect(cell).toBeLessThan(BELOW_SYMBOL_THRESHOLD);

  // Milieu du segment bas→gauche du losange : (127,105)→(112,90), déjà
  // vérifié par lot8-special-stitches.spec.ts comme tombant sur une case
  // vide du point entier à ce zoom-là — donc, sans le correctif, ce pixel
  // serait resté exactement la couleur de toile (`--canvas-fabric`).
  const targetGrid = { x: (127 + 112) / 2, y: (105 + 90) / 2 };
  const px = box.width / 2 + (targetGrid.x - 127) * cell;
  const py = box.height / 2 + (targetGrid.y - 90) * cell;

  const rgb = await canvas.evaluate(
    (element, [x, y]) => {
      const el = element as HTMLCanvasElement;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const ctx = el.getContext("2d");
      if (ctx === null) throw new Error("pas de contexte 2d");
      const data = ctx.getImageData(Math.round(x * ratio), Math.round(y * ratio), 1, 1).data;
      return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0] as [number, number, number];
    },
    [px, py] as [number, number],
  );

  const fabric = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--canvas-fabric").trim(),
  );
  const fabricRgb = await page.evaluate((hex) => {
    const clean = hex.replace("#", "");
    return [0, 2, 4].map((i) => Number.parseInt(clean.slice(i, i + 2), 16));
  }, fabric);

  const distance = Math.hypot(
    rgb[0] - (fabricRgb[0] ?? 0),
    rgb[1] - (fabricRgb[1] ?? 0),
    rgb[2] - (fabricRgb[2] ?? 0),
  );
  expect(distance).toBeGreaterThan(30);
});
