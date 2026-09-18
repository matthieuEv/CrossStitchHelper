import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 6 (docs/roadmap.md) : réimporter
 * un second PDF du même éditeur reprend automatiquement le cadrage validé
 * la première fois — contre une vraie instance, avec de vrais fichiers de
 * référence, la détection et le rapprochement de recette tournant
 * réellement en tâche de fond côté serveur (`backend/app/api/imports.py`,
 * `backend/app/api/recipes.py`, `backend/app/fingerprint.py`).
 *
 * `botanical-citrus-dmc` et `cucurbit-dmc` sont deux grilles DMC officielles
 * réelles, même gabarit d'export mais motifs différents (voir
 * `fixtures/README.md`, `backend/tests/test_fingerprint.py`) : exactement
 * le cas d'usage du lot, sans fixture synthétique fabriquée pour l'occasion.
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

/** Retire toute recette laissée par une exécution précédente de ce même
 * test — sans quoi une recette déjà enregistrée pour l'empreinte DMC
 * officielle ferait échouer l'assertion "pas de bannière sur un premier
 * fichier" (voir `e2e/README.md` : un test doit rester correct qu'il soit
 * lancé une fois ou cent fois de suite sur la même base). */
async function removeLeftoverRecipes(request: APIRequestContext): Promise<void> {
  const response = await request.get("/api/recipes");
  const recipes: Array<{ id: string; label: string }> = await response.json();
  for (const recipe of recipes) {
    if (recipe.label.startsWith(RECIPE_LABEL_PREFIX)) {
      await request.delete(`/api/recipes/${recipe.id}`);
    }
  }
}

test("une recette enregistrée en fin d'import se réapplique sur un second fichier du même éditeur", async ({
  page,
  request,
}) => {
  test.setTimeout(150_000);

  await removeLeftoverRecipes(request);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  const recipeLabel = `${RECIPE_LABEL_PREFIX} ${Date.now()}`;

  // --- Premier import : botanical-citrus, enregistré comme recette -------
  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(BOTANICAL_CITRUS_PATH);

  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // Aucune recette ne correspond encore à cette empreinte — jamais de
  // bannière de recette sur un tout premier fichier.
  await expect(page.getByText(/Cadrage pré-rempli depuis la recette/)).toHaveCount(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click(); // -> Palette
  await page.getByRole("button", { name: "Continuer", exact: true }).click(); // -> Récap

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

  // La recette doit maintenant exister dans la bibliothèque locale (Réglages).
  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await expect(page.getByText(recipeLabel)).toBeVisible();
  await expect(page.getByText("0 utilisation(s)")).toBeVisible();

  // --- Second import : cucurbit, même gabarit DMC officiel ---------------
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(CUCURBIT_PATH);

  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await expect(
    page.getByText(new RegExp(`Cadrage pré-rempli depuis la recette « ${recipeLabel} »`)),
  ).toBeVisible();

  // Les dimensions/palette restent celles, propres, de ce second fichier —
  // jamais copiées depuis la recette (cahier des charges §8.7).
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).not.toHaveValue("");
  await expect(rowsInput!).not.toHaveValue("");

  // La recette réutilisée compte désormais une utilisation.
  await page.getByRole("button", { name: "Réglages", exact: true }).click();
  await expect(page.getByText("1 utilisation(s)")).toBeVisible();

  expect(pageErrors).toEqual([]);
});
