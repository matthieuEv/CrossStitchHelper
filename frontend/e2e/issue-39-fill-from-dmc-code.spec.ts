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
  const shades = (await (
    await request.get("/api/threads/dmc")
  ).json()) as Array<{
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

  const code = page.getByRole("combobox", { name: "Code" });
  const suggestions = page.getByRole("listbox", { name: "Code" });

  // The suggestions are the app's own list, shown as soon as the field gets
  // the focus — not a native datalist, which iPadOS hides in the on-screen
  // keyboard's shortcut bar (review of #39). They follow a printed DMC chart:
  // named whites first, then numbers ascending.
  await code.focus();
  await expect(suggestions).toBeVisible();
  const suggested = (await suggestions.getByRole("option").allInnerTexts()).map(
    (text) => text.trim().split(/\s+/)[0]!,
  );
  expect(suggested).toHaveLength(shades.length);
  expect(suggested.slice(0, 4).map((value) => value.toLowerCase())).toEqual([
    "blanc",
    "white",
    "b5200",
    "ecru",
  ]);
  const numbered = suggested.filter((value) => /^\d+$/.test(value)).map(Number);
  expect(numbered).toEqual([...numbered].sort((a, b) => a - b));
  await code.blur();
  await expect(suggestions).toBeHidden();

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

test.describe("on a touch screen", () => {
  test.use({ hasTouch: true, isMobile: true });

  test("tapping a suggestion fills code, colour and name", async ({
    page,
    request,
  }) => {
    const shades = (await (
      await request.get("/api/threads/dmc")
    ).json()) as Array<{
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
    await page.getByRole("button", { name: "Continuer", exact: true }).tap();
    await page.getByRole("button", { name: /Ajouter une couleur/ }).tap();

    const code = page.getByRole("combobox", { name: "Code" });
    const suggestions = page.getByRole("listbox", { name: "Code" });
    await code.tap();
    await code.pressSequentially("382");
    // Typing narrows the list to the codes starting with what was typed.
    const options = suggestions.getByRole("option");
    for (const text of await options.allInnerTexts())
      expect(text.trim()).toMatch(/^382/);

    await options.filter({ hasText: straw.name }).tap();
    await expect(suggestions).toBeHidden();
    await expect(code).toHaveValue("3820");
    await expect(page.getByPlaceholder("Nom du fil")).toHaveValue(straw.name);
    await expect(page.locator('input[type="color"]')).toHaveValue(
      straw.rgb_hex,
    );
    // The list fits on the phone's screen.
    await code.tap();
    const box = await suggestions.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(375);

    // The on-screen keyboard shrinks the visible area once the field has the
    // focus: the list stays within what is left (above the field if need be).
    await page.setViewportSize({ width: 375, height: 520 });
    // Safari then scrolls the focused field into view.
    await code.scrollIntoViewIfNeeded();
    await expect
      .poll(async () => {
        const list = await suggestions.boundingBox();
        return list === null ? Infinity : list.y + list.height;
      })
      .toBeLessThanOrEqual(520);
    const shrunk = await suggestions.boundingBox();
    expect(shrunk!.y).toBeGreaterThanOrEqual(0);
  });
});
