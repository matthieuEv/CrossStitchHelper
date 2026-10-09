import { expect, test } from "@playwright/test";

/**
 * Regression test for issue #43: in Import > Palette, the colour chips above
 * the grid showed the symbol only when it had been cut out of the PDF — a
 * colour added by hand (text symbol only) showed no symbol at all, although
 * the grid painter draws that symbol in its cells.
 */

// Same minimal 1x1 PNG as lot2-manual-import.spec.ts: the manual path needs
// no real PDF, and a hand-added colour never carries a PDF symbol.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test("a hand-added colour shows its symbol in the palette chip", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "issue-43.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });

  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();

  // The chip is the selectable colour button above the grid (the eraser is
  // the other `aria-pressed` badge, so pick the first one).
  const chip = page.locator("button.badge[aria-pressed]").first();
  const symbolInput = page.getByPlaceholder("Sym.", { exact: true });
  await expect(symbolInput).toHaveValue(/.+/);
  await expect(chip).toContainText(await symbolInput.inputValue());

  // Editing the symbol in the legend row must show up in the chip too.
  await symbolInput.fill("Z");
  await expect(chip).toContainText("Z");
});
