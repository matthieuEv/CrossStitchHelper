import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Checks Lot 4's "done when" criterion (docs/roadmap.md): the reference
 * type A PDF imports by simply accepting the proposals — against a real
 * instance, with the real reference file (not a synthetic excerpt), with
 * detection really running as a background task on the server (see
 * `backend/app/api/imports.py`).
 *
 * Slower than the rest of this suite (real structural analysis, ~10 s): that
 * is expected, see `backend/tests/test_type_a.py` for the exhaustive
 * verification of the extraction's correctness itself — this test only
 * checks the end-to-end user journey.
 */

/** `backend/app/seed.py` — stable id, never regenerated, palette entered by
 * hand (no `symbol_svg`): the text fallback must apply. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

interface PatternSummary {
  id: string;
  name: string;
}

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

async function remainingCount(page: Page): Promise<number> {
  const text = await page.getByText(/restants$/).first().textContent();
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`"Remaining" counter not found in: ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

const FIXTURE_PATH = fileURLToPath(
  new URL(
    "../../fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf",
    import.meta.url,
  ),
);

// Minimal valid PDF (two pages — the per-page independent cropping test needs
// a second page to navigate —, a little running text, no vector rectangle or
// symbol font), hard-coded — faster and more robust than a real fixture for
// checking the manual fallback: `fixtures/river-and-mountains-laserarts`
// (type E) would do it too, but its 18 pages noticeably slow down both
// connectors' analysis under Docker CI (see the fix commit), to the point of
// making these tests time out *and* leaving the container busy enough to make
// the next type A test in the same suite time out as a knock-on effect. The
// DMC fixtures (`winter-wreath-dmc` and the like) are now recognised as
// type B/C since Lot 5 and no longer suit this role either.
const TINY_UNDETECTABLE_PDF_BASE64 =
  "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjguMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjguMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDIvS2lkc1s0IDAgUiA4IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDMwMCAyMDBdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDEwNS9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNoVSjsKQkEQ6+cUcwNnZvdlniAWD2zshOnESnex0MLG8xsJSchHPrKVuBrhulDMtN6ye47XV921pl4PfWBmD4OTLYOpZYsHtWNPNqz/BSs8g897WPKNxMJ+YtDH8VZnOZVc5AcK1hpwCmVuZHN0cmVhbQplbmRvYmoKCjcgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKOCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDMwMCAyMDBdL1JvdGF0ZSAwL1Jlc291cmNlcyA3IDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbOSAwIFJdPj4KZW5kb2JqCgo5IDAgb2JqCjw8L0xlbmd0aCAxMDYvRmlsdGVyL0ZsYXRlRGVjb2RlPj4Kc3RyZWFtCnjaFYoxCkJBEEP7OcXcwJnZ/ZkviMUHGzthOrHSXSy0sPH8RkIeCYl8ZCtxNcp1Icy03rJ7jtdX3bWmXg99YGYPg9Mtg61liwfZsacb1v+CFZ7B5z0s+UZiYeqZmDGOtzrLqeQiPwdxGkMKZW5kc3RyZWFtCmVuZG9iagoKeHJlZgowIDEwCjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAwMTIwIDAwMDAwIG4gCjAwMDAwMDAxNzggMDAwMDAgbiAKMDAwMDAwMDIxOSAwMDAwMCBuIAowMDAwMDAwMzI2IDAwMDAwIG4gCjAwMDAwMDA0MTUgMDAwMDAgbiAKMDAwMDAwMDU4OSAwMDAwMCBuIAowMDAwMDAwNjMwIDAwMDAwIG4gCjAwMDAwMDA3MzcgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSAxMC9Sb290IDEgMCBSL0lEWzxDMjk5NDZDM0EyNTIzNDUwMzkwOEMzOTY2OUMyOEZDMj48OEY2NjgwMzY5NTc3RDkzNzM2OTM4MkE2OTYxN0FBODg+XT4+CnN0YXJ0eHJlZgo5MTIKJSVFT0YK";

function tinyUndetectablePdf(): { name: string; mimeType: string; buffer: Buffer } {
  return {
    name: "not-a-cross-stitch-chart.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(TINY_UNDETECTABLE_PDF_BASE64, "base64"),
  };
}

/**
 * ~10s locally (see `backend/tests/test_type_a.py`), but noticeably more under
 * Docker on CI runners (shared CPU, fewer cores) — measured in practice: a
 * 30s timeout systematically failed the two tests that wait for the analysis
 * to finish in the "Docker image + e2e" job (never locally). Generous rather
 * than guessing an exact figure.
 */
const DETECTION_TIMEOUT = 90_000;

