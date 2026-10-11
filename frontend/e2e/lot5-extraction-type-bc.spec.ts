import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Checks Lot 5's "done when" criterion (docs/roadmap.md): the DMC vector
 * fixtures (types B/C) import with their correct colours, the right page
 * strategy detected automatically, and explicit flagging of uncertain cells
 * — against a real instance, with the real reference files, with detection
 * really running as a background task on the server (see
 * `backend/app/api/imports.py`, `backend/app/type_bc.py`).
 *
 * Slower than the rest of this suite (real structural analysis, a few
 * seconds to about ten seconds depending on the fixture): that is expected,
 * see `backend/tests/test_type_bc.py` for the exhaustive verification of the
 * extraction's correctness itself — these tests only check the end-to-end
 * user journey.
 */

/** Type C, two-page overlay genuinely needed (clean colour page + separate
 * symbol page) — see `fixtures/README.md`. */
const BOTANICAL_CITRUS_PATH = fileURLToPath(
  new URL(
    "../../fixtures/botanical-citrus-dmc/agrumes_-_planche_botanique.pdf",
    import.meta.url,
  ),
);

/** Lot 5's trap case (specification §4.3): same DMC visual template, but the
 * colour page itself already carries its symbols — the connector must notice
 * this and never blindly overlay the redundant second page. Issue #44: once
 * the per-cell outline frames of its colour page are no longer taken for
 * fills, it comes out as a reliable type C read from that single page, with
 * exactly its 12 legend codes, and real uncertainty (symbols crossed by
 * backstitch lines, one colour off its legend swatch) flagged — see
 * `backend/tests/test_type_bc.py`. */
const SUMMER_FLIGHT_PATH = fileURLToPath(
  new URL("../../fixtures/summer-flight-dmc/vol_de_te.pdf", import.meta.url),
);

const DETECTION_TIMEOUT = 90_000;

test("a type C PDF with an overlay pre-fills the wizard with real symbols", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(BOTANICAL_CITRUS_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // Issue #44: every grid colour of this file is exactly its legend swatch
  // and carries a single symbol — no uncertain cell any more (flagging is
  // checked on `summer-flight-dmc` below).

  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).not.toHaveValue("");
  await expect(rowsInput!).not.toHaveValue("");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Palette step: at least one entry must carry a real symbol cut out of the
  // PDF (overlaid symbol page), not just a colour — same selectors as Lot 4
  // for the swatches and the editable legend.
  const paletteSwatchImages = page.locator('button.badge img[src^="data:image/svg+xml;base64,"]');
  await expect(paletteSwatchImages.first()).toBeVisible();

  const legendRowImages = page.locator(
    'div:has(> input[type="color"]) img[src^="data:image/svg+xml;base64,"]',
  );
  await expect(legendRowImages.first()).toBeVisible();

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e type C ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Must land on a real tracking screen, whole pattern assembled.
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  const symbolImages = page.locator('img[src^="data:image/svg+xml;base64,"]');
  await expect(symbolImages.first()).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test("the summer-flight-dmc trap case reads its symbols from its own colour page and flags uncertain cells", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(SUMMER_FLIGHT_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // Explicit flagging of uncertain cells (roadmap Lot 5, "done when"): never
  // a wrong cell left without indication in the detection banner.
  await expect(page.getByText(/case\(s\) signalée\(s\) comme incertaine\(s\)/)).toBeVisible();

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // One palette entry per legend code (issue #44): 12, never one per symbol
  // variant — and real symbols cut out of the colour page itself.
  await expect(page.getByPlaceholder("Code").first()).toBeVisible();
  expect(await page.getByPlaceholder("Code").count()).toBe(12);
  await expect(
    page.locator('button.badge img[src^="data:image/svg+xml;base64,"]').first(),
  ).toBeVisible();

  // Visual marker of uncertain cells on the brush itself (Lot 5,
  // `pattern/render.ts`): the hint text must appear under the canvas, with a
  // non-zero count — consistent with the banner above.
  await expect(page.getByText(/case\(s\) marquée\(s\) d'un repère/)).toBeVisible();

  expect(pageErrors).toEqual([]);
});
