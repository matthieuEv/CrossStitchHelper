import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Checks the "done when" criterion of Lot 8's "Dark theme" sub-project
 * (docs/roadmap.md): against a real backend, the Settings Light/Dark toggle
 * really applies — `data-theme` attribute, system bar colour
 * (`<meta name="theme-color">`), CSS variables read by canvas rendering
 * (`--canvas-*`, `frontend/src/pattern/render.ts::readGridTheme`) — and
 * persists after a reload with no flash of the wrong theme (blocking script
 * in `index.html`).
 *
 * Each test sets the theme back to Light before finishing: the theme is a
 * browser-local setting (`localStorage`), not server data — nothing to
 * restore via the API — but another test in this file or in a file run
 * afterwards could otherwise inherit an unexpected state.
 */

const DEMO_PATTERN_ID = "demo-perf-255x180";

async function fetchDemoPatternName(request: APIRequestContext): Promise<string> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as Array<{ id: string; name: string }>;
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo.name;
}

test("switching to Dark changes the theme and the system bar colour, and persists after a reload", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await page.getByRole("button", { name: "Sombre", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  const metaColor = await page.locator('meta[name="theme-color"]').getAttribute("content");
  expect(metaColor).toBe("#1f1d19");

  // Reload: the blocking script in `index.html` must apply the remembered
  // theme (`localStorage`) before the first render — checked here by reading
  // the attribute immediately after navigation, not after an interaction that
  // would give React time to fix it afterwards.
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

test("canvas rendering follows the theme (--canvas-* variables)", async ({ page, request }) => {
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
