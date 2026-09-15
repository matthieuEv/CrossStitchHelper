import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 1 (docs/roadmap.md) : on peut
 * cocher des cases et retrouver sa progression après rechargement — contre
 * un vrai backend, pas des mocks. Suppose une instance déjà démarrée avec au
 * moins un motif en base (voir e2e/README.md pour la procédure locale, et
 * .github/workflows/ci.yml pour celle de la CI).
 */

interface PatternSummary {
  name: string;
  cell_count: number;
}

/**
 * Le motif de démonstration seedé (`backend/scripts/seed_demo_pattern.py`,
 * 255×180 = 45 900 cases) plutôt que `patterns[0]` : d'autres specs (Lot 2)
 * créent leurs propres motifs, minuscules, dans la même base — prendre le
 * premier motif venu rendrait ce test dépendant de l'ordre d'exécution.
 */
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
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`Compteur "restants" introuvable dans : ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

test("la bibliothèque affiche un motif chargé depuis le serveur", async ({ page, request }) => {
  const response = await request.get("/api/patterns");
  expect(response.ok()).toBeTruthy();

  const demo = await fetchDemoPattern(request);
  await page.goto("/");
  await expect(page.getByText(demo.name)).toBeVisible();
});

test("cocher une zone de cases persiste après rechargement", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);

  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de suivi n'a pas de boîte englobante");

  // Une zone assez grande pour contenir à coup sûr des cases brodables, dans
  // la partie dense du motif de démonstration (centre du canvas).
  const from = { x: box.x + box.width * 0.3, y: box.y + box.height * 0.3 };
  const to = { x: box.x + box.width * 0.7, y: box.y + box.height * 0.7 };

  await page.getByRole("button", { name: "Sélectionner une zone" }).click();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();

  // Baseline connue : on vide d'abord la zone, pour que le remplissage
  // suivant produise un changement garanti, peu importe l'état laissé par
  // une exécution précédente du test.
  await page.getByRole("button", { name: "Décocher la zone", exact: true }).click();
  const emptied = await remainingCount(page);

  await page.getByRole("button", { name: "Sélectionner une zone" }).click();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Cocher la zone", exact: true }).click();
  const filled = await remainingCount(page);

  expect(filled).toBeLessThan(emptied);

  // La synchronisation est asynchrone (file IndexedDB + envoi débounced) :
  // laisser le temps à `useSyncedTracker` de confirmer avant de recharger,
  // sans quoi le rechargement pourrait arriver avant l'écriture serveur.
  await page.waitForTimeout(2000);

  await page.reload();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  await expect.poll(() => remainingCount(page)).toBe(filled);
});
