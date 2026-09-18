import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 7 (docs/roadmap.md) : le PDF
 * `fixtures/river-and-mountains-laserarts/` (type E — catalogue fermé
 * d'images bitmap réutilisées, éditeur tiers LaserArtsDesigns) s'importe
 * avec ses couleurs et symboles corrects, sans que sa page de
 * prévisualisation photoréaliste (page 1, ~40 000 placements d'image) ne
 * soit prise pour une page de grille — contre une vraie instance, la
 * détection tournant réellement en tâche de fond côté serveur
 * (`backend/app/api/imports.py`, `backend/app/type_e.py`).
 *
 * Plus lent que le reste de cette suite (analyse structurelle réelle sur un
 * PDF de 18 pages, dizaines de milliers de placements d'image sur la seule
 * page de couverture) : c'est attendu, voir `backend/tests/test_type_e.py`
 * pour la vérification exhaustive de la justesse de l'extraction — ces
 * tests-ci ne vérifient que le parcours utilisateur bout en bout.
 */

const RIVER_AND_MOUNTAINS_PATH = fileURLToPath(
  new URL(
    "../../fixtures/river-and-mountains-laserarts/RiverAndMountains-CS.pdf",
    import.meta.url,
  ),
);

const DETECTION_TIMEOUT = 90_000;

test("un PDF type E (catalogue d'images réutilisées) pré-remplit l'assistant avec de vraies icônes couleur+symbole", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page
    .locator('input[type="file"][accept*="pdf"]')
    .setInputFiles(RIVER_AND_MOUNTAINS_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type E/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  // Dimensions annoncées en clair par la légende du PDF (page 17) : 217×206.
  await expect(columnsInput!).toHaveValue("217");
  await expect(rowsInput!).toHaveValue("206");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Palette : 20 couleurs DMC réelles, chacune avec sa vraie icône
  // (couleur + symbole déjà combinés) découpée du PDF — jamais une pastille
  // vide ni du texte de repli. `.count()` ne réessaie jamais tout seul
  // (contrairement à `toBeVisible()`) : on attend d'abord qu'un badge soit
  // visible pour laisser l'étape Palette finir de se peupler.
  const paletteSwatchImages = page.locator('button.badge img[src^="data:image/svg+xml;base64,"]');
  await expect(paletteSwatchImages.first()).toBeVisible();
  expect(await paletteSwatchImages.count()).toBe(20);
  expect(await page.getByPlaceholder("Code").count()).toBe(20);

  // Fichier propre (cahier des charges, Lot 7 "terminé quand") : aucune
  // case ne devrait être signalée incertaine ici — le comptage exact
  // suffit à identifier les 20 couleurs sans ambiguïté sur ce fichier.
  await expect(page.getByText(/case\(s\) marquée\(s\) d'un repère/)).toHaveCount(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e type E ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Doit atterrir sur un vrai écran de suivi, motif entier assemblé
  // (mosaïque de 15 pages de grille recollées par numéros d'axes).
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  const symbolImages = page.locator('img[src^="data:image/svg+xml;base64,"]');
  await expect(symbolImages.first()).toBeVisible();

  expect(pageErrors).toEqual([]);
});
