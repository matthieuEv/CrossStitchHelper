---
name: verify-extraction-fixtures
description: Vérifie le moteur d'extraction PDF contre les deux fixtures de référence et leurs valeurs attendues. À utiliser après toute modification du moteur d'extraction (backend), avant de considérer la tâche terminée.
---

# Vérifier l'extraction contre les fixtures de référence

Procédure à suivre après toute modification touchant à l'analyse structurelle des PDF, à la détection de grille, aux parseurs de type A/B/C, ou au rapprochement couleur → DMC.

## 1. Identifier les fixtures concernées

- `fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf` — cas type A (police de symboles embarquée, légende texte).
- `fixtures/winter-wreath-dmc/PATASS117_2C_2.pdf` — cas types B/C (vectoriel, grilles jumelles couleur/symboles).

Lire `fixtures/README.md` pour la liste complète des valeurs attendues avant de commencer.

## 2. Lancer l'extraction sur chaque fixture concernée par le changement

Utiliser le point d'entrée du moteur d'extraction backend (voir `docs/cahier-des-charges.md` §8 pour le détail des étapes du pipeline : analyse structurelle → détection de grille → parseur spécifique → rapprochement couleur → assemblage).

## 3. Comparer aux valeurs attendues

Pour `cafe-brasserie-charting-export` :
- Dimensions extraites = 255 × 180 (45 900 cases)
- 34 couleurs distinctes identifiées
- Comptages par couleur cohérents avec la page 11 du PDF (ex. DMC 310 = 3839 points pleins)

Pour `winter-wreath-dmc` :
- Couleurs de case extraites correctement depuis les rectangles vectoriels de la page 1
- Grille de symboles de la page 2 correctement superposée à la grille de couleurs de la page 1 (mêmes dimensions, recalage correct)
- Codes DMC de la légende (page 4) correctement associés aux couleurs extraites

## 4. En cas d'écart

- Si l'écart est mineur et documenté (score de confiance bas signalé correctement) : c'est attendu, l'assistant d'import doit permettre la correction manuelle — vérifier que le signalement de confiance fonctionne, pas que le résultat est parfait.
- Si l'écart est silencieux (valeur fausse sans signalement de confiance bas) : c'est un bug à corriger avant de considérer la tâche terminée. Ne jamais laisser une extraction incorrecte non signalée.

## 5. Si le changement couvre un cas non représenté par les deux fixtures

Envisager l'ajout d'une nouvelle fixture (voir le skill `add-import-connector`) plutôt que de valider uniquement par inspection manuelle ponctuelle — les fixtures sont ce qui empêche une régression silencieuse plus tard.
