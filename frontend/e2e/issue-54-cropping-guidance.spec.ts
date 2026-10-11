import { expect, test } from "@playwright/test";

/**
 * Issue #54: the Cropping step explains when an imperfect frame or a
 * misaligned image matters, and when no frame can fit the grid — on the
 * manual path only, a file recognised automatically not depending on it.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test.use({ viewport: { width: 375, height: 812 } });

test("the Cropping step explains what an imperfect frame changes", async ({ page }) => {
  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "grille-test.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  await expect(page.getByText("Colonnes")).toBeVisible();

  const guidance = page.getByText("Le cadrage doit-il être parfait ?");
  await expect(guidance).toBeVisible();
  // Closed by default: the explanation does not lengthen the step.
  const seam = page.getByText(/numéros inscrits sur les bords de la grille/);
  await expect(seam).toBeHidden();

  await guidance.click();
  await expect(seam).toBeVisible();
  await expect(page.getByText(/photo prise de biais/)).toBeVisible();
});
