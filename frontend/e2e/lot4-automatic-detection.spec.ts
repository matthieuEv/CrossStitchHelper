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

/**
 * ~10s en local (voir `backend/tests/test_type_a.py`), mais nettement plus
 * sous Docker sur les runners CI (CPU partagé, moins de coeurs) — mesuré en
 * pratique : un délai de 30s faisait systématiquement échouer les deux
 * tests qui attendent la fin de l'analyse dans le job "Image Docker + e2e"
 * (jamais en local). Généreux plutôt que de deviner un chiffre exact.
 */
const DETECTION_TIMEOUT = 90_000;

test("un PDF type A reconnu pré-remplit l'assistant, qu'il suffit de valider", async ({
  page,
}) => {
  test.setTimeout(120_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Étape Cadrage : le message d'analyse en cours apparaît, puis la bannière
  // de détection avec les dimensions déjà pré-remplies — sans aucune saisie.
  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

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

test("taper des dimensions à la main pendant l'analyse ne plante ni le client ni le serveur", async ({
  page,
}) => {
  // Bug réel trouvé en test manuel : le message affiché pendant l'analyse
  // invite explicitement à cadrer ou saisir les dimensions à la main en
  // attendant (`import.detection.running`) — si l'utilisateur le fait
  // vraiment, avant que l'analyse en tâche de fond (~10s sur cette fixture)
  // n'ait fini, deux choses plantaient : le client (`Uint8Array.set` avec
  // une grille détectée devenue trop longue pour les nouvelles dimensions
  // tapées) et le serveur (500 sur `PATCH /config`, même cause côté
  // `apply_fills`). Voir les commits de correction pour le détail.
  test.setTimeout(90_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Ne pas attendre la détection : taper tout de suite, comme un
  // utilisateur pressé qui suit l'invite du message affiché pendant
  // l'analyse plutôt que de patienter les ~10s qu'elle prend réellement.
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("92");
  await rowsInput!.fill("74");

  const configPatch = page.waitForResponse((response) => response.url().includes("/config"));
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  expect((await configPatch).status()).toBe(200);

  // Toujours utilisable : l'étape Palette s'affiche (vide, puisque
  // l'utilisateur a pris la main avant que la détection ne propose quoi que
  // ce soit — comportement Lot 2 normal), pas un écran blanc planté.
  await expect(page.getByRole("button", { name: /Ajouter une couleur/ })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("changer des dimensions déjà détectées ne plante pas non plus", async ({ page }) => {
  // Même bug que le test précédent, mais reproduit de façon déterministe
  // (sans dépendre de battre une course de ~10s) : on laisse la détection
  // se terminer et pré-remplir 255×180 avec une vraie `detected_cells`,
  // *puis* on corrige les dimensions — exactement le geste qui faisait
  // planter le client (`Uint8Array.set`, grille détectée devenue trop
  // longue pour 92×74) et le serveur (500 sur `PATCH /config`).
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await expect(columnsInput!).toHaveValue("255", { timeout: DETECTION_TIMEOUT });
  await expect(rowsInput!).toHaveValue("180");
  expect(pageErrors).toEqual([]); // pas encore planté à ce stade

  await columnsInput!.fill("92");
  expect(pageErrors).toEqual([]); // toujours pas, même avec rows=180 encore incohérent
  await rowsInput!.fill("74");
  expect(pageErrors).toEqual([]);

  const configPatch = page.waitForResponse((response) => response.url().includes("/config"));
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  expect((await configPatch).status()).toBe(200);

  await expect(page.getByRole("button", { name: /Ajouter une couleur/ })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
