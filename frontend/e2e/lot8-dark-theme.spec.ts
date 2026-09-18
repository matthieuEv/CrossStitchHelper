import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du sous-chantier "Thème sombre" du
 * Lot 8 (docs/roadmap.md) : contre un vrai backend, la bascule Clair/Sombre
 * des Réglages s'applique réellement — attribut `data-theme`, couleur de
 * barre système (`<meta name="theme-color">`), variables CSS lues par le
 * rendu canvas (`--canvas-*`, `frontend/src/pattern/render.ts::readGridTheme`)
 * — et persiste après rechargement sans éclair de mauvais thème (script
 * bloquant de `index.html`).
 *
 * Chaque test remet le thème sur Clair avant de terminer : le thème est un
 * réglage local au navigateur (`localStorage`), pas une donnée serveur —
 * rien à restaurer côté API — mais un autre test de ce fichier ou d'un
 * fichier lancé après pourrait sinon hériter d'un état inattendu.
 */

const DEMO_PATTERN_ID = "demo-perf-255x180";

async function fetchDemoPatternName(request: APIRequestContext): Promise<string> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as Array<{ id: string; name: string }>;
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Motif de démonstration introuvable en base");
  return demo.name;
}

test("basculer sur Sombre change le thème et la couleur de barre système, et persiste après rechargement", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await page.getByRole("button", { name: "Sombre", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  const metaColor = await page.locator('meta[name="theme-color"]').getAttribute("content");
  expect(metaColor).toBe("#1f1d19");

  // Rechargement : le script bloquant de `index.html` doit appliquer le
  // thème mémorisé (`localStorage`) avant le premier rendu — vérifié ici en
  // lisant l'attribut immédiatement après navigation, pas après une
  // interaction qui laisserait le temps à React de le corriger après coup.
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const metaColorAfterReload = await page
    .locator('meta[name="theme-color"]')
    .getAttribute("content");
  expect(metaColorAfterReload).toBe("#1f1d19");

  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await page.getByRole("button", { name: "Clair", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("le rendu canvas suit le thème (variables --canvas-*)", async ({ page, request }) => {
  const patternName = await fetchDemoPatternName(request);

  await page.goto("/");
  await page.getByText(patternName).click();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  const readCanvasVars = (): Promise<[string, string, string]> =>
    page.evaluate(() => {
      const styles = getComputedStyle(document.documentElement);
      return [
        styles.getPropertyValue("--canvas-fabric").trim(),
        styles.getPropertyValue("--canvas-ground").trim(),
        styles.getPropertyValue("--canvas-ink").trim(),
      ];
    });

  const light = await readCanvasVars();

  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await page.getByRole("button", { name: "Sombre", exact: true }).click();
  const dark = await readCanvasVars();

  expect(dark).not.toEqual(light);

  await page.getByRole("button", { name: "Clair", exact: true }).click();
});
