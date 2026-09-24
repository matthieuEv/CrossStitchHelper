import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Checks Lot 6's "done when" criterion (docs/roadmap.md): re-importing a
 * second PDF from the same publisher automatically reuses the cropping
 * validated the first time — against a real instance, with real reference
 * files, with detection and recipe matching really running as a background
 * task on the server (`backend/app/api/imports.py`,
 * `backend/app/api/recipes.py`, `backend/app/fingerprint.py`).
 *
 * `botanical-citrus-dmc` and `cucurbit-dmc` are two real official DMC charts,
 * same export template but different patterns (see `fixtures/README.md`,
 * `backend/tests/test_fingerprint.py`): exactly the lot's use case, with no
 * synthetic fixture fabricated for the occasion.
 */

const BOTANICAL_CITRUS_PATH = fileURLToPath(
  new URL(
    "../../fixtures/botanical-citrus-dmc/agrumes_-_planche_botanique.pdf",
    import.meta.url,
  ),
);
const CUCURBIT_PATH = fileURLToPath(
  new URL("../../fixtures/cucurbit-dmc/Cucurbitaces.pdf", import.meta.url),
);

const DETECTION_TIMEOUT = 90_000;
const RECIPE_LABEL_PREFIX = "Officiel DMC e2e";

/** Removes any recipe left by a previous run of this same test — otherwise a
 * recipe already saved for the official DMC fingerprint would fail the "no
 * banner on a first file" assertion (see `e2e/README.md`: a test must stay
 * correct whether it runs once or a hundred times in a row on the same
 * database). */
async function removeLeftoverRecipes(request: APIRequestContext): Promise<void> {
  const response = await request.get("/api/recipes");
  const recipes: Array<{ id: string; label: string }> = await response.json();
  for (const recipe of recipes) {
    if (recipe.label.startsWith(RECIPE_LABEL_PREFIX)) {
      await request.delete(`/api/recipes/${recipe.id}`);
    }
  }
}

test("a recipe saved at the end of an import is re-applied to a second file from the same publisher", async ({
  page,
  request,
}) => {
  test.setTimeout(150_000);

  await removeLeftoverRecipes(request);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  const recipeLabel = `${RECIPE_LABEL_PREFIX} ${Date.now()}`;

  // --- First import: botanical-citrus, saved as a recipe -----------------
  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(BOTANICAL_CITRUS_PATH);

  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // No recipe matches this fingerprint yet — never a recipe banner on the
  // very first file.
  await expect(page.getByText(/Cadrage pré-rempli depuis la recette/)).toHaveCount(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click(); // -> Palette
  await page.getByRole("button", { name: "Continuer", exact: true }).click(); // -> Summary

  await page
    .getByLabel("Enregistrer le cadrage comme recette réutilisable")
    .check();
  await page
    .getByLabel("Nom de la recette (ex. l'éditeur ou la boutique)")
    .fill(recipeLabel);

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e recette ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  // The recipe must now exist in the local library (Settings).
  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await expect(page.getByText(recipeLabel)).toBeVisible();
  await expect(page.getByText("0 utilisation(s)")).toBeVisible();

  // --- Second import: cucurbit, same official DMC template ---------------
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(CUCURBIT_PATH);

  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await expect(
    page.getByText(new RegExp(`Cadrage pré-rempli depuis la recette « ${recipeLabel} »`)),
  ).toBeVisible();

  // Dimensions/palette remain this second file's own — never copied from the
  // recipe (specification §8.7).
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).not.toHaveValue("");
  await expect(rowsInput!).not.toHaveValue("");

  // The reused recipe now counts one use.
  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await expect(page.getByText("1 utilisation(s)")).toBeVisible();

  expect(pageErrors).toEqual([]);
});
