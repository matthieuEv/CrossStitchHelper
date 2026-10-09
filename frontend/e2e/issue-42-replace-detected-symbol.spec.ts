import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Issue #42: on the Palette step, a colour whose symbol was cut out of the
 * PDF (an image) can have it replaced by a symbol of one's own choosing — as
 * colours added by hand always could — and the PDF symbol can be restored
 * while the wizard is open. The choice ends up in the created pattern.
 */

/** Type A fixture (embedded symbol font): every colour gets a PDF symbol. */
const FIXTURE_PATH = fileURLToPath(
  new URL(
    "../../fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf",
    import.meta.url,
  ),
);
/** Same budget as `lot4-automatic-detection.spec.ts`. */
const DETECTION_TIMEOUT = 60_000;

const SVG_IMG = 'img[src^="data:image/svg+xml;base64,"]';

interface ApiPaletteEntry {
  index_in_grid: number;
  symbol_key: string;
  symbol_svg: string | null;
}

test.use({ viewport: { width: 375, height: 812 } });

test("a PDF symbol can be replaced by a typed one, or restored", async ({ page, request }) => {
  test.setTimeout(120_000);

  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);
  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const replaceButtons = page.getByRole("button", {
    name: "Remplacer le symbole du PDF par un symbole au choix",
  });
  await expect(replaceButtons.first()).toBeVisible();
  const pdfSymbolCount = await replaceButtons.count();
  expect(pdfSymbolCount).toBeGreaterThanOrEqual(34);

  // Replace, then restore: the first colour is back to its PDF symbol.
  await replaceButtons.first().click();
  await expect(replaceButtons).toHaveCount(pdfSymbolCount - 1);
  await page.getByRole("button", { name: "Reprendre le symbole du PDF" }).click();
  await expect(replaceButtons).toHaveCount(pdfSymbolCount);

  // Replace the second colour's symbol and type one of our own: the field
  // takes the focus right away.
  await replaceButtons.nth(1).click();
  const symbolField = page.getByRole("textbox", { name: "Sym." });
  await expect(symbolField).toHaveCount(1);
  await expect(symbolField).toBeFocused();
  await symbolField.fill("Q");
  await symbolField.blur();
  // The colour selection chips follow: one PDF symbol image fewer.
  await expect(page.locator(`button.badge ${SVG_IMG}`)).toHaveCount(pdfSymbolCount - 1);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByLabel("Nom du motif").fill(`e2e issue 42 ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  // The created pattern keeps the typed symbol for that colour only.
  const patternId = decodeURIComponent(new URL(page.url()).pathname.split("/").pop() ?? "");
  const detail = (await (await request.get(`/api/patterns/${patternId}`)).json()) as {
    palette: ApiPaletteEntry[];
  };
  const second = detail.palette.find((entry) => entry.index_in_grid === 2);
  expect(second?.symbol_svg ?? null).toBeNull();
  expect(second?.symbol_key).toBe("Q");
  const withPdfSymbol = detail.palette.filter((entry) => entry.symbol_svg !== null);
  expect(withPdfSymbol).toHaveLength(pdfSymbolCount - 1);
  expect(detail.palette.find((entry) => entry.index_in_grid === 1)?.symbol_svg).not.toBeNull();
});
