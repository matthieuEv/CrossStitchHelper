# CLAUDE.md — guide pour travailler sur CrossStitchHelper

Ce fichier est le point d'entrée pour toute session Claude Code travaillant sur ce dépôt. Lis-le avant de commencer, et relis `docs/cahier-des-charges.md` avant toute décision d'architecture non couverte ici.

## En une phrase

CrossStitchHelper est une webapp (PWA) gratuite, open source et **auto-hébergée** qui transforme un PDF de grille de point de croix en motif suivable, avec cochage des cases, couleur exacte par case et statistiques. Cible principale : iPhone/iPad via Safari.

## Documents de référence (à lire dans cet ordre)

1. `docs/fonctionnalites-et-limites.md` — ce que l'app fait et ne fait jamais, en langage clair. Sert de garde-fou de périmètre : si une fonctionnalité demandée n'y figure pas, vérifier avant de l'ajouter.
2. `docs/cahier-des-charges.md` — la spécification complète : architecture, modèle de données, API, moteur d'extraction, exigences non fonctionnelles, décisions actées. **C'est la source de vérité technique.**
3. `docs/roadmap.md` — découpage en lots livrables indépendamment, avec critères "terminé quand". Toujours situer une tâche dans son lot avant de la commencer.

Ne jamais dupliquer ou reformuler le contenu de ces documents ailleurs dans le code (pas de deuxième roadmap dans un README de sous-dossier, par exemple) — un seul endroit par information.

## Décisions non négociables (rappel condensé — détail dans le cahier des charges §3 et §13)

- **Tout self-hosted.** Aucun appel réseau obligatoire vers un service tiers. Aucune télémétrie.
- **Frontend + backend séparés.** Le calcul lourd (parsing PDF, vision) reste côté serveur (Python/FastAPI). Le client React ne doit jamais embarquer de traitement PDF lourd.
- **La progression de suivi est stockée séparément de la grille source.** Ne jamais modifier la structure de `grids` et `progress` de façon couplée — un ré-import ne doit jamais pouvoir écraser une progression existante.
- **Aucun contenu de motif n'est jamais partagé entre utilisateurs**, ni dans les "recettes" d'import (qui ne contiennent que des paramètres géométriques/structurels), ni ailleurs.
- **Le PDF source n'est pas conservé** au-delà de l'extraction, sauf option explicite activée par l'utilisateur.
- **Aucune installation à plusieurs services.** Pas de Redis, pas de Postgres, pas de broker de tâches. SQLite + un conteneur applicatif. Toute proposition d'ajouter une dépendance d'infra doit être justifiée par un besoin réel, pas par habitude.
- **Le rendu de grille est en `<canvas>`, jamais un élément DOM par case.** Un motif de référence fait 45 900 cases (voir `fixtures/`) — tout composant de rendu doit être testé avec un motif de cette taille avant d'être considéré fini.

## Structure du dépôt

```
backend/        API FastAPI, moteur d'extraction PDF, base SQLite
frontend/       PWA React/TypeScript, rendu canvas, assistant d'import
docs/           spécifications (voir ci-dessus)
fixtures/       PDF de référence pour les tests d'extraction (voir plus bas)
.claude/
  agents/       sous-agents spécialisés pour ce dépôt
  skills/       procédures réutilisables (ajout de connecteur, vérification des fixtures)
```

`backend/` et `frontend/` sont vides au démarrage du Lot 0 — voir `docs/roadmap.md`.

## Jeu de tests de référence (`fixtures/`)

Six PDF réels servent de vérité terrain pour tout le moteur d'extraction, couvrant les quatre types actifs A/B/C/E de `docs/cahier-des-charges.md` §4.4 (le type D a été abandonné, voir plus bas). Toute modification du parseur doit être vérifiée contre ces valeurs connues avant d'être considérée correcte — détail complet dans `fixtures/README.md`.

