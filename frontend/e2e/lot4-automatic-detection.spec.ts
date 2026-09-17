import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

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

/** `backend/app/seed.py` — identifiant stable, jamais régénéré, palette
 * saisie à la main (pas de `symbol_svg`) : le repli textuel doit s'appliquer. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

interface PatternSummary {
  id: string;
  name: string;
}

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Motif de démonstration introuvable en base");
  return demo;
}

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

/** Fixture type C (voir `fixtures/README.md`) : `detect_type_a` s'y efface
 * proprement (aucun faux positif attendu), utile pour vérifier le repli
 * manuel quand la détection ne trouve rien — contrairement à la fixture
 * type A ci-dessus, qui réussit toujours. */
const NON_TYPE_A_FIXTURE_PATH = fileURLToPath(
  new URL("../../fixtures/winter-wreath-dmc/PATASS117_2C_2.pdf", import.meta.url),
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

test("le cadrage manuel reste bloqué pendant l'analyse automatique", async ({ page }) => {
  // Demande explicite de l'utilisateur : l'overlay de chargement doit rester
  // flouté et bloquant pendant l'analyse — le repli manuel n'a de sens que
  // si l'automatique a vraiment échoué, pas comme une option concurrente
  // pendant l'attente (contrairement à un choix précédent, revenu en
  // arrière ici : voir l'historique de `crop-stage-loading` dans index.css).
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  // Ne pas attendre la détection : le test vise précisément la fenêtre
  // pendant laquelle l'overlay de chargement est affiché.
  await expect(page.locator(".crop-stage-loading")).toBeVisible();
  await expect(page.locator(".crop-handle").first()).not.toBeVisible();
});

test("le cadrage manuel apparaît si la détection automatique ne trouve rien", async ({
  page,
}) => {
  // Repli explicitement demandé : un fichier qui n'est pas de type A (ou
  // dont `detect_type_a` s'efface, voir fixtures/README.md) doit retomber
  // sur le cadrage manuel du Lot 2 une fois l'analyse terminée — jamais
  // pendant qu'elle tourne encore (test précédent).
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(NON_TYPE_A_FIXTURE_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.locator(".crop-stage-loading")).not.toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  // Jamais de bannière de détection : `detect_type_a` ne s'est pas imposé.
  await expect(page.getByText(/Détection automatique/)).not.toBeVisible();

  const topHandle = page.locator(".crop-handle").first();
  await expect(topHandle).toBeVisible();
  const before = await topHandle.boundingBox();
  if (before === null) throw new Error("La poignée de cadrage n'a pas de boîte englobante");

  await page.mouse.move(before.x + before.width / 2, before.y + before.height / 2);
  await page.mouse.down();
  await page.mouse.move(before.x + before.width / 2, before.y + before.height / 2 + 60, {
    steps: 5,
  });
  await page.mouse.up();

  const after = await topHandle.boundingBox();
  if (after === null) throw new Error("La poignée de cadrage n'a pas de boîte englobante");
  expect(after.y).toBeGreaterThan(before.y + 30);
});

test("le cadrage manuel est indépendant d'une page à l'autre", async ({ page }) => {
  // Demande explicite de l'utilisateur : un seul cadrage imposé à toutes
  // les pages n'a pas de sens (une page peut être une légende, une autre la
  // grille) — chaque page garde donc son propre rectangle, voir
  // `backend/app/schemas.py::ImportConfig.crop_by_page`.
  test.setTimeout(60_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(NON_TYPE_A_FIXTURE_PATH);

  await expect(page.getByText("Colonnes")).toBeVisible();
  await expect(page.locator(".crop-stage-loading")).not.toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });

  const handle = page.locator(".crop-handle").first();
  await expect(handle).toBeVisible();
  const pageOneDefault = await handle.boundingBox();
  if (pageOneDefault === null) throw new Error("La poignée de cadrage n'a pas de boîte englobante");

  // Cadre la page 1 (glisse la poignée du haut vers le bas).
  await page.mouse.move(pageOneDefault.x + pageOneDefault.width / 2, pageOneDefault.y + pageOneDefault.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    pageOneDefault.x + pageOneDefault.width / 2,
    pageOneDefault.y + pageOneDefault.height / 2 + 60,
    { steps: 5 },
  );
  await page.mouse.up();
  const pageOneCropped = await handle.boundingBox();
  if (pageOneCropped === null) throw new Error("La poignée de cadrage n'a pas de boîte englobante");
  expect(pageOneCropped.y).toBeGreaterThan(pageOneDefault.y + 30);

  // La page 2 repart du cadrage par défaut, pas de celui de la page 1.
  await page.getByRole("button", { name: "Page suivante" }).click();
  const pageTwoDefault = await page.locator(".crop-handle").first().boundingBox();
  if (pageTwoDefault === null) throw new Error("La poignée de cadrage n'a pas de boîte englobante");
  expect(pageTwoDefault.y).toBeLessThan(pageOneCropped.y - 20);

  // Revenir à la page 1 retrouve le cadrage qu'on y avait laissé.
  await page.getByRole("button", { name: "Page précédente" }).click();
  const pageOneAgain = await page.locator(".crop-handle").first().boundingBox();
  if (pageOneAgain === null) throw new Error("La poignée de cadrage n'a pas de boîte englobante");
  expect(Math.abs(pageOneAgain.y - pageOneCropped.y)).toBeLessThan(5);
});

