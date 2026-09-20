# Roadmap — CrossStitchHelper

*Extrait actionnable de `docs/cahier-des-charges.md` §11. Ce fichier est celui qu'on coche au fil de l'avancement ; le cahier des charges reste la version narrative de référence — en cas de divergence, c'est lui qui fait foi sur le fond, ce fichier sur le séquencement.*

Chaque lot est indépendamment livrable et utilisable : il n'y a pas de lot "inutile tant que le suivant n'est pas fini". Les lots 0 à 3 forment la V1 utilisable. Les lots 4 et 5 forment la V2 différenciante. Les lots 6 à 9 sont des amplificateurs.

---

## Lot 0 — Socle technique

- [x] Squelette FastAPI + SQLite + Alembic
- [x] Frontend React/Vite/TypeScript en PWA installable (manifest + service worker)
- [x] Image Docker unique (backend sert aussi le frontend construit)
- [x] `docker-compose.yml` d'exemple avec volume de données
- [x] Jeu de tests et intégration continue de base
- [x] `README.md` d'auto-hébergement (installation, mise à jour, sauvegarde)

**Terminé quand :** `docker compose up` donne une application installable sur l'écran d'accueil d'un iPhone, avec une page d'accueil vide et une API qui répond.

> `npm install && npm run build` (frontend) et `pip install -e ".[dev]" && pytest` (backend) ont désormais tourné pour de vrai — un bug de typage réel a été trouvé et corrigé au passage (voir l'historique), et le `package-lock.json` produit est committé. `docker compose up --build` a aussi été vérifié pour de vrai : construction, `/api/health` répond `ok`, le frontend construit est servi à la racine, les icônes et le manifeste PWA répondent, et la progression survit à un `docker compose down` suivi d'un `up` (le volume `./data` fait bien tout le travail de sauvegarde qu'il prétend faire).

---

## Lot 1 — Noyau de rendu et de suivi

- [x] Modèle de données complet (`patterns`, `palette_entries`, `grids`, `progress`, `progress_events`) — SQLAlchemy + migration Alembic (`backend/app/models.py`, `alembic/versions/0002_pattern_model.py`), API de lecture/synchronisation (`backend/app/api/patterns.py`), 26 tests (`backend/tests/test_patterns.py`, `test_codec.py`)
- [x] Rendu `<canvas>` avec ses trois niveaux de détail (aplats / couleur+trame / couleur+symbole+quadrillage)
- [x] Marquage des cases (tap, glisser, sélection rectangulaire, "toute cette couleur dans la zone visible" via le filtre couleur + remplissage de zone)
- [x] Pan/zoom tactile fluide (Pointer Events) — déplacement au glissé, zoom par boutons et **pincement à deux doigts** (`frontend/src/state/useTracker.ts` `zoomTo`, `frontend/src/screens/TrackScreen.tsx`) tous faits — vérifiés géométriquement (ancrage du point médian), par relecture de code, **et par des événements `PointerEvent` de type `touch` rejoués dans un vrai navigateur** (pincement d'écartement et de fermeture jusqu'aux bornes `MIN_CELL`/`MAX_CELL`, glissé un doigt, tap un doigt — aucune case cochée par accident pendant un pincement)
- [x] Synchronisation par deltas versionnés — `frontend/src/state/useSyncedTracker.ts` (file locale IndexedDB → `POST /api/patterns/{id}/progress`, réconciliation via `missing_ops`), vérifié de bout en bout contre un vrai backend (pas seulement en tests unitaires)
- [x] Cache hors-ligne (IndexedDB via Dexie) — `frontend/src/lib/db.ts` : motif, dernière progression connue et file d'opérations en attente ; `frontend/src/state/usePatternLibrary.ts` bascule serveur → cache → démonstration selon ce qui est disponible
- [x] Grille de démonstration de 255 × 180 injectée directement en base pour les tests de perf — `backend/app/seed.py` / `backend/scripts/seed_demo_pattern.py` (motif procédural, idempotent, jamais de contenu créatif réel)

> L'interface complète des cinq écrans est en place depuis le Lot 0 (portage des maquettes). La persistance existe désormais : le motif, sa grille et la progression vivent en base SQLite, synchronisés par deltas versionnés avec repli hors-ligne sur IndexedDB. Le motif de démonstration client (`frontend/src/demo/`) reste comme dernier repli si ni le serveur ni le cache local ne répondent (premier lancement hors-ligne, ou absence de backend en développement).

**Terminé quand :** on peut cocher des cases sur 45 900 cases avec un pan/zoom fluide sur iPhone, hors-ligne, et retrouver sa progression après rechargement et sur un autre appareil.

**Lot clos.** Aucun appareil iOS physique n'est disponible dans l'environnement de développement de ce projet (contrainte durable, pas ponctuelle) : la validation du pan/pincement s'est donc arrêtée à des événements tactiles réels rejoués dans un navigateur de bureau — voir ci-dessus. C'est un repli assumé, pas un remplacement parfait d'un vrai doigt sur un vrai écran (comportements spécifiques à Safari iOS, défilement à inertie, `touch-action` — non couverts). Si un appareil réel devient disponible plus tard, encore mieux ; en attendant, ça ne bloque plus la suite.

---

## Lot 2 — Import assisté universel

- [x] Assistant : dépôt de fichier (PDF ou image) — sélection, envoyé à `POST /api/imports` (`backend/app/api/imports.py`)
- [x] Aperçu de la page et recadrage manuel de la grille — aperçu raster réel (PyMuPDF pour un PDF, redimensionnement Pillow pour une image), poignées de cadrage inchangées
- [x] Calibrage manuel des dimensions (colonnes/lignes)
- [x] Saisie manuelle de la palette et remplissage des couleurs par zone — éditeur de palette + `frontend/src/components/ImportGridPainter.tsx` (sélection rectangulaire puis peinture, réutilise le rendu canvas du suivi)
- [x] Export `.cshp` (format ouvert documenté) — `GET /api/patterns/{id}/export`, archive ZIP autonome (`backend/app/export_cshp.py`), lien direct depuis l'écran Statistiques

> Aucun moteur de détection automatique ici (ni type de grille, ni dimensions, ni couleurs, ni symboles) — c'est tout le sujet des Lots 4 à 7. L'assistant du Lot 2 pré-remplit ce qu'il peut techniquement (l'aperçu de la page), l'utilisateur fait le reste à la main, comme n'importe quel éditeur de grille papier assisté par ordinateur.

**Terminé quand :** n'importe quel PDF ou image peut être transformé en motif suivable, entièrement à la main. À ce stade, l'application est déjà une alternative crédible à Pattern Keeper. **Fait** — vérifié de bout en bout (dépôt réel → cadrage → dimensions → palette → peinture par zone → motif suivable et synchronisé) par `frontend/e2e/lot2-manual-import.spec.ts` contre un vrai backend, pas seulement en tests unitaires.

> **Modifié au Lot 7 :** le bouton de prise de photo (accès direct à l'appareil photo mobile) a été retiré de l'assistant, avec l'abandon du type D — voir plus bas et `docs/cahier-des-charges.md` §4.4/§13. Déposer une image déjà existante (sélection de fichier) reste possible et continue de suivre exactement ce parcours manuel.

---

## Lot 3 — Statistiques et confort de suivi

- [x] Statistiques complètes (progression globale/par couleur, écheveaux estimés, historique) — la progression globale/par couleur était déjà réelle depuis le Lot 1 ; l'historique (`stats.activity`, séances récentes) était le dernier à être factice (`DEMO_ACTIVITY`/`DEMO_SESSIONS` figées dans `App.tsx`) — remplacé par `GET /api/patterns/{id}/activity` (`backend/app/activity.py`), qui agrège `progress_events` (déjà écrit à chaque synchronisation depuis le Lot 1) plutôt que de dupliquer un second historique
- [x] Filtrage par couleur (mise en évidence, estompage des autres) — déjà réel depuis le Lot 1 (`useTracker.highlight`, estompage dans `pattern/render.ts`)
- [x] Masquage des cases déjà faites — nouveau bouton dans la barre d'outils du Suivi (`useTracker.hideDone`), rend une case faite en toile nue plutôt que délavée
- [x] Surlignage de la ligne/colonne courante — déjà réel depuis le Lot 1 (réticule de `drawOverlay`, `pattern/render.ts`)
- [x] Annulation multi-niveaux — déjà réelle depuis le Lot 1 (pile de 16 états dans `useTracker.ts`)

**Terminé quand :** les quatre besoins initiaux (import, suivi, couleur exacte par case, stats) sont couverts, même si l'import reste manuel. **Fin de la V1.**

**Lot clos.** Vérifié par `frontend/e2e/lot3-stats-and-comfort.spec.ts` contre un vrai backend : une zone cochée apparaît dans un vrai historique de séances (pas les données factices), le masquage change réellement les pixels rendus du canvas, et l'annulation revient sur deux gestes d'affilée (pas un seul).

---

## Lot 4 — Extraction automatique type A

- [x] Analyse structurelle des PDF (polices, rectangles, caractères, texte) — `backend/app/type_a.py`, détection de la police de symboles par géométrie (pavage régulier), jamais par nom de police en dur
- [x] Détection de grille (pavage régulier, pas de grille, dimensions) — dimensions annoncées en clair par le PDF privilégiées sur l'étendue reconstruite (§7.2 étape 6), avec repli et avertissement sinon
- [x] Parseur de police de symboles embarquée (type Cafe Brasserie) — clé de rapprochement grille/légende = (glyphe, couleur du petit rectangle sous le glyphe), pas le glyphe seul : ce fichier de référence réutilise le même glyphe pour deux couleurs différentes selon le type de point (voir le commit du moteur)
- [x] Parseur de légende texte ("Floss Used for…") — table symbole → code DMC → nom, à partir du texte réel de la section « Full Stitches »
- [x] Assemblage multi-pages par numéros d'axes — 8 pages de grille recollées via les numéros de colonnes/lignes imprimés en marge, avec repli par ordre de lecture (confiance réduite + avertissement) si une page n'en a pas d'exploitables

**Terminé quand :** le PDF `fixtures/cafe-brasserie-charting-export/` s'importe en validant simplement les propositions, et que les comptages par couleur obtenus correspondent à ceux de sa page 11 (voir `fixtures/README.md`). **Fait** — les 34 couleurs de la légende correspondent exactement aux comptages de la page 11 « Usage Summary » (reparsés depuis le PDF à chaque exécution des tests, jamais recopiés à la main), vérifié à la fois en tests unitaires (`backend/tests/test_type_a.py`) et en e2e bout en bout contre une vraie instance (`frontend/e2e/lot4-automatic-detection.spec.ts` : dépôt du PDF réel → dimensions et palette déjà pré-remplies → validation sans rien construire à la main → motif suivable). Aucune régression sur les cinq autres fixtures (types B/C/E) : `detect_type_a` s'efface proprement (`None`) sur chacune, pas de faux positif.

**Lot clos.** La détection tourne en tâche de fond (`BackgroundTasks`) plutôt que dans la requête d'upload — nécessaire en pratique : l'analyse de cette fixture (11 pages) prenait 41,6 s avant un correctif de performance (indexation spatiale des rectangles de couleur plutôt qu'un balayage par glyphe, voir l'historique), et reste à ~9,5 s après, toujours trop long pour une requête HTTP synchrone. Le parcours manuel du Lot 2 reste intégralement disponible et jamais contourné de force — une correction peinte à la main l'emporte toujours sur la proposition automatique.

---

## Lot 5 — Extraction automatique types B et C

- [x] Extraction des couleurs par remplissage de rectangles (gestion CMJN/RVB)
- [x] Rapprochement Lab vers la palette DMC
- [x] Mesure de la densité de tracés vectoriels par page pour décider si une superposition à deux pages est nécessaire (ne jamais supposer "page 1 = couleur, page 2 = symboles" par défaut — voir `docs/cahier-des-charges.md` §4.3, cas Summer Flight)
- [x] Superposition des grilles jumelles quand elle s'avère nécessaire
- [x] Reconnaissance des symboles vectoriels avec score de confiance
- [x] Repli manuel explicite quand le score est insuffisant

**Terminé quand :** les quatre fixtures DMC (`winter-wreath-dmc`, `botanical-citrus`, `cucurbit`, `summer-flight`) s'importent chacune avec leurs couleurs correctes, la bonne stratégie de page(s) détectée automatiquement, et un signalement explicite des cases incertaines. **Fin de la V2.**

**Lot clos.** `backend/app/type_bc.py` mesure la densité de tracés par page avant de décider d'une superposition — constat contre-intuitif mesuré (pas supposé) : `winter-wreath-dmc` se comporte comme le cas piège `summer-flight-dmc` (sa page couleur porte déjà ses symboles), seules `botanical-citrus-dmc` et `cucurbit-dmc` superposent une vraie deuxième page. `summer-flight-dmc` bascule honnêtement en type B (reconnaissance de forme trop fragmentée sur son illustration nuancée) plutôt que produire une palette inutilisable. Catalogue couleur DMC→RVB communautaire dans `backend/app/dmc_catalog.py` (228 teintes), distinct de `app/dmc_colors.py` (type A, où le texte de légende fait déjà foi). Les cases incertaines (`uncertain_cells`) sont signalées à la fois dans la bannière de détection et par un repère visuel sur chaque case concernée dans le pinceau de l'assistant (`ImportGridPainter`, `pattern/render.ts`).

---

## Lot 6 — Recettes réutilisables

- [x] Calcul d'empreinte de fichier (polices, motifs de texte d'en-tête, géométrie — jamais le contenu créatif)
- [x] Enregistrement d'une configuration validée comme recette
- [x] Réapplication automatique sur un fichier de même empreinte
- [x] Gestion de la bibliothèque locale de recettes

**Terminé quand :** réimporter un second PDF du même éditeur reprend automatiquement le cadrage déjà validé, sans repasser par l'étape de recadrage manuel.

**Lot clos.** `backend/app/fingerprint.py` calcule l'empreinte à partir de la taille de page, des polices embarquées (préfixe de sous-ensemble PDF retiré — jamais stable d'un export à l'autre) et de libellés génériques de logiciel de charting repérés dans le texte (« Floss Used for », « Symbol »... jamais le titre du motif). Vérifiée contre les six fixtures de référence : `botanical-citrus-dmc` et `cucurbit-dmc`, deux grilles DMC officielles réelles au même gabarit d'export mais à motifs différents, obtiennent la **même** empreinte (constat mesuré, pas provoqué — voir `backend/tests/test_fingerprint.py`) ; les quatre autres fixtures restent chacune distinctes. C'est cette paire réelle, pas une fixture synthétique, qui sert de cas de bout en bout au Lot 6 (`backend/tests/test_recipes.py`, `frontend/e2e/lot6-recettes.spec.ts`).

Une recette (`backend/app/models.py::Recipe`, `backend/app/api/recipes.py`) ne porte que `crop_by_page` — jamais les dimensions ni la palette, contenu propre à chaque motif même au sein d'un même éditeur (cf. Winter Wreath/Summer Flight vs Botanical Citrus/Cucurbit ci-dessus) : voir la précision actée au cahier des charges §8.7. Le rapprochement automatique tourne dans la même tâche de fond que la détection type A/B/C (`_run_auto_detection`, `backend/app/api/imports.py`) plutôt que dans la requête d'upload — l'empreinte y avait d'abord été calculée par erreur avant ce déplacement, un bug trouvé grâce à une régression observée sur les suites e2e Lots 4-5 tournées en parallèle (en local), puis confirmé en CI (job « Image Docker + e2e » passé de ~9 min à ~20 min). Le déplacement seul ne suffisait pas : `app/fingerprint.py` utilisait d'abord `pdfplumber` (comme `app/type_a.py`) pour lister les polices, dont le `page.chars` reconstruit un layout par glyphe même pour une simple liste de noms — mesuré à ~2 s **par page** sur `cafe-brasserie-charting-export` (police de symboles dense), soit ~14 s sur ses onze pages à lui seul, un ajout de plus du double du temps de détection déjà en place. Remplacé par PyMuPDF (`page.get_fonts()`/`page.get_text()`, sans reclustering géométrique) : moins de 0,15 s sur ce même fichier, sans rien perdre à la discrimination des six fixtures de référence (`backend/tests/test_fingerprint.py`). Une recette n'écrase jamais un cadrage déjà commencé à la main. Bibliothèque gérée depuis l'écran Réglages du frontend (lister, supprimer) ; proposée à l'enregistrement à l'étape récapitulative de l'assistant d'import.

---

## Lot 7 — Grilles en images bitmap réutilisées (type E)

Le type D (scan/photo libre, vision par ordinateur en plein cadre) a été retiré de ce lot et abandonné avant tout début d'implémentation — voir `docs/cahier-des-charges.md` §4.4/§13 (décision du 18/09/2026) : aucun fichier de référence réel pour le vérifier, contrairement à tous les autres types, et un problème de vision nettement plus ouvert que le reste du moteur d'extraction. Le bouton de prise de photo est retiré de l'assistant (Lot 2) ; l'import manuel universel reste disponible pour toute image déposée par ailleurs.

**Type E — grilles composées d'images bitmap réutilisées** (voir `docs/cahier-des-charges.md` §4.3 et §4.4, cas River And Mountains) :
- [x] Détection et exclusion des pages de prévisualisation photoréaliste (pas des grilles de travail)
- [x] Extraction du catalogue d'images distinctes réutilisées sur les pages de grille (20 sur la fixture de référence, pas les ~531 initialement supposés — voir plus bas)
- [x] Classification de chaque image du catalogue en (couleur, symbole) — un problème fermé de classification sur un petit catalogue, plus simple qu'une reconnaissance libre
- [x] Repositionnement de chaque case à partir des placements de ces images

**Terminé quand :** le PDF `fixtures/river-and-mountains-laserarts/` s'importe avec ses couleurs et symboles corrects, sans que sa page de prévisualisation photoréaliste ne soit prise pour une page de grille.

**Lot clos.** `backend/app/type_e.py` distingue une page de grille d'une page à exclure par mesure structurelle (taille d'image dominante, quasi carrée) plutôt que par position supposée : la page 1 (prévisualisation photoréaliste) mélange deux tailles d'image pour un rendu par empâtement de texture (69,8 % seulement à la taille dominante, contre 100 % sur une vraie page de grille), et la page 18 (carte d'assemblage des pages, pas une page de travail) place des images bien plus grandes et non carrées — deux régimes largement séparés, jamais un seuil ajusté au pif. Assemblage multi-pages par numéros d'axes (même mécanisme que le type A) sur les 15 pages de grille restantes.

