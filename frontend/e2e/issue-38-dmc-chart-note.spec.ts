import { expect, test } from "@playwright/test";

/**
 * Issue #38: DMC is the only thread chart, so the Palette step has no chart
 * selector — it says which chart the codes belong to instead, read-only.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test.use({ viewport: { width: 375, height: 812 } });

test("the Palette step names DMC as the thread chart", async ({ page }) => {
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

  await expect(page.getByText("Nuancier : DMC", { exact: true })).toBeVisible();
  // Still there once colours exist, next to their codes.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  await expect(page.getByText("Nuancier : DMC", { exact: true })).toBeVisible();
  // Informative only: no chart picker.
  await expect(page.getByRole("combobox")).toHaveCount(0);
});

test("Settings no longer offers other thread brands", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await expect(page.getByRole("button", { name: "Français" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Anchor" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Madeira" })).toHaveCount(0);
});
