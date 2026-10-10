import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Issue #44: importing an official DMC chart must propose exactly the
 * colours of its legend — not one entry per shade or symbol variant found on
 * the grid, and never a code the legend does not list. Checked on the
 * reporter's own file ("Couronne d'hiver", `fixtures/winter-wreath-dmc`),
 * whose legend (page 4) lists 14 DMC codes — see `fixtures/README.md`.
 */

const FIXTURE_PATH = fileURLToPath(
  new URL("../../fixtures/winter-wreath-dmc/PATASS117_2C_2.pdf", import.meta.url),
);
const LEGEND_CODES = [
  "3345", "3346", "471", "472", "11", "18", "3821", "726", "3853", "3854", "blanc", "351", "814", "e321",
];
const DETECTION_TIMEOUT = 120_000;

test.use({ viewport: { width: 375, height: 812 } });

test("a DMC chart's palette is exactly its legend's colours", async ({ page }) => {
  test.setTimeout(180_000);

  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);
  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const codeFields = page.getByPlaceholder("Code");
  await expect(codeFields.first()).toBeVisible();
  const codes = (await codeFields.evaluateAll((inputs) =>
    inputs.map((input) => (input as HTMLInputElement).value.trim().toLowerCase()),
  )) as string[];

  expect(codes).toHaveLength(LEGEND_CODES.length);
  expect(new Set(codes).size).toBe(codes.length);
  expect([...codes].sort()).toEqual([...LEGEND_CODES].sort());
});