test("les symboles affichés sont les vrais glyphes du PDF, pas des lettres synthétiques", async ({
  page,
}) => {
  // Bug réel signalé par l'utilisateur : le moteur d'extraction générait une
  // clé interne imprimable (A, B, ..., AB, ...) faute de pouvoir réutiliser
  // le glyphe brut de la police privée du PDF (`app.type_a.symbol_key`) —
  // mais cette clé n'a jamais été pensée comme le symbole à afficher, jamais
  // une liste de symboles connus à l'avance (les symboles varient d'un PDF à
  // l'autre) : `app.imports_engine.render_symbol_svg` découpe désormais le
  // symbole réel depuis la page rendue, voir `tests/test_type_a.py` côté
  // backend pour la vérification exhaustive de sa justesse.
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await expect(page.getByPlaceholder("Code").first()).toBeVisible();

  // L'étape Palette doit elle aussi afficher les vrais symboles, pas
  // seulement l'écran de Suivi final — bug réel trouvé en test manuel : une
  // palette construite localement dans `ImportScreen.tsx` pour le pinceau
  // (`ImportGridPainter`, distincte de `lib/mappers.ts`, déjà correcte)
  // perdait `symbol_svg` en route vers `useImportPainter`. Vérifié ici sur
  // les pastilles de sélection de couleur (de vraies balises `<img>`, pas le
  // canvas du pinceau lui-même : son image s'y décode de façon asynchrone,
  // trop vite et de façon trop peu fiable pour une course dans un test).
  const paletteSwatchImages = page.locator('button.badge img[src^="data:image/svg+xml;base64,"]');
  await expect(paletteSwatchImages.first()).toBeVisible();
  expect(await paletteSwatchImages.count()).toBeGreaterThanOrEqual(34);

  // Repère à côté de la clé éditable (`symbol_key`) de la légende du bas —
  // un deuxième site distinct qui perdait aussi `symbol_svg` avant d'être
  // corrigé, trouvé par le même bug réel que les pastilles ci-dessus.
  const legendRowImages = page.locator(
    'div:has(> input[type="color"]) img[src^="data:image/svg+xml;base64,"]',
  );
  await expect(legendRowImages.first()).toBeVisible();
  expect(await legendRowImages.count()).toBeGreaterThanOrEqual(34);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e symboles réels ${Date.now()}`);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  // La légende (`ColorList.tsx`) affiche le symbole réel en image, pas la
  // lettre synthétique en texte — au moins les 34 couleurs DMC de la
  // légende du PDF.
  const symbolImages = page.locator('img[src^="data:image/svg+xml;base64,"]');
  await expect(symbolImages.first()).toBeVisible();
  expect(await symbolImages.count()).toBeGreaterThanOrEqual(34);

  expect(pageErrors).toEqual([]);
});

test("une palette saisie à la main garde son repli textuel, sans symbole réel à afficher", async ({
  page,
  request,
}) => {
  // Contrepartie du test précédent : le motif de démonstration (Lot 1, pas
  // un import PDF) n'a jamais eu de PDF source à découper — la légende doit
  // continuer d'afficher le texte de `symbol_key`, jamais casser en essayant
  // d'afficher une image absente.
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  await expect(page.getByText("DMC 310")).toBeVisible();
  expect(await page.locator('img[src^="data:image/svg+xml;base64,"]').count()).toBe(0);
});
