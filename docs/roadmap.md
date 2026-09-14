# Roadmap — CrossStitchHelper

*Extrait actionnable de `docs/cahier-des-charges.md` §11. Ce fichier est celui qu'on coche au fil de l'avancement ; le cahier des charges reste la version narrative de référence — en cas de divergence, c'est lui qui fait foi sur le fond, ce fichier sur le séquencement.*

Chaque lot est indépendamment livrable et utilisable : il n'y a pas de lot "inutile tant que le suivant n'est pas fini". Les lots 0 à 3 forment la V1 utilisable. Les lots 4 et 5 forment la V2 différenciante. Les lots 6 à 8 sont des amplificateurs.

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

- [ ] Modèle de données complet (`patterns`, `palette_entries`, `grids`, `progress`, `progress_events`)
- [x] Rendu `<canvas>` avec ses trois niveaux de détail (aplats / couleur+trame / couleur+symbole+quadrillage)
- [x] Marquage des cases (tap, glisser, sélection rectangulaire, "toute cette couleur dans la zone visible" via le filtre couleur + remplissage de zone)
- [ ] Pan/zoom tactile fluide (Pointer Events) — *déplacement au glissé et zoom par boutons faits ; **le pincement à deux doigts reste à implémenter***
- [ ] Synchronisation par deltas versionnés
- [ ] Cache hors-ligne (IndexedDB via Dexie)
- [ ] Grille de démonstration de 255 × 180 injectée directement en base pour les tests de perf — *le motif de démonstration actuel fait 140 × 100 et vit côté client (`frontend/src/demo/`)*

> L'interface complète des cinq écrans est en place depuis le Lot 0 (portage des maquettes). Ce qui manque ici est la **persistance** : aujourd'hui la progression vit en mémoire dans l'onglet et disparaît au rechargement.

**Terminé quand :** on peut cocher des cases sur 45 900 cases avec un pan/zoom fluide sur iPhone, hors-ligne, et retrouver sa progression après rechargement et sur un autre appareil.

**⚠️ Lot le plus risqué techniquement — placé tôt délibérément. Ne pas commencer le Lot 2 avant que la fluidité soit validée sur un appareil réel, pas seulement en simulateur.**

---

## Lot 2 — Import assisté universel (type D)

- [ ] Assistant : dépôt de fichier (PDF ou photo) — *l'écran existe et se parcourt, mais aucun fichier n'est encore lu*
- [ ] Aperçu de la page et recadrage manuel de la grille — *les poignées de recadrage fonctionnent sur un aperçu de démonstration*
- [ ] Calibrage manuel des dimensions (colonnes/lignes)
- [ ] Saisie manuelle de la palette et remplissage des couleurs par zone — *l'éditeur de légende existe (téléphone et tablette)*
- [ ] Export `.cshp` (format ouvert documenté)

**Terminé quand :** n'importe quel PDF ou photo peut être transformé en motif suivable, entièrement à la main. À ce stade, l'application est déjà une alternative crédible à Pattern Keeper.

---

## Lot 3 — Statistiques et confort de suivi

- [ ] Statistiques complètes (progression globale/par couleur, écheveaux estimés, historique)
- [ ] Filtrage par couleur (mise en évidence, estompage des autres)
- [ ] Masquage des cases déjà faites
- [ ] Surlignage de la ligne/colonne courante
- [ ] Annulation multi-niveaux

**Terminé quand :** les quatre besoins initiaux (import, suivi, couleur exacte par case, stats) sont couverts, même si l'import reste manuel. **Fin de la V1.**

---

## Lot 4 — Extraction automatique type A

- [ ] Analyse structurelle des PDF (polices, rectangles, caractères, texte)
- [ ] Détection de grille (pavage régulier, pas de grille, dimensions)
- [ ] Parseur de police de symboles embarquée (type Cafe Brasserie)
- [ ] Parseur de légende texte ("Floss Used for…")
- [ ] Assemblage multi-pages par numéros d'axes

**Terminé quand :** le PDF `fixtures/cafe-brasserie-charting-export/` s'importe en validant simplement les propositions, et que les comptages par couleur obtenus correspondent à ceux de sa page 11 (voir `fixtures/README.md`).

---

## Lot 5 — Extraction automatique types B et C

- [ ] Extraction des couleurs par remplissage de rectangles (gestion CMJN/RVB)
- [ ] Rapprochement Lab vers la palette DMC
- [ ] Mesure de la densité de tracés vectoriels par page pour décider si une superposition à deux pages est nécessaire (ne jamais supposer "page 1 = couleur, page 2 = symboles" par défaut — voir `docs/cahier-des-charges.md` §4.3, cas Summer Flight)
- [ ] Superposition des grilles jumelles quand elle s'avère nécessaire
- [ ] Reconnaissance des symboles vectoriels avec score de confiance
- [ ] Repli manuel explicite quand le score est insuffisant

**Terminé quand :** les quatre fixtures DMC (`winter-wreath-dmc`, `botanical-citrus`, `cucurbit`, `summer-flight`) s'importent chacune avec leurs couleurs correctes, la bonne stratégie de page(s) détectée automatiquement, et un signalement explicite des cases incertaines. **Fin de la V2.**

---

## Lot 6 — Recettes réutilisables

- [ ] Calcul d'empreinte de fichier (polices, motifs de texte d'en-tête, géométrie — jamais le contenu créatif)
- [ ] Enregistrement d'une configuration validée comme recette
- [ ] Réapplication automatique sur un fichier de même empreinte
- [ ] Gestion de la bibliothèque locale de recettes

**Terminé quand :** réimporter un second PDF du même éditeur saute directement au récapitulatif.

---

## Lot 7 — Scan, photo et grilles en images réutilisées (types D et E)

**Type D — scan/photo libre :**
- [ ] Détection de grille par vision par ordinateur
- [ ] Correction de perspective
- [ ] Quantification des couleurs par case
- [ ] Classification des symboles
- [ ] Validation manuelle obligatoire des zones à faible confiance

**Type E — grilles composées d'images bitmap réutilisées** (voir `docs/cahier-des-charges.md` §4.3 et §4.4, cas River And Mountains) :
- [ ] Détection et exclusion des pages de prévisualisation photoréaliste (pas des grilles de travail)
- [ ] Extraction du catalogue d'images distinctes réutilisées sur les pages de grille (généralement quelques centaines, pas des milliers)
- [ ] Classification de chaque image du catalogue en (couleur, symbole) — un problème fermé, plus simple que la vision libre du type D
- [ ] Repositionnement de chaque case à partir des placements de ces images

**Terminé quand :** une photo correcte d'une grille papier (type D) et le PDF `fixtures/river-and-mountains/` (type E) produisent chacun une proposition exploitable, l'utilisateur n'ayant plus qu'à corriger les erreurs signalées.

---

## Lot 8 — Finitions

- [ ] Points fractionnés et spéciaux complets dans l'interface (quart, demi, point arrière, point de nœud, perles)
- [ ] Sauvegarde/restauration des données
- [ ] Thème sombre
- [ ] Traductions FR/EN complètes
- [ ] Partage communautaire des recettes (éventuel, sous conditions strictes — voir cahier des charges §8.7)

---

## Décisions encore ouvertes (à trancher avant certains lots)

- Licence open source (MIT vs AGPL) — à trancher avant toute publication publique, indépendamment des lots.
- Partage communautaire des recettes (Lot 8) — sous conditions légales strictes à définir.
