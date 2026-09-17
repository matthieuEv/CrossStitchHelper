import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 5 (docs/roadmap.md) : les
 * fixtures DMC vectorielles (types B/C) s'importent avec leurs couleurs
 * correctes, la bonne stratégie de page(s) détectée automatiquement, et un
 * signalement explicite des cases incertaines — contre une vraie instance,
 * avec les vrais fichiers de référence, la détection tournant réellement en
 * tâche de fond côté serveur (voir `backend/app/api/imports.py`,
 * `backend/app/type_bc.py`).
 *
 * Plus lent que le reste de cette suite (analyse structurelle réelle,
 * quelques secondes à une dizaine de secondes selon la fixture) : c'est
 * attendu, voir `backend/tests/test_type_bc.py` pour la vérification
 * exhaustive de la justesse de l'extraction elle-même — ces tests-ci ne
 * vérifient que le parcours utilisateur bout en bout.
 */

/** Type C, superposition à deux pages réellement nécessaire (page couleur
 * propre + page symboles séparée) — voir `fixtures/README.md`. */
const BOTANICAL_CITRUS_PATH = fileURLToPath(
  new URL(
    "../../fixtures/botanical-citrus-dmc/agrumes_-_planche_botanique.pdf",
    import.meta.url,
  ),
);

/** Cas piège du Lot 5 (cahier des charges §4.3) : même gabarit visuel DMC,
 * mais la page couleur porte déjà elle-même une quantité de tracés
 * vectoriels comparable à une page symboles — le connecteur doit s'en
 * apercevoir et ne jamais superposer une deuxième page redondante à
 * l'aveugle. La reconnaissance de forme s'y avère en plus trop peu fiable
 * sur l'ensemble du fichier (illustration richement nuancée), d'où un repli
 * honnête en type B plutôt qu'une palette de plusieurs centaines d'entrées
 * inutilisable — voir `backend/tests/test_type_bc.py`. */
const SUMMER_FLIGHT_PATH = fileURLToPath(
  new URL("../../fixtures/summer-flight-dmc/vol_de_te.pdf", import.meta.url),
);

const DETECTION_TIMEOUT = 90_000;

test("un PDF type C avec superposition pré-remplit l'assistant avec de vrais symboles et signale les cases incertaines", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(BOTANICAL_CITRUS_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // Signalement explicite des cases incertaines (roadmap Lot 5, "terminé
  // quand") : jamais une case fausse laissée sans indication dans la
  // bannière de détection.
  await expect(page.getByText(/case\(s\) signalée\(s\) comme incertaine\(s\)/)).toBeVisible();

  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).not.toHaveValue("");
  await expect(rowsInput!).not.toHaveValue("");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Palette : au moins une entrée doit porter un vrai symbole découpé
  // du PDF (page symboles superposée), pas seulement une couleur — mêmes
  // sélecteurs que le Lot 4 pour les pastilles et la légende éditable.
  const paletteSwatchImages = page.locator('button.badge img[src^="data:image/svg+xml;base64,"]');
  await expect(paletteSwatchImages.first()).toBeVisible();

  const legendRowImages = page.locator(
    'div:has(> input[type="color"]) img[src^="data:image/svg+xml;base64,"]',
  );
  await expect(legendRowImages.first()).toBeVisible();

  // Repère visuel des cases incertaines sur le pinceau lui-même (Lot 5,
  // `pattern/render.ts`) : le texte d'indicatif doit apparaître sous le
  // canvas, avec un décompte non nul — cohérent avec la bannière ci-dessus.
  await expect(page.getByText(/case\(s\) marquée\(s\) d'un repère/)).toBeVisible();

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e type C ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Doit atterrir sur un vrai écran de suivi, motif entier assemblé.
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  const symbolImages = page.locator('img[src^="data:image/svg+xml;base64,"]');
  await expect(symbolImages.first()).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test("le cas piège summer-flight-dmc ne superpose jamais une page redondante et se replie honnêtement en type B", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(SUMMER_FLIGHT_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type B/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Type B : couleur seule, jamais un symbole présenté comme fiable alors
  // qu'il ne l'est pas (`app/type_bc.py` : repli plutôt qu'une palette de
  // plusieurs centaines d'entrées inutilisable). Une palette réelle doit
  // malgré tout être là, pas une liste vide comme au Lot 2 manuel.
  await expect(page.getByPlaceholder("Code").first()).toBeVisible();
  expect(await page.getByPlaceholder("Code").count()).toBeGreaterThan(0);
  expect(
    await page.locator('button.badge img[src^="data:image/svg+xml;base64,"]').count(),
  ).toBe(0);

  expect(pageErrors).toEqual([]);
});
