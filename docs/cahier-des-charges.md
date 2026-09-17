# Cahier des charges — CrossStitchHelper

*Version 1.0 — 13/09/2026. Ce document remplace la note de discovery initiale : il en conserve tous les constats actionnables et les transforme en spécifications de réalisation. Il sert de référence pour construire l'application.*

---

## 1. Objectif

CrossStitchHelper est une application web gratuite et open source, auto-hébergeable, qui permet à un·e brodeur·se de :

1. **importer** une grille de point de croix au format PDF (ou image) et la convertir en données structurées exploitables ("fichier machine") ;
2. **suivre sa progression** en cochant les cases au fur et à mesure de la broderie ;
3. **savoir exactement quelle couleur va dans quelle case**, avec un repérage fiable ligne par ligne ;
4. **consulter des statistiques** de progression et de consommation de fil.

Le produit vise l'usage réel sur **iPhone et iPad** (broderie en main, téléphone à côté), sans passer par l'App Store.

### Positionnement

L'équivalent commercial le plus proche est Markup R-XP (payant, fermé, ~15 £/an), qui revendique une détection automatique des symboles et couleurs sans documentation publique sur sa fiabilité. Pattern Keeper, la référence gratuite, ne détecte rien : l'utilisateur aligne lui-même une grille et lit les couleurs à l'œil sur le PDF d'origine.

CrossStitchHelper se différencie par un **import semi-automatique transparent** : l'application pré-remplit tout ce qu'elle sait deviner, et l'utilisateur corrige ce qui ne va pas dans un assistant en étapes. Ni boîte noire, ni corvée manuelle. Une application tierce disparue (Cross Stitch Markup) fournit la leçon inverse à ne pas répéter : elle dépendait d'un format propriétaire `.chart` introuvable — il faut accepter le fichier que l'utilisateur a réellement entre les mains.

---

## 2. Périmètre

### 2.1 Inclus

| Domaine | Contenu |
|---|---|
| Import | PDF vectoriel (export logiciel et publication éditoriale), image/scan en mode assisté, assistant de correction en étapes, assemblage multi-pages |
| Grille | Points entiers, demi-points, quarts de point, points arrière, points de nœud, perles |
| Suivi | Cochage case par case, par zone, par couleur ; annulation ; reprise multi-appareils |
| Couleurs | Palette DMC (codes, noms, RVB approché), correspondance symbole → fil, filtrage par couleur |
| Statistiques | Progression globale et par couleur, points restants, estimation d'écheveaux, historique |
| Déploiement | Auto-hébergement en une commande (`docker compose up`), données chez l'utilisateur |

### 2.2 Exclu (explicitement hors périmètre)