test("a recognised type A PDF pre-fills the wizard, which only needs validating", async ({
  page,
}) => {
  test.setTimeout(120_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Cropping step: the analysis-in-progress message appears, then the
  // detection banner with the dimensions already pre-filled — without any
  // input.
  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).toHaveValue("255");
  await expect(rowsInput!).toHaveValue("180");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Palette step: already populated by detection, nothing to add — just
  // check that a real palette (at least the legend's 34 DMC colours) is
  // there, not an empty list the user would have to fill by hand as in
  // Lot 2.
  await expect(page.getByPlaceholder("Code").first()).toBeVisible();
  expect(await page.getByPlaceholder("Code").count()).toBeGreaterThanOrEqual(34);
  await expect(page.getByText(/\d+ \/ 45\s?900 cases peintes/)).toBeVisible();

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Summary step: name, then validation — the user only confirmed a
  // proposal, never built the grid themselves.
  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e type A ${Date.now()}`);

  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Must land on a real tracking screen, whole pattern assembled — far more
  // than what manual painting would produce in a quick test.
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  expect(await remainingCount(page)).toBeGreaterThan(30_000);
});

test("typing dimensions by hand during analysis crashes neither the client nor the server", async ({
  page,
}) => {
  // Real bug found in manual testing: the message shown during analysis
  // explicitly invites cropping or entering the dimensions by hand while
  // waiting (`import.detection.running`) — if the user really does so, before
  // the background analysis (~10s on this fixture) has finished, two things
  // crashed: the client (`Uint8Array.set` with a detected grid that had
  // become too long for the newly typed dimensions) and the server (500 on
  // `PATCH /config`, same cause in `apply_fills`). See the fix commits for
  // the details.
  test.setTimeout(90_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Don't wait for detection: type right away, like a hurried user following
  // the prompt of the message shown during analysis rather than waiting the
  // ~10s it really takes.
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("92");
  await rowsInput!.fill("74");

  const configPatch = page.waitForResponse((response) => response.url().includes("/config"));
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  expect((await configPatch).status()).toBe(200);

  // Still usable: the Palette step shows up (empty, since the user took over
  // before detection proposed anything — normal Lot 2 behaviour), not a
  // crashed blank screen.
  await expect(page.getByRole("button", { name: /Ajouter une couleur/ })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("changing already detected dimensions does not crash either", async ({ page }) => {
  // Same bug as the previous test, but reproduced deterministically (without
  // depending on winning a ~10s race): let detection finish and pre-fill
  // 255×180 with a real `detected_cells`, *then* correct the dimensions —
  // exactly the gesture that crashed the client (`Uint8Array.set`, detected
  // grid too long for 92×74) and the server (500 on `PATCH /config`).
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).toHaveValue("255", { timeout: DETECTION_TIMEOUT });
  await expect(rowsInput!).toHaveValue("180");
  expect(pageErrors).toEqual([]); // not crashed yet at this point

  await columnsInput!.fill("92");
  expect(pageErrors).toEqual([]); // still not, even with rows=180 still inconsistent
  await rowsInput!.fill("74");
  expect(pageErrors).toEqual([]);

  const configPatch = page.waitForResponse((response) => response.url().includes("/config"));
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  expect((await configPatch).status()).toBe(200);

  await expect(page.getByRole("button", { name: /Ajouter une couleur/ })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("manual cropping stays blocked during automatic analysis", async ({ page }) => {
  // Explicit user request: the loading overlay must stay blurred and
  // blocking during analysis — the manual fallback only makes sense if the
  // automatic one really failed, not as a competing option while waiting
  // (unlike a previous choice, reverted here: see the history of
  // `crop-stage-loading` in index.css).
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Don't wait for detection: the test targets precisely the window during
  // which the loading overlay is shown.
  await expect(page.locator(".crop-stage-loading")).toBeVisible();
  await expect(page.locator(".crop-handle").first()).not.toBeVisible();
});

test("manual cropping appears if automatic detection finds nothing", async ({
  page,
}) => {
  // Explicitly requested fallback: a file matching no recognised type
  // (neither `detect_type_a` nor `detect_type_bc` since Lot 5 — see
  // fixtures/README.md) must fall back to Lot 2's manual cropping once the
  // analysis is finished — never while it is still running (previous test).
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(tinyUndetectablePdf());

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.locator(".crop-stage-loading")).not.toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // Never a detection banner: neither connector claimed the file.
  await expect(page.getByText(/Détection automatique/)).not.toBeVisible();

  const topHandle = page.locator(".crop-handle").first();
  await expect(topHandle).toBeVisible();
  const before = await topHandle.boundingBox();
  if (before === null) throw new Error("The crop handle has no bounding box");

  await page.mouse.move(before.x + before.width / 2, before.y + before.height / 2);
  await page.mouse.down();
  await page.mouse.move(before.x + before.width / 2, before.y + before.height / 2 + 60, {
    steps: 5,
  });
  await page.mouse.up();

  const after = await topHandle.boundingBox();
  if (after === null) throw new Error("The crop handle has no bounding box");
  expect(after.y).toBeGreaterThan(before.y + 30);
});

test("manual cropping is independent from one page to another", async ({ page }) => {
  // Explicit user request: a single crop imposed on every page makes no sense
  // (one page may be a legend, another the grid) — each page therefore keeps
  // its own rectangle, see `backend/app/schemas.py::ImportConfig.crop_by_page`.
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(tinyUndetectablePdf());

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.locator(".crop-stage-loading")).not.toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

  const handle = page.locator(".crop-handle").first();
  await expect(handle).toBeVisible();
  const pageOneDefault = await handle.boundingBox();
  if (pageOneDefault === null) throw new Error("The crop handle has no bounding box");

  // Crop page 1 (drag the top handle downwards).
  await page.mouse.move(pageOneDefault.x + pageOneDefault.width / 2, pageOneDefault.y + pageOneDefault.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    pageOneDefault.x + pageOneDefault.width / 2,
    pageOneDefault.y + pageOneDefault.height / 2 + 60,
    { steps: 5 },
  );
  await page.mouse.up();
  const pageOneCropped = await handle.boundingBox();
  if (pageOneCropped === null) throw new Error("The crop handle has no bounding box");
  expect(pageOneCropped.y).toBeGreaterThan(pageOneDefault.y + 30);

  // Page 2 starts from the default crop, not page 1's.
  await page.getByRole("button", { name: "Page suivante" }).click();
  const pageTwoDefault = await page.locator(".crop-handle").first().boundingBox();
  if (pageTwoDefault === null) throw new Error("The crop handle has no bounding box");
  expect(pageTwoDefault.y).toBeLessThan(pageOneCropped.y - 20);

  // Going back to page 1 finds the crop left there.
  await page.getByRole("button", { name: "Page précédente" }).click();
  const pageOneAgain = await page.locator(".crop-handle").first().boundingBox();
  if (pageOneAgain === null) throw new Error("The crop handle has no bounding box");
  expect(Math.abs(pageOneAgain.y - pageOneCropped.y)).toBeLessThan(5);
});

test("the displayed symbols are the PDF's real glyphs, not synthetic letters", async ({
  page,
}) => {
  // Real bug reported by the user: the extraction engine generated a
  // printable internal key (A, B, ..., AB, ...) for lack of being able to
  // reuse the raw glyph of the PDF's private font (`app.type_a.symbol_key`) —
  // but that key was never meant as the symbol to display, never a list of
  // symbols known in advance (symbols vary from one PDF to another):
  // `app.imports_engine.render_symbol_svg` now cuts the real symbol out of
  // the rendered page, see `tests/test_type_a.py` on the backend for the
  // exhaustive verification of its correctness.
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await expect(page.getByPlaceholder("Code").first()).toBeVisible();

  // The Palette step must also show the real symbols, not just the final
  // Tracking screen — real bug found in manual testing: a palette built
  // locally in `ImportScreen.tsx` for the brush (`ImportGridPainter`,
  // distinct from `lib/mappers.ts`, which was already correct) lost
  // `symbol_svg` on its way to `useImportPainter`. Checked here on the colour
  // selection swatches (real `<img>` tags, not the brush canvas itself: its
  // image decodes there asynchronously, too fast and too unreliably for a
  // race in a test).
  const paletteSwatchImages = page.locator('button.badge img[src^="data:image/svg+xml;base64,"]');
  await expect(paletteSwatchImages.first()).toBeVisible();
  expect(await paletteSwatchImages.count()).toBeGreaterThanOrEqual(34);

  // Marker next to the editable key (`symbol_key`) of the bottom legend — a
  // second distinct site that also lost `symbol_svg` before being fixed,
  // found through the same real bug as the swatches above.
  const legendRowImages = page.locator(
    'div:has(> input[type="color"]) img[src^="data:image/svg+xml;base64,"]',
  );
  await expect(legendRowImages.first()).toBeVisible();
  expect(await legendRowImages.count()).toBeGreaterThanOrEqual(34);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e symboles réels ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  // The legend (`ColorList.tsx`) shows the real symbol as an image, not the
  // synthetic letter as text — at least the 34 DMC colours of the PDF's
  // legend.
  const symbolImages = page.locator('img[src^="data:image/svg+xml;base64,"]');
  await expect(symbolImages.first()).toBeVisible();
  expect(await symbolImages.count()).toBeGreaterThanOrEqual(34);

  expect(pageErrors).toEqual([]);
});

test("a palette entered by hand keeps its text fallback, with no real symbol to show", async ({
  page,
  request,
}) => {
  // Counterpart of the previous test: the demo pattern (Lot 1, not a PDF
  // import) never had a source PDF to cut from — the legend must keep
  // showing the `symbol_key` text, never break trying to show a missing
  // image.
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  await expect(page.getByText("DMC 310")).toBeVisible();
  expect(await page.locator('img[src^="data:image/svg+xml;base64,"]').count()).toBe(0);
});
