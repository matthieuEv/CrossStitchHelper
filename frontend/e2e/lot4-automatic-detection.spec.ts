import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 4 (docs/roadmap.md) : le PDF de
 * référence type A s'importe en validant simplement les propositions —
 * contre une vraie instance, avec le vrai fichier de référence (pas un
 * extrait synthétique), la détection tournant réellement en tâche de fond
 * côté serveur (voir `backend/app/api/imports.py`).
 *
 * Plus lent que le reste de cette suite (analyse structurelle réelle,
 * ~10 s) : c'est attendu, voir `backend/tests/test_type_a.py` pour la
 * vérification exhaustive de la justesse de l'extraction elle-même — ce
 * test-ci ne vérifie que le parcours utilisateur bout en bout.
 */

async function remainingCount(page: Page): Promise<number> {
  const text = await page.getByText(/restants$/).first().textContent();
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`Compteur "restants" introuvable dans : ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

const FIXTURE_PATH = fileURLToPath(
  new URL(
    "../../fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf",
    import.meta.url,
  ),
);

test("un PDF type A reconnu pré-remplit l'assistant, qu'il suffit de valider", async ({
  page,
}) => {
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Étape Cadrage : le message d'analyse en cours apparaît, puis la bannière
  // de détection avec les dimensions déjà pré-remplies — sans aucune saisie.
  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({ timeout: 30_000 });

  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).toHaveValue("255");
  await expect(rowsInput!).toHaveValue("180");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Palette : déjà peuplée par la détection, rien à ajouter — juste
  // vérifier qu'une vraie palette (au moins les 34 couleurs DMC de la
  // légende) est bien là, pas une liste vide que l'utilisateur devrait
  // remplir à la main comme au Lot 2.
  await expect(page.getByPlaceholder("Code").first()).toBeVisible();
  expect(await page.getByPlaceholder("Code").count()).toBeGreaterThanOrEqual(34);
  await expect(page.getByText(/\d+ \/ 45\s?900 cases peintes/)).toBeVisible();

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Récap : nom, puis validation — l'utilisateur n'a fait que
  // confirmer une proposition, jamais construit la grille lui-même.
  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e type A ${Date.now()}`);

  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Doit atterrir sur un vrai écran de suivi, motif entier assemblé — bien
  // plus que ce qu'une peinture manuelle produirait dans un test rapide.
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  expect(await remainingCount(page)).toBeGreaterThan(30_000);
});
