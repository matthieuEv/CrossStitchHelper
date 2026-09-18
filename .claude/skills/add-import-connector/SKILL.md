---
name: add-import-connector
description: Procédure pour ajouter la prise en charge d'un nouveau format de PDF source (un nouvel éditeur ou logiciel de charting non couvert par les parseurs existants). À utiliser quand un utilisateur signale qu'un PDF s'importe mal ou qu'on veut élargir la couverture du type A.
---

# Ajouter un connecteur d'import pour un nouveau format de PDF

Rappel du principe directeur (`docs/cahier-des-charges.md` §2.3 et §4.3) : il n'existe pas de parseur universel. Chaque nouveau format rencontré est soit rattaché à un type existant (A/B/C/E), soit révèle un besoin d'affiner la détection de type. L'objectif n'est jamais une reconnaissance parfaite, mais une bonne proposition de départ que l'assistant d'import laisse corriger.

Le type D (photo libre, vision par ordinateur) a été abandonné avant toute implémentation (§4.4/§13 du cahier des charges) — ne jamais proposer d'y rattacher un nouveau cas ni d'y consacrer du travail ; un fichier essentiellement bitmap sans catalogue fermé d'icônes reste dans le mode assisté universel (Lot 2), sans connecteur dédié.

## 1. Analyser la structure interne du nouveau PDF

Ne jamais se fier à l'apparence visuelle. Inspecter :
- le texte extractible et les polices embarquées (`pdffonts`, ou `pdfplumber` : `page.chars`, noms de police)
- les rectangles vectoriels et leurs couleurs de remplissage (`page.rects`)
- la présence d'images bitmap et leur réutilisation (`pdfimages -list`, ou `page.images`/`page.get_image_info()`) — un petit nombre d'images distinctes réutilisées des milliers de fois signale un type E, pas juste une image de fond
- les mots-clés de mise en page qui pourraient servir de signature (ex. "Floss Used for", noms de colonnes de légende)

C'est exactement la démarche qui a permis de distinguer les fixtures existantes — voir `docs/cahier-des-charges.md` §4.1, §4.2 et §4.3 pour des exemples complets de ce diagnostic, y compris le cas River And Mountains (type E).

## 2. Déterminer le type (A/B/C/E)

- Police embarquée avec de nombreux glyphes répétés en pavage régulier + légende texte structurée → **type A**, éligible à un parseur dédié.
- Rectangles colorés + symboles en tracés vectoriels, une seule grille → **type B**.
- Deux zones de grille de mêmes dimensions, l'une couleur, l'autre symboles → **type C**.
- Grille composée d'un petit catalogue fermé d'images bitmap (couleur+symbole déjà combinés dans chaque image), réutilisées des milliers de fois → **type E** (`backend/app/type_e.py`) : un problème de classification d'image sur catalogue fermé, pas de vision libre.

## 3. Créer la fixture

Ajouter le PDF (ou un extrait anonymisé s'il pose un problème de droits — ne jamais committer un motif dont l'origine/licence est incertaine) dans un nouveau sous-dossier de `fixtures/`, avec un `README.md` documentant les valeurs attendues, sur le modèle de `fixtures/README.md` existant.

## 4. Écrire ou adapter le parseur

- Type A : ajouter la signature de police/mise en page à la détection existante, réutiliser le pipeline de parsing de légende texte plutôt que d'en écrire un nouveau à chaque fois.
- Type B/C : vérifier d'abord si les heuristiques génériques de détection de grille et de rapprochement couleur suffisent déjà — un nouveau cas B/C ne devrait presque jamais nécessiter de code spécifique à l'éditeur, seulement des ajustements de seuils.
- Type E : vérifier d'abord si `backend/app/type_e.py` (catalogue d'images, déduplication, classification couleur+symbole par image) s'applique tel quel — un nouvel éditeur en type E ne devrait nécessiter que des ajustements de seuils de dédoublonnage, pas un nouveau pipeline.

## 5. Vérifier avec le skill `verify-extraction-fixtures`

Ne jamais considérer un connecteur terminé sans être passé par cette vérification, fixture par fixture, y compris les fixtures existantes (non-régression).

## 6. Envisager une recette

Si ce format vient d'une source qui produira probablement d'autres PDF similaires (un éditeur, une boutique), la fonctionnalité de recettes réutilisables (§8.7 du cahier des charges, Lot 6, `backend/app/fingerprint.py`/`backend/app/api/recipes.py`) s'applique déjà sans rien à écrire de spécifique — elle repose sur une empreinte structurelle générique (taille de page, polices, libellés), pas sur une logique par éditeur.
