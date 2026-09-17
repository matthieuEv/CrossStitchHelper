import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Zoomer/dézoomer à la molette ou au trackpad (défilement vertical, deltaY),
 * et se déplacer horizontalement par glissé du trackpad (défilement
 * horizontal, deltaX) — plutôt que seulement par les boutons +/-, le
 * pincement à deux doigts ou le glissé à la souris, demandes explicites de
 * l'utilisateur, pas un critère du roadmap. Vérifié sur les deux canvas
 * concernés : le Suivi (`TrackScreen`) et le pinceau de l'assistant d'import
 * (`ImportGridPainter`), qui partagent le même geste (`state/useTracker.ts`
 * et `state/useImportPainter.ts`, toutes deux via `zoomTo`/`setOffset`).
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** `backend/app/seed.py` — identifiant stable, jamais régénéré. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Motif de démonstration introuvable en base");
  return demo;
}

async function zoomBadgeSize(page: Page): Promise<number> {
  const text = await page.locator(".track-badges .badge").first().textContent();
  const match = text?.match(/(\d+)\s*px\/case/);
  if (match?.[1] === undefined) throw new Error(`Badge de zoom introuvable dans : ${text}`);
  return Number(match[1]);
}

test("la molette/le trackpad zoome le Suivi sous le curseur", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  const initial = await zoomBadgeSize(page);

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(0, -600); // défilement vers le haut : zoom avant
  await expect.poll(() => zoomBadgeSize(page)).toBeGreaterThan(initial);
  const zoomedIn = await zoomBadgeSize(page);

  await page.mouse.wheel(0, 600); // défilement vers le bas : zoom arrière
  await expect.poll(() => zoomBadgeSize(page)).toBeLessThan(zoomedIn);

  // La page elle-même ne doit jamais défiler derrière le canvas — sans
  // `preventDefault()` sur l'écouteur natif, elle le ferait.
  const scrollY = await page.evaluate(() => window.scrollY);
  expect(scrollY).toBe(0);
});

test("le glissé horizontal du trackpad déplace la vue sans zoomer", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  const column = async (): Promise<number> => {
    const text = await page.getByText(/Colonne \d+/).textContent();
    const match = text?.match(/Colonne (\d+)/);
    if (match?.[1] === undefined) throw new Error(`Position introuvable dans : ${text}`);
    return Number(match[1]);
  };

  const initialZoom = await zoomBadgeSize(page);
  const initialColumn = await column();

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(600, 0); // glissé horizontal, pas vertical
  await expect.poll(column).toBeGreaterThan(initialColumn);

  // Le zoom, lui, ne doit pas avoir bougé — seul deltaY zoome.
  expect(await zoomBadgeSize(page)).toBe(initialZoom);
});

test("la molette/le trackpad zoome aussi le pinceau de l'assistant d'import", async ({ page }) => {
  // PDF/photo importe pas ici : seul le geste de zoom sur le canvas de
  // peinture est en jeu, pas le contenu — une image minimale suffit, comme
  // lot2-manual-import.spec.ts.
  const TINY_PNG_BASE64 =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page
    .locator('input[type="file"][accept*="pdf"]')
    .setInputFiles({
      name: "grille-test.png",
      mimeType: "image/png",
      buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
    });

  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("10");
  await rowsInput!.fill("8");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de peinture n'a pas de boîte englobante");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  // Pas d'indicateur de zoom visible ici (contrairement au badge du Suivi) :
  // une case plus grande/petite change forcément le quadrillage rendu, donc
  // une simple capture du canvas suffit à prouver que le geste a un effet,
  // sans avoir à interpréter le contenu des pixels.
  const snapshot = (): Promise<string> => canvas.evaluate((element) => (element as HTMLCanvasElement).toDataURL());

  const before = await snapshot();
  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(0, -600);
  await expect.poll(snapshot).not.toBe(before);
});