**Correction mesurée en cours de route, pas supposée** (`docs/cahier-des-charges.md` §4.3, `fixtures/README.md`) : le catalogue d'images de la fixture de référence contient réellement **20** images distinctes, pas ~531 comme documenté avant ce lot — 531 était le nombre de *placements* sur une seule page, confondu avec un nombre d'images distinctes. Ces 20 images correspondent exactement aux 20 couleurs DMC de sa légende texte (page 17, comptages exacts par couleur — même rôle de vérité terrain que la page 11 de `cafe-brasserie-charting-export` au Lot 4). Constat notable : rapprocher la couleur de fond de chaque image vers le code DMC le plus proche s'avère peu fiable sur ce fichier (12 des 20 mal identifiées, mesuré) — le signal réellement exploité par `detect_type_e` est le nombre total de placements de chaque image, qui correspond exactement au nombre de points déclaré par la légende pour chaque couleur ; la couleur perceptuelle (`nearest_dmc_among`, `backend/app/dmc_catalog.py`) ne sert que de repli explicite, signalé incertain, pour les images que le comptage ne peut départager sans ambiguïté.

---

## Lot 8 — Finitions

Sous-chantiers assez indépendants pour être livrés en PR séparées (décision du 18/09/2026) plutôt qu'en un seul gros commit.

