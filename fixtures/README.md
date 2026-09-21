# Fixtures — jeu de tests de référence

Six PDF réels utilisés comme vérité terrain pour développer et valider le moteur d'extraction (voir `docs/cahier-des-charges.md` §4 et §8, et le skill `.claude/skills/verify-extraction-fixtures/`). Cinq viennent de DMC (deux structures internes différentes malgré un gabarit visuel commun — voir §4.3 du cahier des charges), un vient d'un éditeur tiers (LaserArtsDesigns) avec une structure entièrement différente.

## `cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf` — type A

Export d'un logiciel de charting (police embarquée personnalisée `CROSSSTICH6`, un glyphe = un symbole). Légende texte complète en pages 9–11.

**Valeurs attendues à vérifier par les tests :**
- Dimensions : 255 × 180 cases (45 900 cases au total)
- 34 couleurs DMC utilisées
- Comptages exacts par couleur en page 11 (ex. DMC 310 "Black" = 3839 points pleins, DMC 3031 "Mocha Brown-VY DK" = 3756 points pleins + 4 quarts + 128,8 cm de point arrière)
- Toile de référence : Aida 16, blanche

**Points spéciaux — mesuré au Lot 9 (`backend/tests/test_type_a.py`), pas supposé :**
- La légende ne s'arrête pas aux points entiers : pages 9–10, cinq sections « Floss Used for ... » se suivent — *Full* (34 lignes), *Half* (762, 3756, B5200), *Quarter* (3031), *French Knots* (742), *Back Stitches* (310, 640, 642, 742, 814, 839, 938, 3031). Les deux dernières sections n'ont **pas** de glyphe de symbole : leur colonne « Symbol » est un échantillon vectoriel tracé dans la couleur exacte utilisée sur les pages de grille — c'est la clé de rapprochement couleur → code DMC, mesurée dans le fichier, et non une ressemblance colorimétrique (un plus proche voisin Lab se trompe sur ce fichier : il intervertit 938 et 3031, et n'attribue jamais 310, tracé en (35, 40, 29) et non en noir).
- Chaque point arrière est tracé **deux fois** au même endroit (passe sombre de 2.4 pt puis passe claire de 2.08 pt) : le compter deux fois double la longueur. En prime, chaque page redessine en teintes délavées la bande qu'elle partage avec la page voisine — 8 teintes supplémentaires qui ne doivent jamais s'ajouter au total (elles ne recouvrent que des tracés déjà comptés).
- Extrémités de point arrière : toutes sur le réseau demi-case (5 120 sur des coins de case, 52 sur des milieux), souvent en diagonale — et 36 des 56 diagonales de la page 1 sont *descendantes*, donc illisibles depuis la seule bbox pdfplumber (il faut `pts`).
- La colonne « Back(cm) » de la page 11 est en réalité exprimée en **pouces** : sa valeur vaut exactement la longueur en cases divisée par le compte de toile déclaré (Aida 16). Les huit codes se retrouvent à moins de 0,1 % près par cette conversion.
- Les 4 points 1/4 (DMC 3031) sont dessinés en petit **dans un coin de case déjà occupée** par un demi-point DMC 3756, avec le même glyphe et la même couleur de fond que le point entier 3031 : seuls leur décalage dans la case les distingue (48 310 glyphes sur 48 314 sont exactement centrés).
- Les 3 nœuds (DMC 742) sont sur la seule page 1. À ne pas confondre avec deux autres formes présentes sur les pages de grille : les **flèches de repère de page** (petite forme pleine noire d'exactement une case, en marge, sur chaque page) et des **annotations manuelles** laissées dans le fichier (traits bleu système `#007AFF` tracés à main levée sur les pages 2 et 6, hors de tout alignement sur les cases).

## `winter-wreath-dmc/PATASS117_2C_2.pdf` — type C

Grille officielle DMC ("Winter Wreath / Couronne d'hiver"), 5 pages, 100 % vectorielle.

**Caractéristiques à vérifier par les tests :**
- Page 1 : grille couleur (~6800 rectangles vectoriels colorés) — **mesuré au Lot 5 (`backend/tests/test_type_bc.py`) : cette page porte en réalité déjà ~3362 courbes de tracé réparties sur toute la grille (un petit symbole par-dessus chaque aplat de couleur), pas "peu de tracés" comme le laisse croire un premier coup d'œil**
- Page 2 : grille symboles séparée en noir et blanc, mêmes dimensions que la page 1 (~2466 courbes) — mesuré au Lot 5 : redondante avec les symboles déjà présents sur la page 1, jamais la seule source exploitable
- Page 4 : légende texte avec codes DMC (3345, 3346, 471, 472, 11, 18, 3821, 726, 3853, 3854, blanc, 351, 814, E321)
- Taille dessin annoncée : 16 × 15,81 cm sur Aida 14 count
- **Se comporte en réalité comme le cas piège `summer-flight-dmc` ci-dessous** (contrairement à ce qu'un premier examen visuel suggère) : `botanical-citrus-dmc` et `cucurbit-dmc` sont les deux seules fixtures DMC de ce jeu à réellement superposer une deuxième page de symboles — voir cahier des charges §4.1 pour le détail de cette correction mesurée au Lot 5.

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
- Page 1 : image de prévisualisation photoréaliste du motif terminé (40084 placements d'image sur cette page) — **à détecter et exclure de l'extraction**. **Précision mesurée au Lot 7 (`backend/app/type_e.py`), pas supposée à l'écriture initiale de cette fiche :** ces placements ne sont pas tous identiques — 21 images distinctes (tailles mêlées 48×48 et 64×64 px), un empâtement de texture pour un rendu photoréaliste, entièrement disjoint du catalogue des pages de grille (aucune image en commun). C'est la fraction de placements à la taille dominante (69,8 % ici, jamais 100 % comme sur une vraie page de grille) qui permet de l'exclure de façon fiable, pas sa position de « page 1 » à elle seule.
- Pages de grille (2 à 16) : composées d'images bitmap réutilisées (64×64 px), pavées sur un quadrillage régulier avec numéros d'axe absolus en marge (même mécanisme d'assemblage multi-pages que `cafe-brasserie-charting-export`, en 5 pages de large x 3 pages de haut). **Correction Lot 7, mesurée et non supposée : seulement 20 images réellement distinctes, pas ~531** (531 est le nombre de *placements* sur la seule page 2, pas le nombre d'images distinctes — voir `docs/cahier-des-charges.md` §4.3 pour le détail de cette correction). Ces 20 images correspondent exactement aux 20 couleurs DMC de la légende (page 17) : une image par couleur, combinant déjà un aplat de fond uni et un symbole dessiné par-dessus en couleur contrastante — confirmé visuellement (`doc.extract_image` + Pillow).
- Page 17 : légende texte complète (comme la page 11 de `cafe-brasserie-charting-export`), 20 couleurs DMC avec code, nom et **nombre de points exact par couleur**, et les dimensions déclarées en clair (« 217x206 Stitches »). Réutilise les mêmes 20 images que les pages de grille (à titre d'aperçu, une par ligne) — ce n'est ni sa taille d'image ni son taux de réutilisation qui l'excluent de l'extraction de grille, mais l'absence de numéros d'axe à deux dimensions (ses images sont alignées en une seule colonne verticale, jamais pavées sur un quadrillage).
- Page 18 : carte d'assemblage des 15 pages de grille (pas une page de travail), avec 15 images bien plus grandes (207×294 pt) et non carrées (ratio ≈ 0,70), chacune utilisée une seule fois — **à exclure aussi**, par le même genre de mesure structurelle que la page 1 (taille/forme des images placées), jamais une exclusion supposée par position de page.
- **Aucune extraction par rectangle coloré ou tracé vectoriel ne fonctionnera sur ce fichier** — c'est le cas de test qui vérifie que le connecteur type E (catalogue fermé d'images à classifier) est bien invoqué au lieu des connecteurs B/C.
- **Rapprocher la couleur de fond de chaque image du catalogue vers le code DMC le plus proche (même restreint aux 20 codes de la légende) s'avère peu fiable sur ce fichier** (12 des 20 images mal identifiées, mesuré) : le signal fiable et vérifié exact utilisé par `detect_type_e` est le nombre total de placements de chaque image, qui correspond très exactement au nombre de points déclaré par la légende pour chaque couleur — la couleur perceptuelle ne sert que de repli explicite, jamais de signal primaire, pour ce connecteur précis.

## Ajouter une nouvelle fixture

Voir le skill `.claude/skills/add-import-connector/` — chaque nouveau type de PDF rencontré en production et non couvert par ces six cas doit idéalement devenir une nouvelle fixture ici, avec ses valeurs attendues documentées de la même façon.
