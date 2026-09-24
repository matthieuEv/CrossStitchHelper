import { expect, test } from "@playwright/test";

/**
 * Checks Lot 2's "done when" criterion (docs/roadmap.md): any image can be
 * turned into a trackable pattern, entirely by hand — upload, cropping,
 * dimensions, palette, area painting, saving. Against a real instance, like
 * lot1-persistence.spec.ts.
 *
 * A minimal PNG image is enough (no need for a real PDF): Lot 2 does no
 * analysis of the file's content, only of its raster rendering.
 */

// Shortest possible valid 1x1 PNG, hard-coded: generating a minimal PDF in a
// test would be more code than the payload it replaces, whereas a PNG fits
// in a short base64 string.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test("importing an image by hand creates a trackable pattern", async ({ page }) => {
  await page.goto("/");
  // The navigation bar's "Importer" (Import) button is always present, unlike
  // the library's "+ Importer un motif" button, reserved for the narrow
  // layout (frontend/src/screens/LibraryScreen.tsx).
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page
    .locator('input[type="file"][accept*="pdf"]')
    .setInputFiles({
      name: "grille-test.png",
      mimeType: "image/png",
      buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
    });

  // Cropping step: the real raster preview must load, then the dimensions.
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Palette step: one colour, then painting an area.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");

  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + 80, box.y + 60, { steps: 4 });
  await page.mouse.up();

  await expect(page.getByText(/\d+ \/ 30 cases peintes/)).toBeVisible();
  const filledText = await page.getByText(/\d+ \/ 30 cases peintes/).textContent();
  const filled = Number(filledText?.match(/(\d+) \/ 30/)?.[1]);
  expect(filled).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Summary step: name, then validation.
  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e import ${Date.now()}`);
  await expect(page.getByText(`${filled}`, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Must land on the tracking screen of the freshly created pattern, with
  // exactly the painted cells as remaining cells (nothing checked).
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  await expect(page.getByText(`${filled} restants`)).toBeVisible();
});
