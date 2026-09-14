# CLAUDE.md — guide pour travailler sur CrossStitchHelper

Ce fichier est le point d'entrée pour toute session Claude Code travaillant sur ce dépôt. Lis-le avant de commencer, et relis `docs/cahier-des-charges.md` avant toute décision d'architecture non couverte ici.

## En une phrase

CrossStitchHelper est une webapp (PWA) gratuite, open source et **auto-hébergée** qui transforme un PDF (ou une photo) de grille de point de croix en motif suivable, avec cochage des cases, couleur exacte par case et statistiques. Cible principale : iPhone/iPad via Safari.

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

Six PDF réels servent de vérité terrain pour tout le moteur d'extraction, couvrant les cinq types A/B/C/D/E de `docs/cahier-des-charges.md` §4.4. Toute modification du parseur doit être vérifiée contre ces valeurs connues avant d'être considérée correcte — détail complet dans `fixtures/README.md`.

- **`cafe-brasserie-charting-export/` — type A.** Police embarquée personnalisée (un glyphe = un symbole), légende texte complète. Dimensions attendues : 255 × 180 cases, 34 couleurs, comptages exacts par couleur en page 11.
- **`winter-wreath-dmc/`, `botanical-citrus-dmc/`, `cucurbit-dmc/` — type C, superposition nette.** Trois grilles DMC où la page couleur a peu de tracés vectoriels et la page symboles en a beaucoup — la séparation en deux pages est fiable.
- **`summer-flight-dmc/` — type C, cas piège.** Même gabarit visuel DMC, mais **les deux pages contiennent déjà beaucoup de tracés vectoriels** : ne jamais supposer "page 1 = couleur seule" sans mesurer la densité de tracés par page d'abord. Ce fichier doit faire échouer un connecteur qui ferait cette hypothèse aveuglément.
- **`river-and-mountains-laserarts/` — type E.** Éditeur tiers, structure entièrement différente : la grille est composée d'environ 531 petites images bitmap réutilisées (couleur + symbole déjà combinés dans chaque image), pas de rectangles colorés ni de tracés vectoriels. La page 1 est une prévisualisation photoréaliste à exclure de l'extraction, pas une grille de travail.

**Enseignement à retenir :** même au sein d'un seul éditeur (DMC) et d'un gabarit visuel identique, la structure interne varie d'un fichier à l'autre (`summer-flight-dmc` vs les trois autres fixtures DMC). Ne jamais coder une heuristique d'extraction qui suppose une structure fixe sans la vérifier sur le fichier en cours — toujours mesurer avant de décider.

Avant de considérer une évolution du moteur d'extraction comme terminée, exécuter la procédure du skill `verify-extraction-fixtures` (voir `.claude/skills/`).

## Conventions de code

- **Backend** : Python 3.12, FastAPI, `pdfplumber`/`PyMuPDF` pour l'extraction, SQLAlchemy + Alembic pour la base, typage strict (mypy propre), tests avec `pytest`.
- **Frontend** : TypeScript strict, React, rendu de grille en `<canvas>` écrit à la main (pas de dépendance lourde de grille virtualisée générique — la logique de niveaux de détail est spécifique au domaine).
- **Chaînes utilisateur** : toujours passer par les clés i18n (français + anglais dès le départ), jamais de texte en dur dans les composants.
- **Commits** : messages en français ou anglais au choix, mais cohérents dans un même lot ; référencer le numéro de lot du `docs/roadmap.md` quand c'est pertinent.
- **Tests** : toute fonctionnalité touchant à l'extraction ou au modèle de données de grille doit avoir un test utilisant les fixtures ci-dessus.

## Statut actuel

**Lots 0 et 1 terminés.** Le backend FastAPI + SQLite + Alembic, le frontend PWA React/TypeScript, l'image Docker unique, la CI et le README d'auto-hébergement sont en place. Les cinq écrans des maquettes sont implémentés et le suivi est réellement interactif (cochage, déplacement, zoom dont le pincement à deux doigts, filtre par couleur, sélection de zone, annulation), persisté en base et synchronisé entre appareils par deltas versionnés (`backend/app/api/patterns.py`), avec repli hors-ligne sur IndexedDB (`frontend/src/state/useSyncedTracker.ts`). **Aucun appareil iOS physique n'est disponible dans cet environnement de développement** (contrainte durable) : le pan/pincement est validé par événements tactiles réels rejoués dans un navigateur de bureau, pas sur un vrai iPhone — voir `docs/roadmap.md` Lot 1 pour le détail exact de ce que ça couvre et ne couvre pas.

**Lot 2 terminé.** L'assistant d'import (`backend/app/api/imports.py`, `frontend/src/screens/ImportScreen.tsx`) lit vraiment le fichier déposé : aperçu raster réel, cadrage, dimensions, palette et peinture par zone à la main (`frontend/src/components/ImportGridPainter.tsx`, réutilise le rendu canvas du suivi), jusqu'à un motif réellement suivable. Aucune détection automatique — ça reste les Lots 4 à 7. Export `.cshp` disponible depuis l'écran Statistiques. `frontend/src/demo/` reste utile au-delà de ça : c'est le repli hors-ligne de premier lancement quand ni le serveur ni le cache IndexedDB n'ont encore de motif.

La chaîne d'installation (`npm install`, `pip install`, `docker compose up --build`) a maintenant tourné pour de vrai — voir `docs/roadmap.md` pour le détail de ce qui a été vérifié.

Voir `docs/roadmap.md` pour la suite.

## Ce que le portage des maquettes a figé

- **Le système de design vit dans `frontend/src/index.css`**, en variables CSS. Le rendu canvas relit ces variables (`readGridTheme`) : ne jamais écrire une couleur de thème en dur dans du JavaScript.
- **Les maquettes chargeaient Caprasimo et Figtree depuis Google Fonts.** Remplacées par des piles système, parce qu'une instance auto-hébergée ne doit dépendre d'aucun service tiers ni cesser de fonctionner hors ligne. Pour retrouver la typographie d'origine, auto-héberger les `.woff2` (procédure dans `frontend/README.md`).
- **Les maquettes distinguaient iPhone et iPad par une propriété ; l'application suit la largeur disponible** (`useWideLayout`, seuil 768 px), pour que le Split View d'un iPad soit traité comme l'écran étroit qu'il est.
- **Aucune chaîne en dur dans un composant.** Ajouter une clé dans `src/i18n/fr.ts` casse la compilation tant que `en.ts` n'est pas complété : c'est le garde-fou qui empêche une traduction de manquer en silence.
