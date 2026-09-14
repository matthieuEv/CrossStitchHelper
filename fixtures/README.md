# Fixtures — jeu de tests de référence

Six PDF réels utilisés comme vérité terrain pour développer et valider le moteur d'extraction (voir `docs/cahier-des-charges.md` §4 et §8, et le skill `.claude/skills/verify-extraction-fixtures/`). Cinq viennent de DMC (deux structures internes différentes malgré un gabarit visuel commun — voir §4.3 du cahier des charges), un vient d'un éditeur tiers (LaserArtsDesigns) avec une structure entièrement différente.

## `cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf` — type A

Export d'un logiciel de charting (police embarquée personnalisée `CROSSSTICH6`, un glyphe = un symbole). Légende texte complète en pages 9–11.

**Valeurs attendues à vérifier par les tests :**
- Dimensions : 255 × 180 cases (45 900 cases au total)
- 34 couleurs DMC utilisées
- Comptages exacts par couleur en page 11 (ex. DMC 310 "Black" = 3839 points pleins, DMC 3031 "Mocha Brown-VY DK" = 3756 points pleins + 4 quarts + 128,8 cm de point arrière)
- Toile de référence : Aida 16, blanche

## `winter-wreath-dmc/PATASS117_2C_2.pdf` — type C

Grille officielle DMC ("Winter Wreath / Couronne d'hiver"), 5 pages, 100 % vectorielle.

**Caractéristiques à vérifier par les tests :**
- Page 1 : grille couleur (~6800 rectangles vectoriels colorés) — peu de tracés (symboles) sur cette page
- Page 2 : grille symboles séparée, mêmes dimensions que la page 1 (tracés vectoriels, pas du texte)
- Page 4 : légende texte avec codes DMC (3345, 3346, 471, 472, 11, 18, 3821, 726, 3853, 3854, blanc, 351, 814, E321)
- Taille dessin annoncée : 16 × 15,81 cm sur Aida 14 count
- **Sert de cas de référence pour la vraie superposition à deux pages** (contrairement à `summer-flight-dmc` ci-dessous)

## `botanical-citrus-dmc/agrumes_-_planche_botanique.pdf` — type C

Grille officielle DMC ("Botanical Citrus / Agrumes - planche botanique"), 4 pages, 100 % vectorielle.

**Caractéristiques à vérifier par les tests :**
- Page 1 (couleur) : 2827 rectangles, seulement 103 tracés vectoriels — page couleur "propre", peu de bruit de symboles
- Page 2 (symboles) : 1643 rectangles, 1981 tracés vectoriels — page symboles dense
- Séparation couleur/page symbole nette, comme Winter Wreath
- Légende page 4, 17 couleurs DMC

## `cucurbit-dmc/Cucurbitaces.pdf` — type C

Grille officielle DMC ("Cucurbitacées / Cucurbit"), 4 pages, 100 % vectorielle.

**Caractéristiques à vérifier par les tests :**
- Page 1 (couleur) : 1922 rectangles, seulement 31 tracés vectoriels
- Page 2 (symboles) : 886 rectangles, 1072 tracés vectoriels
- Séparation couleur/symbole nette, motif plus petit (13,2 × 9,8 cm)
- Légende page 4, 18 couleurs DMC (6 échantillons hors motif dans la légende — vérifier le filtrage des couleurs réellement utilisées)

## `summer-flight-dmc/vol_de_te.pdf` — type C, variante à superposition non garantie

Grille officielle DMC ("Summer Flight / Envolée estivale"), 5 pages, 100 % vectorielle. **Même gabarit visuel que les trois fixtures DMC ci-dessus, mais structure interne différente — cas de test délibérément piégeux.**

**Caractéristiques à vérifier par les tests :**
- Page 1 : 10224 rectangles **et 2220 tracés vectoriels** — contrairement aux autres fixtures DMC, la page couleur contient déjà une quantité de tracés comparable à une page symboles à part entière
- Page 2 : 7960 rectangles, 1730 tracés vectoriels — également dense, probable doublon noir et blanc plutôt que source de symboles indispensable
- **Ce cas doit faire échouer un connecteur qui supposerait aveuglément "page 1 = couleur seule, page 2 = symboles seuls"** — le moteur d'extraction doit mesurer la densité de tracés par page avant de décider s'il superpose deux pages ou s'il extrait tout depuis une seule
- Légende pages 4–5, 12 couleurs DMC + points de nœud

## `river-and-mountains-laserarts/RiverAndMountains-CS.pdf` — type E

Grille d'un éditeur tiers (LaserArtsDesigns, "River And Mountains - Color Symbol"), 18 pages. **Structure radicalement différente des PDF DMC — aucun rectangle coloré, aucun tracé vectoriel de symbole, aucune police de symboles.**

**Caractéristiques à vérifier par les tests :**
- Page 1 : image de prévisualisation photoréaliste du motif terminé (40084 images sur cette page, mais toutes identiques — une texture de toile Aida réutilisée en fond, pas une grille de travail) — **à détecter et exclure de l'extraction**
- Pages de grille (à partir de la page 2) : composées d'environ 531 petites images bitmap distinctes (48×48 ou 64×64 px, JPEG), réutilisées des milliers de fois — chaque image combine déjà une couleur de fond et une icône de symbole
- Grille large : les axes visibles vont au moins jusqu'à la colonne 220 sur les pages fournies
- **Aucune extraction par rectangle coloré ou tracé vectoriel ne fonctionnera sur ce fichier** — c'est le cas de test qui vérifie que le connecteur type E (catalogue fermé d'images à classifier) est bien invoqué au lieu des connecteurs B/C

## Ajouter une nouvelle fixture

Voir le skill `.claude/skills/add-import-connector/` — chaque nouveau type de PDF rencontré en production et non couvert par ces six cas doit idéalement devenir une nouvelle fixture ici, avec ses valeurs attendues documentées de la même façon.