- **`cafe-brasserie-charting-export/` — type A.** Police embarquée personnalisée (un glyphe = un symbole), légende texte complète. Dimensions attendues : 255 × 180 cases, 34 couleurs, comptages exacts par couleur en page 11.
- **`botanical-citrus-dmc/`, `cucurbit-dmc/` — type C, superposition nette.** Deux grilles DMC où la page couleur a peu de tracés vectoriels et la page symboles en a beaucoup — la séparation en deux pages est fiable.
- **`winter-wreath-dmc/`, `summer-flight-dmc/` — type C, cas piège.** Même gabarit visuel DMC que les deux fixtures ci-dessus, mais **la page couleur porte déjà elle-même ses tracés de symbole** (mesuré au Lot 5, pas visible à l'œil pour `winter-wreath-dmc` — voir `fixtures/README.md`) : ne jamais supposer "page 1 = couleur seule" sans mesurer la densité de tracés par page d'abord. Ces deux fichiers doivent faire échouer un connecteur qui ferait cette hypothèse aveuglément.
- **`river-and-mountains-laserarts/` — type E.** Éditeur tiers, structure entièrement différente : la grille est composée de petites images bitmap réutilisées (couleur + symbole déjà combinés dans chaque image, 20 images distinctes mesurées au Lot 7 — pas les ~531 d'abord supposés, voir `docs/roadmap.md`), pas de rectangles colorés ni de tracés vectoriels. La page 1 (prévisualisation photoréaliste) et la page 18 (carte d'assemblage des pages) sont exclues de l'extraction par mesure structurelle, pas par position de page supposée.

**Enseignement à retenir :** même au sein d'un seul éditeur (DMC) et d'un gabarit visuel identique, la structure interne varie d'un fichier à l'autre (`winter-wreath-dmc`/`summer-flight-dmc` vs `botanical-citrus-dmc`/`cucurbit-dmc`) — et cette structure réelle n'est pas toujours celle que suggère un premier examen visuel du PDF, `winter-wreath-dmc` en étant la preuve directe. Ne jamais coder une heuristique d'extraction qui suppose une structure fixe sans la vérifier sur le fichier en cours — toujours mesurer avant de décider.

Avant de considérer une évolution du moteur d'extraction comme terminée, exécuter la procédure du skill `verify-extraction-fixtures` (voir `.claude/skills/`).

## Conventions de code

- **Backend** : Python 3.12, FastAPI, `pdfplumber`/`PyMuPDF` pour l'extraction, SQLAlchemy + Alembic pour la base, typage strict (mypy propre), tests avec `pytest`.
- **Frontend** : TypeScript strict, React, rendu de grille en `<canvas>` écrit à la main (pas de dépendance lourde de grille virtualisée générique — la logique de niveaux de détail est spécifique au domaine).
- **Chaînes utilisateur** : toujours passer par les clés i18n (français + anglais dès le départ), jamais de texte en dur dans les composants.
- **Commits** : messages en français ou anglais au choix, mais cohérents dans un même lot ; référencer le numéro de lot du `docs/roadmap.md` quand c'est pertinent.
- **Tests** : toute fonctionnalité touchant à l'extraction ou au modèle de données de grille doit avoir un test utilisant les fixtures ci-dessus.

## Statut actuel

**Lots 0 et 1 terminés.** Le backend FastAPI + SQLite + Alembic, le frontend PWA React/TypeScript, l'image Docker unique, la CI et le README d'auto-hébergement sont en place. Les cinq écrans des maquettes sont implémentés et le suivi est réellement interactif (cochage, déplacement, zoom dont le pincement à deux doigts, filtre par couleur, sélection de zone, annulation), persisté en base et synchronisé entre appareils par deltas versionnés (`backend/app/api/patterns.py`), avec repli hors-ligne sur IndexedDB (`frontend/src/state/useSyncedTracker.ts`). **Aucun appareil iOS physique n'est disponible dans cet environnement de développement** (contrainte durable) : le pan/pincement est validé par événements tactiles réels rejoués dans un navigateur de bureau, pas sur un vrai iPhone — voir `docs/roadmap.md` Lot 1 pour le détail exact de ce que ça couvre et ne couvre pas.

**Lot 2 terminé.** L'assistant d'import (`backend/app/api/imports.py`, `frontend/src/screens/ImportScreen.tsx`) lit vraiment le fichier déposé : aperçu raster réel (avec navigation entre pages pour un PDF multi-pages), cadrage, dimensions, palette et peinture par zone à la main (`frontend/src/components/ImportGridPainter.tsx`, réutilise le rendu canvas du suivi), jusqu'à un motif réellement suivable. Aucune détection automatique — ça reste les Lots 4 à 7. Export `.cshp` disponible depuis l'écran Statistiques. `frontend/src/demo/` reste utile au-delà de ça : c'est le repli hors-ligne de premier lancement quand ni le serveur ni le cache IndexedDB n'ont encore de motif.

**Lot 3 terminé — fin de la V1.** Les statistiques (`frontend/src/screens/StatsScreen.tsx`) sont désormais entièrement réelles : l'historique d'activité vient de `GET /api/patterns/{id}/activity` (`backend/app/activity.py`), qui agrège le journal `progress_events` déjà écrit à chaque synchronisation (Lot 1) plutôt que de dupliquer un second historique. Le filtrage par couleur, le surlignage ligne/colonne et l'annulation multi-niveaux existaient déjà depuis le Lot 1 ; le seul ajout de confort réellement nouveau est le masquage des cases déjà brodées (`useTracker.hideDone`, bouton dans la barre d'outils du Suivi).