- [x] Points fractionnés et spéciaux complets dans l'interface (quart, demi, point arrière, point de nœud, perles)
- [x] Sauvegarde/restauration des données
- [x] Thème sombre
- [x] Traductions FR/EN complètes

> **Partage communautaire des recettes retiré du périmètre (décision du 18/09/2026) :** évoqué comme une possibilité éventuelle au cahier des charges §8.7, jamais un engagement. L'utilisateur n'en a pas l'usage — la bibliothèque de recettes reste locale (Lot 6), point final.

**Points fractionnés et spéciaux — terminé.** Modèle de progression étendu à cinq catégories (`backend/app/models.py::Progress.bitmap_half`/`_quarter`/`_backstitch`/`_knots`, migration 0005) au lieu d'une seule, chacune avec son propre espace d'index — jamais partagé entre catégories. `stitched_count`/le pourcentage global restent basés sur le point entier uniquement (§7.1, inchangé). Convention de coordonnées actée pour `Grid.backstitch_json`/`french_knots_json` (jamais précisée avant ce lot) : coins de case pour un segment, centre de case pour un nœud — voir `backend/app/schemas.py::BackstitchSegment`/`FrenchKnot`. Rendu canvas et interaction tactile ajoutés (`frontend/src/pattern/render.ts`, `state/useTracker.ts`, nouvelle barre de sélection de catégorie dans `TrackScreen.tsx`) : point arrière/nœuds interactifs seulement à partir du même seuil de zoom que l'apparition des symboles (`SYMBOL_MIN_CELL`), une case en dessous faisant trop peu de pixels pour distinguer deux éléments voisins au doigt. **Correction après retour d'usage réel (20/09/2026)** : le rendu, lui, ne doit pas dépendre de ce seuil — sur un diagramme papier, le point arrière reste visible même sur une vue d'ensemble dézoomée. Seule l'interaction (cocher) reste réservée au zoom rapproché ; `frontend/src/pattern/render.ts` a été corrigé en conséquence (voir `frontend/e2e/backstitch-visible-zoomed-out.spec.ts`). Perles : déjà couvertes par le mécanisme du point entier existant (`PaletteEntry.count_beads`) — une case « perle » est une case de `layer_full` dont l'entrée de palette référencée représente une perle, jamais une géométrie ou un espace d'index séparé, donc rien de nouveau à construire pour cette catégorie précise. Aucun connecteur d'extraction ne produit encore cette donnée depuis un PDF réel (Lot 9, pas commencé) : le motif de démonstration (`backend/app/seed.py`) porte désormais un petit contenu synthétique dans les quatre catégories pour que la fonctionnalité soit réellement vérifiable en attendant.

