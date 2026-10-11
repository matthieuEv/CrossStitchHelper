import { expect, test } from "@playwright/test";

/**
 * Issue #39: on the import wizard's Palette step, typing a DMC code fills in
 * that shade's colour and thread name — once the field is left, and only when
 * the code really changed, so a name corrected by hand is never overwritten
 * by just passing through the field.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test.use({ viewport: { width: 375, height: 812 } });

test("a DMC code fills in its colour and name", async ({ page, request }) => {
  // Expected values come from the server's chart, not hard-coded here.
  const shades = (await (await request.get("/api/threads/dmc")).json()) as Array<{
    code: string;
    name: string;
    rgb_hex: string;
  }>;
  const straw = shades.find((shade) => shade.code === "3820");
  if (straw === undefined) throw new Error("DMC 3820 missing from the chart");

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
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();

  const code = page.getByLabel("Code", { exact: true });
  const name = page.getByPlaceholder("Nom du fil");
  const colour = page.locator('input[type="color"]');

  // An unknown code changes nothing.
  const initialColour = await colour.inputValue();
  await code.fill("zz9");
  await code.blur();
  await expect(name).toHaveValue("");
  await expect(colour).toHaveValue(initialColour);

  // A known code fills in colour and name — case does not matter.
  await code.fill("3820");
  await code.blur();
  await expect(name).toHaveValue(straw.name);
  await expect(colour).toHaveValue(straw.rgb_hex);

  // A name corrected by hand survives passing through the code field again.
  await name.fill("Jaune paille");
  await name.blur();
  await code.focus();
  await code.blur();
  await expect(name).toHaveValue("Jaune paille");

  // Lettered codes match whatever the case typed.
  await code.fill("ECRU");
  await code.blur();
  const ecru = shades.find((shade) => shade.code.toLowerCase() === "ecru");
  await expect(name).toHaveValue(ecru!.name);
});
