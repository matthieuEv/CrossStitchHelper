import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Checks Lot 9's "done when" criterion (docs/roadmap.md): type A automatic
 * detection also extracts special stitches (1/2, 1/4, backstitch, knot) —
 * against a real instance, with the real reference file, all the way
 * through the real import journey (not just the unit tests in
 * `backend/tests/test_type_a.py`, which verify the extraction's correctness
 * itself but not the user journey).
 *
 * Ground truth values: the fixture's page 11 "Usage Summary", taken as is
 * (see `backend/tests/test_type_a.py::_expected_usage_by_code` for the
 * independent re-parsing of these same figures at the source).
 */

const FIXTURE_PATH = fileURLToPath(
  new URL(
    "../../fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf",
    import.meta.url,
  ),
);

/** See the equivalent comment in `lot4-automatic-detection.spec.ts`. */
const DETECTION_TIMEOUT = 90_000;

interface PatternSummary {
  id: string;
  name: string;
}

interface PatternPaletteEntry {
  code: string;
  count_half: number;
  count_quarter: number;
  count_french: number;
  backstitch_length_cm: number | null;
}

interface PatternDetail {
  palette: PatternPaletteEntry[];
}

async function fetchPatternByName(
  request: APIRequestContext,
  name: string,
): Promise<PatternDetail> {
  const list = await request.get("/api/patterns");
  const patterns = (await list.json()) as PatternSummary[];
  const found = patterns.find((pattern) => pattern.name === name);
  if (found === undefined) throw new Error(`Pattern "${name}" not found in the database`);
  const detail = await request.get(`/api/patterns/${found.id}`);
  return (await detail.json()) as PatternDetail;
}

test("type A import pre-fills the fabric count and the special stitches end up in the created pattern", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  await expect(page.getByPlaceholder("Code").first()).toBeVisible();
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Summary step: the fabric count (Aida 16, read from the PDF text) is
  // already filled in — never imposed, manual input would always win (see
  // `manualFabricEditRef` in `ImportScreen.tsx`), but here we precisely check
  // that nothing was typed.
  const fabricInput = page.getByLabel("Toile (fils au pouce)");
  await expect(fabricInput).toHaveValue("16");

  const patternName = `e2e points spéciaux ${Date.now()}`;
  await page.getByLabel("Nom du motif").fill(patternName);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  const detail = await fetchPatternByName(request, patternName);
  const palette = Object.fromEntries(detail.palette.map((entry) => [entry.code, entry]));

  // DMC 3031: the 4 quarter stitches declared on page 11 (off-centre glyphs,
  // distinct from the 3031 full stitch).
  expect(palette["3031"]?.count_quarter).toBe(4);

  // DMC 742: the 3 knots, all on the fixture's page 1.
  expect(palette["742"]?.count_french).toBe(3);

  // DMC 310: backstitch length converted to cm from the fabric count just
  // validated (16) — never `null` since the field was filled in at
  // validation.
  expect(palette["310"]?.backstitch_length_cm).not.toBeNull();
  expect(palette["310"]!.backstitch_length_cm!).toBeGreaterThan(100);
});
