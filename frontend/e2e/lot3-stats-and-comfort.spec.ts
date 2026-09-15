import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Vérifie les critères "terminé quand" du Lot 3 (docs/roadmap.md) restés à
 * couvrir après le Lot 1 (filtrage couleur et surlignage ligne/colonne y
 * étaient déjà réels) : un historique de statistiques dérivé de vraies
 * données de progression, le masquage des cases déjà brodées, et une
 * annulation qui revient sur plusieurs gestes d'affilée — contre un vrai
 * backend, pas des mocks.
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** Même repli que lot1-persistence.spec.ts : d'autres specs créent leurs
 * propres motifs dans la même base, le plus grand est toujours le motif de
 * démonstration seedé. */
async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const sorted = [...patterns].sort((a, b) => b.cell_count - a.cell_count);
  const demo = sorted[0];
  if (demo === undefined) throw new Error("Aucun motif en base");
  return demo;
}

async function remainingCount(page: Page): Promise<number> {
  const text = await page.getByText(/restants$/).first().textContent();
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`Compteur "restants" introuvable dans : ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

async function fillZone(
  page: Page,
  canvas: ReturnType<Page["locator"]>,
  fromFraction: { x: number; y: number },
  toFraction: { x: number; y: number },
  action: "Cocher la zone" | "Décocher la zone",
): Promise<void> {
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");
  const from = { x: box.x + box.width * fromFraction.x, y: box.y + box.height * fromFraction.y };
  const to = { x: box.x + box.width * toFraction.x, y: box.y + box.height * toFraction.y };

  await page.getByRole("button", { name: "Sélectionner une zone" }).click();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();
  await page.getByRole("button", { name: action, exact: true }).click();
}

test("cocher des cases apparaît dans l'historique d'activité réel des statistiques", async ({
  page,
  request,
}) => {
  const pattern = await fetchDemoPattern(request);

  await page.goto("/");
  await page.getByText(pattern.name).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // Baseline connue, comme lot1-persistence.spec.ts : vider puis remplir,
  // pour un changement garanti quel que soit l'état laissé par une
  // exécution précédente.
  await fillZone(page, canvas, { x: 0.3, y: 0.3 }, { x: 0.7, y: 0.7 }, "Décocher la zone");
  await fillZone(page, canvas, { x: 0.3, y: 0.3 }, { x: 0.7, y: 0.7 }, "Cocher la zone");

  // La synchronisation est asynchrone (voir lot1-persistence.spec.ts) :
  // laisser le temps au serveur d'écrire le `progress_events` avant de
  // l'interroger.
  await page.waitForTimeout(1500);

  const activity = await request
    .get(`/api/patterns/${pattern.id}/activity`)
    .then((response) => response.json());
  expect(activity.sessions.length).toBeGreaterThan(0);
  expect(activity.sessions[0].stitches).toBeGreaterThan(0);
  expect(activity.sessions[0].hours_ago).toBeLessThan(0.1);

  await page.getByRole("button", { name: "Statistiques" }).click();
  await expect(page.getByRole("heading", { name: "Statistiques" })).toBeVisible();
  // Une vraie séance récente, jamais un texte figé du jeu de données factice
  // (voir usePatternActivity.ts : ce motif n'est pas un motif de démo).
  await expect(page.getByText(/il y a (\d+ )?(minute|seconde)/)).toBeVisible();
});

test("masquer les cases déjà brodées les vide visuellement", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // Dézoome jusqu'à la borne (MIN_CELL) puis déplace la vue jusqu'à sa borne
  // opposée (-6 cases, voir useTracker.ts `setOffset`) : quel que soit le
  // nombre exact de clics/la distance du glissé, on atterrit systématiquement
  // au même endroit — l'angle du motif, dont la bordure (cases 310, noir)
  // est intégralement brodée dès le seed (voir `backend/app/seed.py`).
  const zoomOut = page.getByRole("button", { name: "Dézoomer" });
  for (let i = 0; i < 10; i++) await zoomOut.click();

  await page.getByRole("button", { name: "Déplacer" }).click();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  await page.mouse.move(center.x + 1000, center.y + 1000, { steps: 8 });
  await page.mouse.up();

  // Case (0,0) du motif : bordure noire, 100 % brodée depuis le seed. Avec
  // MIN_CELL = 4px et l'origine de vue calée à -6, elle occupe le pixel
  // (24-28, 24-28) du canvas — sans quadrillage ni symbole à cette taille
  // (sous GRIDLINE_MIN_CELL/SYMBOL_MIN_CELL), un aplat de couleur pur.
  const sample = (): Promise<[number, number, number]> =>
    canvas.evaluate((element) => {
      const ctx = (element as HTMLCanvasElement).getContext("2d");
      if (ctx === null) throw new Error("pas de contexte 2d");
      const data = ctx.getImageData(26, 26, 1, 1).data;
      return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0];
    });

  const stitchedColor = await sample();
  // Case brodée : délavée (mélange noir/fond), donc claire — jamais du noir pur.
  expect(stitchedColor[0]).toBeGreaterThan(80);

  const hideButton = page.getByRole("button", { name: "Masquer les cases faites" });
  await hideButton.click();
  const hiddenColor = await sample();
  // Masquée : couleur de la toile nue, sensiblement différente du délavé.
  expect(Math.abs(hiddenColor[0] - stitchedColor[0])).toBeGreaterThan(20);

  await page.getByRole("button", { name: "Réafficher les cases faites" }).click();
  const shownAgainColor = await sample();
  expect(shownAgainColor).toEqual(stitchedColor);
});

test("l'annulation revient sur plusieurs zones cochées d'affilée", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // Deux zones adjacentes, disjointes, toutes deux vidées d'abord pour une
  // base connue (même motif que les autres specs).
  await fillZone(page, canvas, { x: 0.25, y: 0.3 }, { x: 0.45, y: 0.7 }, "Décocher la zone");
  await fillZone(page, canvas, { x: 0.5, y: 0.3 }, { x: 0.7, y: 0.7 }, "Décocher la zone");
  const baseline = await remainingCount(page);

  await fillZone(page, canvas, { x: 0.25, y: 0.3 }, { x: 0.45, y: 0.7 }, "Cocher la zone");
  const afterFirstFill = await remainingCount(page);
  expect(afterFirstFill).toBeLessThan(baseline);

  await fillZone(page, canvas, { x: 0.5, y: 0.3 }, { x: 0.7, y: 0.7 }, "Cocher la zone");
  const afterSecondFill = await remainingCount(page);
  expect(afterSecondFill).toBeLessThan(afterFirstFill);

  const undo = page.getByRole("button", { name: "Annuler" });
  await undo.click();
  await expect.poll(() => remainingCount(page)).toBe(afterFirstFill);

  await undo.click();
  await expect.poll(() => remainingCount(page)).toBe(baseline);
});