- **Création** de motifs (conversion photo → grille) : c'est le métier de Stitch Fiddle et consorts, pas le nôtre.
- **Bibliothèque partagée de motifs** : aucun motif n'est distribué, stocké côté tiers ou partagé entre utilisateurs (cf. §3.3).
- **Applications natives** iOS/Android : écartées volontairement (compte développeur Apple payant, contraire à l'objectif gratuit).
- **Multi-utilisateurs avec comptes et permissions** : hors V1. Le modèle de données ne doit pas l'interdire pour autant.
- **Marketplace, paiement, publicité** : aucun.

---

## 3. Contraintes structurantes

### 3.1 Contraintes techniques

- **Tout self-hosted et local.** Aucune dépendance à un service tiers (pas de cloud propriétaire, pas d'API externe obligatoire). L'instance tourne chez l'utilisateur : NAS, Raspberry Pi, machine perso, petit VPS.
- **Le calcul lourd est côté serveur.** L'extraction PDF et, plus tard, la vision par ordinateur s'exécutent sur le backend — c'est la raison d'être de l'architecture frontend + backend retenue : ne pas faire ramer un iPhone avec du parsing de PDF ou de l'OCR.
- **Le client doit rester utilisable hors-ligne** pour la partie suivi : une fois un motif chargé, cocher des cases ne doit exiger aucun réseau.
- **Installation en une commande.** Pas de Redis, pas de Postgres, pas de broker à administrer : un conteneur applicatif et un volume de données.

### 3.2 Contraintes de plateforme

- Cible principale : **Safari sur iPhone et iPad**, installée en **PWA** ("Ajouter à l'écran d'accueil") — plein écran, icône, hors-ligne, sans App Store.
- Le stockage navigateur (IndexedDB) est traité comme un **cache**, jamais comme la source de vérité : Safari applique une politique d'éviction des données de site après inactivité, et le comportement a varié selon les versions d'iOS. La source de vérité est la base du serveur auto-hébergé.
- L'import d'une photo de grille papier passe par un simple `<input type="file" accept="image/*" capture>`, sans app native.
- L'accès depuis l'extérieur du réseau local (tunnel type Tailscale/WireGuard, ou reverse proxy HTTPS) est un sujet de **documentation**, pas de code applicatif.

### 3.3 Contraintes juridiques

Une grille de point de croix est une œuvre protégée. L'application est un **outil de suivi personnel** : l'utilisateur importe des fichiers qu'il possède déjà.

- Aucun motif importé n'est partagé entre utilisateurs ni envoyé à un tiers.
- Le PDF source n'est pas conservé au-delà de l'import (option de suppression automatique après extraction, activée par défaut).
- Les "recettes" d'import réutilisables (§8.7) ne contiennent **que des paramètres géométriques et structurels** — jamais le contenu créatif du motif.
- Les tables de correspondance DMC → RVB utilisées sont des données communautaires non officielles : à créditer comme telles, et à présenter dans l'interface comme une approximation.
- Les conditions d'utilisation doivent énoncer que l'application ne fournit aucun motif.

---

## 4. Constats techniques d'entrée

Six PDF réels ont été analysés en profondeur (structure interne, polices, tracés vectoriels, couleurs de remplissage, images embarquées). Ils sont visuellement semblables et **internement très différents**. C'est le constat qui conditionne toute la conception du moteur d'extraction.

### 4.1 PDF « Winter Wreath » (DMC officiel, 5 pages)

- Grille dessinée en **~6 800 rectangles vectoriels par page**, chacun portant sa couleur de remplissage → **la couleur de chaque case est extractible sans OCR**.
- Les symboles (T, Z, U…) sont des **tracés vectoriels** (~3 300–3 700 lignes/courbes par page), **pas du texte** → illisibles par extraction de texte, nécessitent une reconnaissance de forme.
- Motif réparti sur **deux grilles jumelles visuellement semblables**, mêmes dimensions : à l'œil, page 1 = couleurs, page 2 = symboles en noir et blanc. **Correction Lot 5, mesurée et non supposée (`backend/app/type_bc.py`) :** la page 1 porte en réalité déjà ses propres petits tracés de symbole par-dessus chaque aplat de couleur (~3 362 courbes mesurées, réparties sur toute la grille, pas un simple ornement localisé — confirmé par rendu visuel d'un symbole extrait) ; la page 2 (tout en noir, ~2 466 courbes) n'est donc qu'un doublon redondant, pas la seule source de symboles exploitable. Ce fichier se comporte en pratique comme le cas piège `summer-flight-dmc` (§4.3) plutôt que comme `botanical-citrus-dmc`/`cucurbit-dmc`, qui superposent vraiment deux pages — **la leçon du §4.3 s'applique donc aussi à ce fichier lui-même : ne jamais supposer sans mesurer, même ici.**
- Légende page 4 : codes DMC en texte (3345, 3346, 471…), pastilles de couleur en aplats.
- Aucune image bitmap : 100 % vectoriel.

### 4.2 PDF « Cafe Brasserie » (export de logiciel de charting, 11 pages)

- Chaque symbole est un **caractère d'une police embarquée personnalisée (`CROSSSTICH6`)**, positionné case par case → **du texte réel, directement extractible**.
- Légende texte complète et non ambiguë (pages 9–11) : symbole, brins, code DMC, nom, et **comptage exact des points par couleur** (ex. DMC 310 = 3 839 points entiers).
- Dimensions annoncées en clair : **255 × 180 points = 45 900 cases**, tailles en cm pour toiles 14/16/18.
- Tableaux séparés pour points entiers, demis, quarts, nœuds, points arrière.
- Numéros de colonnes et de lignes imprimés en marge de chaque page de grille (10, 20, 30…) → **repère fiable pour l'assemblage multi-pages automatique**.

### 4.3 Quatre échantillons supplémentaires (élargissement de la base de test)

Quatre PDF additionnels ont été analysés pour vérifier si la typologie A/B/C/D tenait sur un échantillon plus large. Trois viennent du même éditeur (DMC) que Winter Wreath, un vient d'un éditeur totalement différent.

**« Botanical Citrus » et « Cucurbit »** (DMC, 4 pages chacun) — même gabarit visuel que Winter Wreath, et confirment le schéma type C : sur les deux, la page couleur a très peu de tracés vectoriels (103 et 31 courbes) tandis que la page symboles en a beaucoup (1981 et 1072) — la séparation couleur/symbole entre les deux pages est nette et fiable.

**« Summer Flight / Envolée estivale »** (DMC, 5 pages) — même gabarit visuel, mais **la séparation n'est pas la même** : sa page 1 (couleur) contient déjà énormément de tracés vectoriels (2220 courbes, autant que la page symboles habituelle), signe que les symboles y sont probablement déjà dessinés sur la page couleur elle-même, et la page 2 n'est qu'un doublon noir et blanc redondant plutôt qu'une source de symboles indispensable. **Conséquence directe pour le moteur d'extraction : même au sein d'un seul éditeur (DMC) et d'un même gabarit visuel, la relation entre les pages n'est pas garantie identique d'un motif à l'autre.** Le connecteur type C ne doit jamais supposer aveuglément "page 1 = couleur seule, page 2 = symboles" : il doit mesurer la densité de tracés vectoriels de chaque page candidate avant de décider si une superposition à deux pages est réellement nécessaire, ou si une seule page suffit déjà.

**« River And Mountains »** (éditeur tiers, LaserArtsDesigns, 18 pages) — structure radicalement différente des PDF DMC, et qui **ne rentre dans aucun des quatre types existants** :
- La page 1 est une image de prévisualisation photoréaliste de l'ouvrage terminé (pas une grille de travail) — un cas à détecter et écarter avant même de chercher une grille.
- Les pages de grille (à partir de la page 2) ne sont ni du texte, ni des rectangles vectoriels colorés, ni des tracés vectoriels : ce sont des **milliers de petites images bitmap réutilisées** (531 images distinctes de 48×48/64×64 px, chacune combinant déjà une couleur de fond et une icône de symbole, placées des dizaines de milliers de fois pour composer la grille).
- La couleur et le symbole d'une case sont donc obtenus en identifiant **quelle image parmi les ~531 réutilisées** est placée à cette position — un problème de classification d'image sur un petit catalogue fermé d'icônes, très différent à la fois de la lecture d'un remplissage vectoriel (type B/C) et de la vision par ordinateur en plein cadre sur une photo libre (type D).

Ce dernier cas justifie l'ajout d'un **type E** à la typologie (§4.4) : les grilles composées d'images bitmap réutilisées, ni purement vectorielles ni des photos libres.

### 4.4 Typologie retenue pour le moteur d'extraction

| Type | Description | Couleur | Symbole | Exemple |
|---|---|---|---|---|
| **A** | Export logiciel structuré : police de symboles embarquée + légende texte | Auto | Auto | Cafe Brasserie |
| **B** | Vectoriel éditorial, couleur seule (symboles ignorés ou absents de la page) | Auto | Non traité | DMC, magazines |
| **C** | Une ou deux grilles vectorielles à couleur + symboles, densité de tracés à mesurer par page pour savoir si une superposition est nécessaire | Auto | Reconnaissance de forme | DMC Winter Wreath, Botanical Citrus, Cucurbit, Summer Flight |
| **D** | Image / scan / photo libre | Assisté puis auto (V3) | Assisté puis auto (V3) | Grille papier photographiée |
| **E** | Grille composée de petites images bitmap réutilisées (catalogue fermé d'icônes couleur+symbole) | Auto (classification d'image sur catalogue fermé) | Auto (idem) | River And Mountains |

**Conséquence de conception majeure :** aucun parseur universel n'est possible, et cette diversité s'observe **même à l'intérieur d'un seul éditeur** (§4.3). L'auto-détection n'a pas besoin d'être parfaite — elle doit produire une **bonne proposition de départ** que l'utilisateur corrige. Le type D en mode assisté est le **filet de sécurité universel** : il fonctionne sur n'importe quel fichier, et égale au minimum ce que fait Pattern Keeper aujourd'hui. Le type E, bien que nouveau, reste hors du périmètre du Lot 5 (types B/C) — voir `docs/roadmap.md` pour son positionnement.

---

## 5. Architecture technique

### 5.1 Vue d'ensemble

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  PWA React (iPhone/iPad)    │  HTTPS  │  Backend FastAPI (Python)    │
│  - assistant d'import       │ ◄─────► │  - analyse structurelle PDF  │
│  - rendu grille <canvas>    │  JSON   │  - moteurs d'extraction A/B/C│
│  - suivi hors-ligne         │  +blob  │  - vision (D, V3)            │
│  - cache IndexedDB          │         │  - stats, recettes           │
└─────────────────────────────┘         └──────────────┬───────────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │ SQLite + volume │
                                              └─────────────────┘
```

### 5.2 Backend

- **Python 3.12 + FastAPI** (API REST, documentation OpenAPI automatique).
- **Extraction PDF : `pdfplumber` (structure : rectangles, couleurs, caractères, polices) + `PyMuPDF` (rendu d'aperçus raster, performances)** — les deux ont été validés concrètement sur les deux PDF de test.
- **Vision (lot 7 uniquement) : `opencv-python-headless` + `numpy`.**
- **SQLite + SQLAlchemy + Alembic** (migrations). Pas de serveur de base séparé.
- **Tâches longues : `BackgroundTasks` FastAPI + table de jobs en base**, interrogée par le client. Volontairement pas de Celery/Redis : un service de moins à auto-héberger.
- **Authentification V1** : instance mono-utilisateur, mot de passe unique optionnel (variable d'environnement) protégeant toute l'API. Le modèle de données prévoit un `owner_id` nullable pour ne pas fermer la porte au multi-utilisateurs.

### 5.3 Frontend

- **React + TypeScript + Vite**, PWA via `vite-plugin-pwa` (manifest + service worker).
- **Rendu de grille : `<canvas>` 2D écrit à la main** (pas de composant DOM par case), avec repli WebGL/PixiJS envisageable si nécessaire.
- **État serveur : TanStack Query.** **État local : Zustand.** **Cache hors-ligne : IndexedDB via Dexie.**
- **Interactions tactiles : Pointer Events** (pinch-zoom, pan, tap, glisser-peindre), sans dépendre de comportements Safari spécifiques.

### 5.4 Déploiement

- Une image Docker unique (backend servant aussi les fichiers statiques du frontend construit), plus un `docker-compose.yml` d'exemple avec un volume pour `data/` (base SQLite + fichiers).
- Variables d'environnement : port, mot de passe optionnel, rétention des PDF sources, chemin des données.
- Un `README` couvrant : installation, mise à jour, sauvegarde du volume, accès distant via tunnel personnel.

---

## 6. Modèle de données

### 6.1 Principe directeur

Une grille de 45 900 cases n'est **jamais** stockée à raison d'une ligne par case : elle est lue comme un tout, jamais interrogée case par case. Elle est donc stockée **compactée**, et la progression est stockée comme un **bitmap** (1 bit par case ≈ 5,7 ko pour 45 900 cases).

Corollaire indispensable : **la progression est stockée séparément de la grille**, pour pouvoir ré-importer ou corriger un motif sans perdre le travail de suivi déjà effectué.

### 6.2 Tables

```sql
patterns (
  id, owner_id NULL, name, source_filename, source_sha256,
  width, height, fabric_count, created_at, updated_at,
  import_config_json,        -- configuration validée dans l'assistant
  recipe_id NULL,
  notes
)

palette_entries (
  id, pattern_id, index_in_grid,    -- index utilisé dans le blob de grille
  brand, code, name, rgb_hex,
  symbol_key, symbol_svg NULL,      -- rendu vectoriel du symbole si disponible
  strands_full, strands_back,
  count_full, count_half, count_quarter, count_french, count_beads,
  backstitch_length_cm
)

grids (
  pattern_id PRIMARY KEY,
  layer_full BLOB,        -- Uint16Array w*h, 0 = case vide, n = index palette
  layer_half BLOB NULL,
  layer_quarter BLOB NULL,
  backstitch_json,        -- [{x1,y1,x2,y2,palette_index}]
  french_knots_json,      -- [{x,y,palette_index}]
  encoding, version
)

progress (
  pattern_id PRIMARY KEY,
  bitmap BLOB,            -- 1 bit par case
  version INTEGER,        -- incrémenté à chaque delta appliqué
  stitched_count, updated_at
)

progress_events (
  id, pattern_id, ts, ops_json, version_after
)                         -- journal pour annulation et reprise multi-appareils

recipes (
  id, fingerprint, label, grid_type, config_json,
  created_at, usage_count
)

import_jobs (
  id, status, kind, pattern_id NULL, progress_pct,
  result_json, error, created_at, finished_at
)
```

### 6.3 Format d'échange de la grille

Le blob de grille est transmis au client en `Uint16Array` encodé base64, compressé par la couche HTTP (gzip/brotli). Ordre de parcours : ligne par ligne, de gauche à droite, de haut en bas.

Pour 255 × 180 : 91,8 ko bruts, typiquement 10–20 ko compressés. Aucun besoin de pagination.

### 6.4 Format « fichier machine » exportable

Un export ouvert et documenté doit être disponible dès le lot 2, pour que l'utilisateur ne soit jamais captif de l'application (leçon de Cross Stitch Markup) : archive `.cshp` (ZIP) contenant `pattern.json` (métadonnées + palette + segments), `grid.bin` (les couches), `progress.bin`, et un `README.txt` décrivant le format.

---

## 7. Spécifications fonctionnelles

### 7.1 Bibliothèque de projets

Écran d'accueil : liste des motifs importés avec vignette, dimensions, avancement en pourcentage, date de dernière activité. Actions : ouvrir, renommer, dupliquer, exporter, supprimer, importer un nouveau motif.

### 7.2 Assistant d'import

Parcours en étapes, chacune pré-remplie automatiquement et modifiable, avec navigation avant/arrière sans perte de saisie.

**Étape 1 — Dépôt du fichier.** PDF ou image, par sélection ou glisser-déposer, avec accès direct à l'appareil photo sur mobile. Le fichier est envoyé au serveur ; un job d'analyse démarre.

**Étape 2 — Analyse automatique.** Le serveur calcule l'empreinte du fichier et cherche une recette connue (§8.7). Si elle existe, toutes les étapes suivantes sont pré-remplies et l'utilisateur peut aller directement au récapitulatif. Sinon, il produit ses meilleures estimations : nature de chaque page, zone de grille probable, pas de la grille, dimensions en cases, légende candidate, indices de pagination, détection de grilles jumelles.

**Étape 3 — Recadrage.** Aperçu raster de la page avec un cadre proposé, ajustable par poignées sur les quatre bords, zoom pour le réglage fin. Objectif : exclure marges, titres, légendes intercalées, ou corriger une détection imprécise.

**Étape 4 — Type de grille.** Choix dans la liste fermée A / B / C / D (§4.4), pré-sélectionné par la détection, avec une description courte et honnête des conséquences de chaque choix (notamment : en type B, les symboles sont ignorés et deux nuances très proches peuvent être confondues). Le type E (§4.4) n'est pas encore proposé comme choix à l'utilisateur en V1 — voir `docs/roadmap.md`.

**Étape 5 — Association des grilles jumelles** (type C uniquement). Désignation ou confirmation de la page/zone « couleur » et de la page/zone « symboles », avec un réglage fin de recalage si la superposition n'est pas exacte.

**Étape 6 — Dimensions.** Nombre de colonnes et de lignes proposé automatiquement, éditable. Quand le PDF annonce ses dimensions en clair (cas Cafe Brasserie : « 255w x 180h stitches »), cette valeur est proposée en priorité et signalée comme telle.

**Étape 7 — Légende.** Tableau éditable de la correspondance symbole/couleur → fil : ajout d'une entrée manquante, correction d'un code, fusion de deux entrées détectées à tort comme distinctes, choix de la marque (DMC par défaut). Chaque ligne affiche la couleur détectée à côté de la couleur théorique du fil, pour rendre visible tout rapprochement douteux.

**Étape 8 — Pages multiples.** Mosaïque d'assemblage proposée automatiquement (à partir des numéros d'axes et des mentions « 1/5 »), réorganisable par glisser-déposer, avec visualisation des zones de chevauchement.

**Étape 9 — Récapitulatif.** Aperçu de la grille reconstituée, indicateurs de confiance (nombre de cases non attribuées, couleurs rapprochées de justesse), enregistrement du motif, et proposition d'enregistrer la configuration comme recette réutilisable.

### 7.3 Écran de suivi

C'est l'écran le plus utilisé, et le plus exigeant techniquement.

- **Navigation** : pan et pinch-zoom fluides, saut à une coordonnée, minimap de position.
- **Trois niveaux de détail** selon le zoom : aplats de couleur seuls en vue éloignée, couleur + trame en vue moyenne, couleur + symbole + quadrillage décimal en vue rapprochée.
- **Marquage** : tap sur une case, glisser pour marquer une série, sélection rectangulaire, « marquer toute cette couleur dans la zone visible ». Annulation multi-niveaux.
- **Mise en évidence** : filtrer sur une couleur (les autres sont estompées), masquer les cases déjà faites, surligner la ligne et la colonne courantes — c'est la réponse directe au besoin « savoir quelle couleur pour quelle case avec des lignes exactes ».
- **Repères** : quadrillage tous les 10 points, numéros de lignes et colonnes en marge, marqueur de centre.
- **Hors-ligne** : toute cette interaction fonctionne sans réseau, les modifications sont mises en file et synchronisées au retour de la connexion.

### 7.4 Statistiques

Progression globale et par couleur (faits / restants / pourcentage), nombre de points par type (entiers, demis, quarts, nœuds, longueur de point arrière), estimation des écheveaux nécessaires et restants selon la toile et le nombre de brins, historique d'activité et rythme moyen. Quand le PDF fournit lui-même les comptages (cas Cafe Brasserie), ils sont utilisés pour vérifier l'extraction et tout écart est signalé.

### 7.5 Réglages

Marque de fil par défaut, toile par défaut, rétention ou suppression des PDF sources, thème clair/sombre, langue (français et anglais), sauvegarde et restauration des données.

---

## 8. Moteur d'extraction (backend)

### 8.1 Analyse structurelle

Pour chaque page : comptage et géométrie des rectangles, des tracés, des caractères ; polices embarquées et leurs noms ; images bitmap présentes ; texte extractible. Classification en page de grille, page de légende, page d'instructions, page raster.

### 8.2 Détection de grille

Recherche du plus grand pavage régulier de rectangles (ou de caractères) de dimensions homogènes. Le pas de grille est déduit de l'écart médian entre éléments adjacents sur chaque axe ; les dimensions en cases se déduisent du rapport entre l'étendue de la zone et le pas. Résultat : une boîte englobante et un couple (colonnes, lignes) proposés à l'utilisateur, jamais imposés.

### 8.3 Parseur type A

Détection d'une police embarquée servant de police de symboles (nombreux glyphes répétés en pavage régulier). Chaque caractère devient une case, sa position dans la grille se déduisant du pas détecté. La légende texte est parsée pour obtenir la table symbole → code fil (repères : « Floss Used for », colonnes Symbol / Strands / Type / Number / Color). La couleur de fond du rectangle sous-jacent sert de vérification croisée.

### 8.4 Parseur types B et C

La couleur de chaque case est lue dans la couleur de remplissage de son rectangle, convertie en RVB (attention aux espaces CMJN). En type C, la grille de symboles est superposée à la grille de couleurs après recalage ; la reconnaissance des symboles vectoriels se fait par comparaison des tracés d'une case avec les tracés des symboles de la légende (normalisation puis appariement de formes), avec un score de confiance et un repli manuel quand le score est insuffisant.

### 8.5 Rapprochement couleur → fil

Conversion RVB → Lab et recherche du plus proche voisin dans la table de la marque, avec un score de distance. Toute correspondance au-delà d'un seuil est signalée à l'utilisateur à l'étape 7 de l'assistant. Lorsque la légende fournit les codes en texte, ils font foi et le rapprochement ne sert qu'à associer chaque couleur de grille à la bonne entrée de légende.

### 8.6 Assemblage multi-pages

Priorité aux numéros d'axes imprimés en marge, qui donnent la position absolue de chaque page dans la grille globale (mécanisme observé sur le PDF Cafe Brasserie). À défaut, appariement par corrélation des bandes de chevauchement. Les zones de recouvrement sont dédupliquées et toute incohérence entre deux pages est signalée.

### 8.7 Recettes réutilisables

Une empreinte est calculée à partir de la structure du fichier — polices embarquées, motifs de texte d'en-tête, géométrie de mise en page — **et jamais à partir du contenu créatif**. Après validation d'un import, la configuration peut être enregistrée comme recette associée à cette empreinte. Un fichier ultérieur de même empreinte (même éditeur, même logiciel, même boutique) est alors pré-configuré automatiquement.

Cette bibliothèque est locale en V2. Un partage communautaire, limité aux paramètres géométriques et structurels, est envisageable ensuite : c'est ce qui permet de résorber progressivement le problème d'hétérogénéité des formats sans coder un connecteur par éditeur.

---

## 9. API

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/imports` | Envoi du fichier, création du job d'analyse |
| GET | `/api/imports/{id}` | État du job et résultat d'analyse |
| GET | `/api/imports/{id}/pages/{n}/preview` | Aperçu raster d'une page (paramètre de résolution) |
| PATCH | `/api/imports/{id}/config` | Mise à jour de la configuration de l'assistant |
| POST | `/api/imports/{id}/extract` | Extraction d'essai avec la configuration courante |
| POST | `/api/imports/{id}/commit` | Création du motif définitif |
| GET | `/api/patterns` | Liste des motifs |
| GET | `/api/patterns/{id}` | Métadonnées et palette |
| GET | `/api/patterns/{id}/grid` | Couches de grille (blob compact) |
| GET | `/api/patterns/{id}/progress` | Bitmap de progression et version |
| POST | `/api/patterns/{id}/progress` | Application d'un lot de modifications (avec version pour la détection de conflit) |
| GET | `/api/patterns/{id}/stats` | Statistiques calculées |
| GET | `/api/patterns/{id}/export` | Export `.cshp` |
| GET/POST/DELETE | `/api/recipes` | Bibliothèque de recettes |

La synchronisation de progression fonctionne par **deltas versionnés** : le client envoie les cases modifiées avec la version qu'il connaît ; en cas de divergence, le serveur renvoie les opérations manquantes et le client rejoue. Cocher une case est une opération idempotente, ce qui rend les conflits triviaux à résoudre.

---

## 10. Exigences non fonctionnelles

- **Performance** : pan et zoom fluides (cible 60 images/s, plancher acceptable 30) sur un motif de 45 900 cases, sur iPhone réel — pas seulement sur simulateur de bureau. Chargement d'un motif en moins de 2 secondes sur réseau local.
- **Extraction** : analyse d'un PDF de 10 pages en moins de 30 secondes, avec avancement affiché.
- **Hors-ligne** : suivi pleinement fonctionnel sans réseau sur les motifs déjà ouverts ; synchronisation automatique au retour.
- **Robustesse** : aucun import ne doit aboutir à une impasse — le mode assisté du type D reste toujours accessible en repli.
- **Accessibilité** : cibles tactiles d'au moins 44 px, contrastes suffisants, interface utilisable d'une seule main sur iPhone.
- **Internationalisation** : français et anglais dès le départ, chaînes externalisées.
- **Tests** : les deux PDF analysés servent de jeu de tests de référence ; toute évolution du moteur d'extraction doit être vérifiée contre les valeurs connues (255 × 180 cases, 34 couleurs, comptages par couleur de la page 11).

---

## 11. Roadmap

Le projet est découpé en lots indépendamment livrables. Chaque lot est utilisable en fin de parcours : il n'y a pas de lot « inutile tant que le suivant n'est pas fini ».

### Lot 0 — Socle technique

Squelette FastAPI + SQLite + Alembic, frontend React/Vite/TypeScript en PWA installable, image Docker unique et `docker-compose.yml`, jeu de tests et intégration continue, `README` d'auto-hébergement.

*Terminé quand :* `docker compose up` donne une application installable sur l'écran d'accueil d'un iPhone, avec une page d'accueil vide et une API qui répond.

### Lot 1 — Noyau de rendu et de suivi

Modèle de données complet, rendu `<canvas>` avec ses trois niveaux de détail, pan/zoom tactile, marquage des cases, synchronisation par deltas versionnés, cache hors-ligne. Testé sur une grille de démonstration de 255 × 180 injectée directement en base.

*Terminé quand :* on peut cocher des cases sur 45 900 cases avec un pan/zoom fluide sur iPhone, hors-ligne, et retrouver sa progression après rechargement et sur un autre appareil.

*C'est le lot le plus risqué techniquement : il est placé tôt délibérément.*

### Lot 2 — Import assisté universel (type D)

Assistant : dépôt de fichier, aperçu, recadrage manuel, calibrage des dimensions, saisie manuelle de la palette, remplissage des couleurs par zone. Export `.cshp`.

*Terminé quand :* n'importe quel PDF ou photo peut être transformé en motif suivable, entièrement à la main. À ce stade, l'application est déjà une alternative crédible à Pattern Keeper.

### Lot 3 — Statistiques et confort de suivi

Statistiques complètes, filtrage par couleur, masquage des cases faites, surlignage ligne/colonne, annulation multi-niveaux, historique.

*Terminé quand :* les quatre besoins initiaux du §1 sont couverts, même si l'import reste manuel.

### Lot 4 — Extraction automatique type A

Analyse structurelle, détection de grille, parseur de police de symboles, parseur de légende texte, assemblage multi-pages par numéros d'axes. Étapes 2, 6, 7 et 8 de l'assistant passent en pré-remplies.

*Terminé quand :* le PDF « Cafe Brasserie » s'importe en validant simplement les propositions, et que les comptages par couleur obtenus correspondent à ceux de sa page 11.

### Lot 5 — Extraction automatique types B et C

Extraction des couleurs par remplissage de rectangles, rapprochement Lab vers la palette de fils, superposition des grilles jumelles, reconnaissance des symboles vectoriels avec score de confiance.

*Terminé quand :* le PDF « Winter Wreath » s'importe avec ses couleurs correctes, ses deux grilles superposées, et un signalement explicite des cases incertaines.

### Lot 6 — Recettes réutilisables

Calcul d'empreinte, enregistrement et réapplication automatique des configurations validées, gestion de la bibliothèque locale.

*Terminé quand :* réimporter un second PDF du même éditeur saute directement au récapitulatif.

### Lot 7 — Scan et photo (type D automatique)

Détection de grille par vision par ordinateur, correction de perspective, quantification des couleurs par case, classification des symboles, avec validation manuelle obligatoire des zones à faible confiance.

*Terminé quand :* une photo correcte d'une grille papier produit une proposition exploitable, l'utilisateur n'ayant plus qu'à corriger les erreurs signalées.

### Lot 8 — Finitions

Points fractionnés et spéciaux complets dans l'interface de suivi, sauvegarde/restauration, thème sombre, traductions, éventuel partage communautaire des recettes.

### Séquencement recommandé

Les lots 0 à 3 constituent la **V1 utilisable** et devraient être menés d'un trait. Les lots 4 et 5 forment la **V2 différenciante** — c'est là que l'application dépasse la concurrence gratuite. Les lots 6 à 8 sont des amplificateurs, à prioriser selon l'usage réel.

---

## 12. Risques et parades

| Risque | Gravité | Parade |
|---|---|---|
| Rendu de 45 900 cases trop lent sur iPhone | Élevée — c'est l'écran principal | Traité au lot 1, avant tout le reste ; canvas avec tuiles et niveaux de détail ; repli WebGL |
| Hétérogénéité des PDF : chaque nouveau format casse le parseur | Élevée | Assistant semi-automatique (l'utilisateur corrige), mode assisté universel toujours disponible, recettes pour capitaliser |
| Confusion entre deux nuances proches de fil | Moyenne — fausse la broderie | Distance perceptuelle Lab, seuil de confiance, signalement explicite, codes texte de la légende prioritaires sur la couleur |
| Éviction du stockage par Safari | Moyenne — perte de progression | Le serveur est la source de vérité, IndexedDB n'est qu'un cache, deltas rejouables |
| Reconnaissance des symboles vectoriels sans solution existante à réutiliser | Moyenne | Reportée au lot 5, non bloquante ; type B (couleur seule) reste utilisable en attendant |
| Propriété intellectuelle des motifs | Moyenne — juridique | Traitement strictement local, aucun partage de motif, recettes sans contenu créatif, CGU explicites |
| Complexité d'auto-hébergement rebutante | Faible à moyenne | Un seul conteneur, aucune dépendance externe, documentation soignée |

---

## 13. Décisions actées

| Date | Décision |
|---|---|
| 13/09/2026 | Import **semi-automatique guidé** plutôt que tout-automatique ou tout-manuel |
| 13/09/2026 | **Pas d'app native** : webapp PWA installable, iPhone/iPad en cible principale |
| 13/09/2026 | **Frontend + backend self-hosted** : le calcul PDF et la vision restent sur le serveur |
| 13/09/2026 | **React + FastAPI + SQLite + Docker**, sans service externe ni dépendance cloud |
| 13/09/2026 | **Progression stockée séparément de la grille**, pour survivre à un ré-import |
| 14/09/2026 | Ajout du **type E** (grilles en images bitmap réutilisées) à la typologie, après analyse de 4 PDF supplémentaires — hors périmètre du Lot 5, à repositionner dans la roadmap |
| À trancher | Licence open source (MIT pour la diffusion, AGPL pour garantir l'ouverture des forks) |
| À trancher | Partage communautaire des recettes (V3, sous conditions strictes) |
