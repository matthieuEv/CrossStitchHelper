import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Checks Lot 7's "done when" criterion (docs/roadmap.md): the
 * `fixtures/river-and-mountains-laserarts/` PDF (type E — closed catalogue of
 * reused bitmap images, third-party publisher LaserArtsDesigns) imports with
 * its correct colours and symbols, without its photorealistic preview page
 * (page 1, ~40,000 image placements) being taken for a grid page — against a
 * real instance, with detection really running as a background task on the
 * server (`backend/app/api/imports.py`, `backend/app/type_e.py`).
 *
 * Slower than the rest of this suite (real structural analysis of an 18-page
 * PDF, tens of thousands of image placements on the cover page alone): that
 * is expected, see `backend/tests/test_type_e.py` for the exhaustive
 * verification of the extraction's correctness — these tests only check the
 * end-to-end user journey.
 */

const RIVER_AND_MOUNTAINS_PATH = fileURLToPath(
  new URL(
    "../../fixtures/river-and-mountains-laserarts/RiverAndMountains-CS.pdf",
    import.meta.url,
  ),
);

// More generous than the Lot 4-5 DMC fixtures (90s): this file is the
// repository's heaviest fixture (18 pages, ~40,000 image placements on its
// cover page alone) and goes through the three detectors in sequence
// (detect_type_a and detect_type_bc must first return `None` on it) —
// measured at ~21s locally for the whole chain, but the "Docker image + e2e"
// CI job runs on a measurably slower runner (see the history: already the
// cause of a similar adjustment in Lot 5).
const DETECTION_TIMEOUT = 180_000;

test("a type E PDF (reused image catalogue) pre-fills the wizard with real colour+symbol icons", async ({
  page,
}) => {
  test.setTimeout(240_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page
    .locator('input[type="file"][accept*="pdf"]')
    .setInputFiles(RIVER_AND_MOUNTAINS_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type E/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  // Dimensions stated plainly by the PDF's legend (page 17): 217×206.
  await expect(columnsInput!).toHaveValue("217");
  await expect(rowsInput!).toHaveValue("206");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Palette step: 20 real DMC colours, each with its real icon (colour +
  // symbol already combined) cut out of the PDF — never an empty swatch or
  // fallback text. `.count()` never retries on its own (unlike
  // `toBeVisible()`): first wait for a badge to be visible so the Palette step
  // can finish populating.
  const paletteSwatchImages = page.locator('button.badge img[src^="data:image/svg+xml;base64,"]');
  await expect(paletteSwatchImages.first()).toBeVisible();
  expect(await paletteSwatchImages.count()).toBe(20);
  expect(await page.getByPlaceholder("Code").count()).toBe(20);

  // Clean file (specification, Lot 7 "done when"): no cell should be
  // flagged uncertain here — the exact count is enough to identify the 20
  // colours unambiguously on this file.
  await expect(page.getByText(/case\(s\) marquée\(s\) d'un repère/)).toHaveCount(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e type E ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Must land on a real tracking screen, whole pattern assembled (mosaic of
  // 15 grid pages stitched back together by axis numbers).
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  const symbolImages = page.locator('img[src^="data:image/svg+xml;base64,"]');
  await expect(symbolImages.first()).toBeVisible();

  expect(pageErrors).toEqual([]);
});