**Sauvegarde/restauration des données — terminé.** Un document JSON unique (`backend/app/backup.py`, format `csh-backup`) couvre toute l'instance — tous les motifs, leur palette, leur grille, leur progression (les cinq catégories du sous-chantier précédent comprises), le journal `progress_events` (sans lui l'historique d'activité, §11, disparaîtrait d'une restauration) et les recettes réutilisables (Lot 6). Hors périmètre, délibérément : `ImportJob` (état transitoire d'un assistant d'import en cours, jamais une donnée durable) et `AppMeta` (bookkeeping interne). Deux nouvelles routes (`backend/app/api/backup.py`) : `GET /api/backup` (téléchargement direct, en-tête `Content-Disposition` comme l'export `.cshp` du Lot 2) et `POST /api/backup/restore`, un **remplacement complet** — jamais une fusion, sémantique attendue d'une restauration — que le bouton « Effacer toutes les données » des réglages réutilise tel quel avec un document vide plutôt que de dupliquer une logique de suppression séparée. Sauvegarde automatique quotidienne (`backend/app/auto_backup.py`) : une boucle asyncio dans le processus applicatif (pas de nouvelle dépendance d'infrastructure — `CLAUDE.md` : « aucune installation à plusieurs services »), activable/désactivable depuis les réglages (`AppMeta`, un réglage serveur, pas une préférence de navigateur), un instantané écrit dans `data/backups/` à chaque démarrage puis toutes les 24h, les 14 plus anciens purgés à chaque écriture. Côté frontend (`frontend/src/screens/SettingsScreen.tsx`), une restauration ou un effacement vide aussi le cache hors-ligne (`frontend/src/lib/db.ts::clearOfflineCache`) avant de recharger la page — sans ça, une file d'opérations de progression en attente (`pendingOps`, hors-ligne) risquerait de rejouer une modification obsolète par-dessus les données fraîchement restaurées.

**Thème sombre — terminé.** L'infrastructure (`frontend/src/lib/theme.tsx`, attribut `data-theme`, portée depuis les maquettes) existait déjà mais était incomplète : audit mené case par case (variables CSS numérotées consommées directement en dehors des classes `.tag-*` déjà couvertes, couleurs codées en dur) plutôt que supposée correcte. Trois bugs réels trouvés et corrigés (`frontend/src/index.css`) : `--color-neutral-200`/`-300`/`-400` et `--color-accent-700` n'avaient pas d'override sombre (un encart de vignette et le texte du bouton « Effacer toutes les données » restaient dans leurs teintes claires, ce dernier quasi illisible sur fond sombre) ; `.crop-stage` (assistant d'import) avait un fond `#cfc4ae` codé en dur plutôt qu'une variable. Le rendu canvas (`pattern/render.ts::readGridTheme`, `--canvas-fabric`/`-ground`/`-ink`) suivait déjà correctement le thème, vérifié plutôt que supposé. Éclair de mauvais thème au chargement corrigé : un script bloquant dans `frontend/index.html` applique `data-theme` et la couleur de barre système (`<meta name="theme-color">`, jusque-là seulement pilotée par la préférence système, jamais par un choix explicite en désaccord avec elle) avant le premier rendu, dupliquant à dessein la logique de `theme.tsx` — aucune variable CSS n'est encore chargée à ce stade pour la factoriser autrement.

**Traductions FR/EN complètes — terminé.** L'infrastructure (`frontend/src/i18n/`, garde-fou de compilation entre `fr.ts`/`en.ts`) garantit déjà qu'aucune clé ne manque d'un côté — l'audit a donc porté sur ce que ce garde-fou ne peut pas voir. Trois catégories de bugs réels trouvées et corrigées, aucune supposée : (1) `frontend/src/screens/StatsScreen.tsx` construisait ses formateurs `Intl.DateTimeFormat`/`RelativeTimeFormat` avec la locale du **navigateur** plutôt que la langue choisie dans les Réglages (jours de la semaine et dates relatives des statistiques pouvaient s'afficher dans la mauvaise langue malgré un choix explicite) — centralisé dans `frontend/src/lib/format.ts` (`useWeekdayLabel`, `useSessionRelativeTime`), avec `<html lang>` désormais appliqué dès le script bloquant de `index.html`, comme le thème ; (2) une découverte bien plus large que prévu : **tous** les messages d'erreur de l'API (18 sites `HTTPException`) et **tous** les avertissements de détection automatique (21 sites dans `type_a.py`/`type_bc.py`/`type_e.py`, plus 2 dans `api/imports.py`) étaient des chaînes françaises figées côté serveur, affichées telles quelles côté client même en anglais — restructurés en `code` + `params` (`backend/app/schemas.py::ApiErrorDetail`/`DetectionWarning`), traduits côté client (`frontend/src/lib/api.ts::translateApiError`/`translateDetectionWarning`, clés `error.<code>`/`import.warning.<code>`) avec repli explicite si un code est inconnu du frontend, jamais un plantage. La restructuration du moteur d'extraction (délégué à l'agent `pdf-extraction-specialist`, vérifié indépendamment par relecture complète du diff, `ruff`/`mypy`/`pytest` propres, et re-mesure sur les six fixtures réelles : dimensions, palette, confiance, cases incertaines et nombre d'avertissements strictement identiques avant/après, seul le format change) illustre le principe directeur du projet — mesurer plutôt que supposer, y compris pour un correctif qui n'a rien à voir avec l'extraction elle-même. Un vrai bug trouvé au passage par une vérification systématique des noms de paramètres : `error.import_file_too_large` utilisait `{maxMb}` côté traduction contre `max_mb` envoyé par le serveur (camelCase vs snake_case), qui aurait laissé le texte non interpolé.

---

## Lot 9 — Extraction des points spéciaux (arrière, nœuds, fractionnés)

Repéré en testant le Lot 5 en vrai sur `cafe-brasserie-charting-export` : certains PDF dessinent des points arrière (traits) et des points de nœud (petites formes isolées) directement par-dessus la grille de points comptés — `backstitch_json`/`french_knots_json` existent déjà dans le modèle de données (§6.2) mais aucun connecteur (A/B/C) ne les remplit jamais aujourd'hui, ils restent toujours vides. Le Lot 8 suppose cette donnée déjà présente pour compléter l'*interface* de suivi (cocher un point arrière) — ce lot-ci est ce qui la produit réellement depuis le PDF.

- [ ] Détection des tracés de point arrière : un trait qui **traverse plusieurs cases** (contrairement à un symbole de point plein, toujours contenu dans une seule case, et au quadrillage imprimé, toujours aligné sur les axes — voir `backend/app/type_bc.py::_is_grid_ruling`, à généraliser plutôt qu'à dupliquer)
- [ ] Détection des points de nœud : petite forme isolée, pas alignée sur le pavage régulier des cases coloriées
- [ ] Distinction entre point arrière **décoratif** (texte ou bordure d'une page de garde/légende, hors de la grille de travail) et point arrière **réel** (fait partie du motif, doit être signalé au fil) — ne jamais extraire le premier comme s'il fallait le broder
- [ ] Type A : croiser avec les tableaux de légende déjà présents mais ignorés depuis le Lot 4 ("Floss Used for Backstitch"/"French Knots", distincts de "Full Stitches") pour valider les comptages, comme déjà fait pour les points entiers (§7.3)
- [ ] Vérifier explicitement (fixtures existantes, pas seulement de nouvelles) que cette extraction ne dégrade jamais la reconnaissance des points pleins déjà en place (Lots 4-5) — un point arrière qui traverse une case de la grille de symboles type B/C ne doit jamais faire basculer cette case en case incertaine à tort

**Terminé quand :** les points arrière et de nœuds documentés dans la légende de `cafe-brasserie-charting-export` sont extraits avec des comptages cohérents avec cette légende, cochables dans le suivi (Lot 8), sans qu'aucun point arrière décoratif hors-grille ne soit importé comme faisant partie du motif à broder.

---

## Décisions encore ouvertes (à trancher avant certains lots)

- Licence open source (MIT vs AGPL) — à trancher avant toute publication publique, indépendamment des lots.