**Lot 4 terminé — début de la V2.** Premier moteur d'extraction automatique (`backend/app/type_a.py`, type A — export logiciel structuré avec police de symboles embarquée). Tourne en tâche de fond (`BackgroundTasks`, `POST /api/imports`) plutôt que dans la requête : l'analyse structurelle d'un PDF réel prend plusieurs secondes, jamais adapté à une requête HTTP synchrone (cahier des charges §5.2). Le résultat ne fait que pré-remplir la même configuration modifiable qu'au Lot 2 (`ImportConfig.detected_cells`, sous les zones peintes à la main via `apply_fills(..., base=...)`) — jamais un résultat imposé, une correction manuelle l'emporte toujours. Vérifié contre les six fixtures de référence : les 34 couleurs de `cafe-brasserie-charting-export` correspondent exactement aux comptages de sa page 11, et `detect_type_a` s'efface proprement (aucun faux positif) sur les cinq fixtures d'un autre type.

**Lot 5 terminé.** Deuxième moteur d'extraction automatique (`backend/app/type_bc.py`, types B/C — grilles vectorielles DMC sans police de symboles). `POST /api/imports` essaie `detect_type_a` puis, s'il ne reconnaît rien, `detect_type_bc` (`_run_auto_detection`, `backend/app/api/imports.py`) : un seul résultat de détection par fichier. La couleur de chaque case vient du remplissage d'un rectangle vectoriel, rapprochée de `backend/app/dmc_catalog.py` (catalogue communautaire DMC→RVB, 228 teintes, distinct de `app/dmc_colors.py` du type A) par distance Lab — jamais RVB brute. La densité de tracés vectoriels est mesurée par page avant de décider d'une superposition à deux pages : constat mesuré (pas supposé) que `winter-wreath-dmc` se comporte comme le cas piège `summer-flight-dmc` (sa page couleur porte déjà ses symboles), seules `botanical-citrus-dmc` et `cucurbit-dmc` en superposent vraiment une deuxième. `summer-flight-dmc` bascule honnêtement en type B (reconnaissance de forme trop peu fiable sur son illustration nuancée) plutôt que produire une palette inutilisable. Les cases incertaines (`ImportConfig.uncertain_cells`) sont signalées à la fois dans la bannière de détection et par un repère visuel sur chaque case concernée dans le pinceau de l'assistant.

