---
name: add-import-connector
description: Procédure pour ajouter la prise en charge d'un nouveau format de PDF source (un nouvel éditeur ou logiciel de charting non couvert par les parseurs existants). À utiliser quand un utilisateur signale qu'un PDF s'importe mal ou qu'on veut élargir la couverture du type A.
---

# Ajouter un connecteur d'import pour un nouveau format de PDF

Rappel du principe directeur (`docs/cahier-des-charges.md` §2.3 et §4.3) : il n'existe pas de parseur universel. Chaque nouveau format rencontré est soit rattaché à un type existant (A/B/C/D), soit révèle un besoin d'affiner la détection de type. L'objectif n'est jamais une reconnaissance parfaite, mais une bonne proposition de départ que l'assistant d'import laisse corriger.

## 1. Analyser la structure interne du nouveau PDF

Ne jamais se fier à l'apparence visuelle. Inspecter :
- le texte extractible et les polices embarquées (`pdffonts`, ou `pdfplumber` : `page.chars`, noms de police)
- les rectangles vectoriels et leurs couleurs de remplissage (`page.rects`)
- la présence d'images bitmap (`pdfimages -list`, ou `page.images`)
- les mots-clés de mise en page qui pourraient servir de signature (ex. "Floss Used for", noms de colonnes de légende)

C'est exactement la démarche qui a permis de distinguer les deux fixtures existantes — voir `docs/cahier-des-charges.md` §4.1 et §4.2 pour deux exemples complets de ce diagnostic.

## 2. Déterminer le type (A/B/C/D)

- Police embarquée avec de nombreux glyphes répétés en pavage régulier + légende texte structurée → **type A**, éligible à un parseur dédié.
- Rectangles colorés + symboles en tracés vectoriels, une seule grille → **type B**.
- Deux zones de grille de mêmes dimensions, l'une couleur, l'autre symboles → **type C**.
- Essentiellement une image bitmap → **type D**, pas de connecteur dédié à écrire, le mode assisté universel s'applique déjà.

## 3. Créer la fixture

Ajouter le PDF (ou un extrait anonymisé s'il pose un problème de droits — ne jamais committer un motif dont l'origine/licence est incertaine) dans un nouveau sous-dossier de `fixtures/`, avec un `README.md` documentant les valeurs attendues, sur le modèle de `fixtures/README.md` existant.

## 4. Écrire ou adapter le parseur

- Type A : ajouter la signature de police/mise en page à la détection existante, réutiliser le pipeline de parsing de légende texte plutôt que d'en écrire un nouveau à chaque fois.
- Type B/C : vérifier d'abord si les heuristiques génériques de détection de grille et de rapprochement couleur suffisent déjà — un nouveau cas B/C ne devrait presque jamais nécessiter de code spécifique à l'éditeur, seulement des ajustements de seuils.

## 5. Vérifier avec le skill `verify-extraction-fixtures`

Ne jamais considérer un connecteur terminé sans être passé par cette vérification, fixture par fixture, y compris les fixtures existantes (non-régression).

## 6. Envisager une recette

Si ce format vient d'une source qui produira probablement d'autres PDF similaires (un éditeur, une boutique), envisager de documenter son empreinte pour la fonctionnalité de recettes réutilisables (§8.7 du cahier des charges) — mais cela reste un chantier du Lot 6, pas une obligation immédiate.
