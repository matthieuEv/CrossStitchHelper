import { fileURLToPath } from "node:url";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Issue #40: on the import wizard's Palette step, the imported file itself is
 * shown next to the generated grid, so it can be checked against the
 * original — side by side on a wide screen, on demand on a phone, zoomable,
 * with page navigation for a multi-page PDF.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";
/** Multi-page type A fixture. */
const MULTI_PAGE_PDF = fileURLToPath(
  new URL(
    "../../fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf",
    import.meta.url,
  ),
);

async function reachPaletteWithImage(page: Page): Promise<void> {
  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "grille-test.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
}

/** The preview image really loaded (not a broken image). */
async function expectLoaded(image: Locator): Promise<void> {
  await expect(image).toBeVisible();
  await expect
    .poll(() => image.evaluate((element) => (element as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
}

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("the original file is shown on demand, and zooms", async ({ page }) => {
    await reachPaletteWithImage(page);

    const source = page.getByRole("img", { name: "Page 1 du fichier importé" });
    await expect(source).toHaveCount(0);
    await page.getByRole("button", { name: "Voir le fichier d'origine" }).click();
    await expectLoaded(source);

    const width = async (): Promise<number> => (await source.boundingBox())?.width ?? 0;
    const before = await width();
    await page.getByRole("button", { name: "Zoomer sur le fichier d'origine" }).click();
    await expect.poll(width).toBeGreaterThan(before * 1.4);

    await page.getByRole("button", { name: "Masquer le fichier d'origine" }).click();
    await expect(source).toHaveCount(0);
  });
});

test.describe("desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the original file sits next to the grid, page by page", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/import");
    await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(MULTI_PAGE_PDF);
    await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Continuer", exact: true }).click();

    const grid = page.locator("canvas.track-canvas");
    await expect(grid).toBeVisible();
    const first = page.getByRole("img", { name: "Page 1 du fichier importé" });
    await expectLoaded(first);

    // Side by side: the file starts to the right of the grid, on the same row.
    const gridBox = await grid.boundingBox();
    const sourceBox = await first.boundingBox();
    if (gridBox === null || sourceBox === null) throw new Error("Missing bounding box");
    expect(sourceBox.x).toBeGreaterThanOrEqual(gridBox.x + gridBox.width);
    expect(Math.abs(sourceBox.y - gridBox.y)).toBeLessThan(40);

    await page
      .getByRole("region", { name: "Fichier d'origine" })
      .getByRole("button", { name: "Page suivante" })
      .click();
    await expectLoaded(page.getByRole("img", { name: "Page 2 du fichier importé" }));
  });
});