**Lot 6 terminé.** Recettes réutilisables (`backend/app/fingerprint.py`, `backend/app/api/recipes.py`) : une empreinte de fichier (taille de page, polices embarquées sans leur préfixe de sous-ensemble, libellés génériques de logiciel de charting — jamais le contenu créatif) associée à une recette qui ne porte que `crop_by_page`, jamais les dimensions ni la palette d'un motif (contenu propre à chaque fichier, même au sein d'un même éditeur — cf. Winter Wreath/Summer Flight vs Botanical Citrus/Cucurbit ci-dessus). Vérifié avec ces deux dernières fixtures, qui obtiennent réellement la même empreinte (même gabarit d'export DMC officiel, motifs différents) : pas de paire synthétique fabriquée pour l'occasion. Rapprochement automatique dans la même tâche de fond que la détection type A/B/C, jamais dans la requête d'upload — deux bugs de performance réels ont été trouvés et corrigés avant la fin du lot : le calcul d'empreinte d'abord synchrone dans la requête, puis, une fois déplacé, encore trop lent (`pdfplumber` reconstruit un layout par glyphe, ~14 s sur la fixture Café Brasserie) et remplacé par PyMuPDF (`get_fonts()`/`get_text()`, sans reclustering géométrique, <0,15 s).

**Lot 7 terminé.** Troisième moteur d'extraction automatique (`backend/app/type_e.py`, type E — catalogues fermés d'images bitmap réutilisées, éditeurs tiers). `POST /api/imports` essaie `detect_type_a`, puis `detect_type_bc`, puis en dernier recours `detect_type_e`. Le type D (photo libre, vision par ordinateur) a été **abandonné avant toute implémentation** — décision actée le 18/09/2026 (`docs/cahier-des-charges.md` §4.4/§13) faute de fichier de référence réel pour le vérifier ; le bouton de prise de photo a été retiré de l'assistant d'import, qui reste par ailleurs universel pour toute image déposée. Page de grille détectée par mesure structurelle (taille d'image dominante et carrée), jamais par position de page supposée. Rapprochement image → couleur DMC par comptage exact de placements (signal primaire, vérifié fiable) plutôt que par couleur perceptuelle seule (repli explicite, signalé incertain) : mesuré nettement moins fiable sur la fixture de référence. Correction mesurée en cours de route : le catalogue d'images de cette fixture contient réellement 20 images distinctes, pas ~531 comme documenté avant ce lot.

La chaîne d'installation (`npm install`, `pip install`, `docker compose up --build`) a maintenant tourné pour de vrai — voir `docs/roadmap.md` pour le détail de ce qui a été vérifié.

Voir `docs/roadmap.md` pour la suite.

## Ce que le portage des maquettes a figé

- **Le système de design vit dans `frontend/src/index.css`**, en variables CSS. Le rendu canvas relit ces variables (`readGridTheme`) : ne jamais écrire une couleur de thème en dur dans du JavaScript.
- **Les maquettes chargeaient Caprasimo et Figtree depuis Google Fonts.** Remplacées par des piles système, parce qu'une instance auto-hébergée ne doit dépendre d'aucun service tiers ni cesser de fonctionner hors ligne. Pour retrouver la typographie d'origine, auto-héberger les `.woff2` (procédure dans `frontend/README.md`).
- **Les maquettes distinguaient iPhone et iPad par une propriété ; l'application suit la largeur disponible** (`useWideLayout`, seuil 768 px), pour que le Split View d'un iPad soit traité comme l'écran étroit qu'il est.
- **Aucune chaîne en dur dans un composant.** Ajouter une clé dans `src/i18n/fr.ts` casse la compilation tant que `en.ts` n'est pas complété : c'est le garde-fou qui empêche une traduction de manquer en silence.
