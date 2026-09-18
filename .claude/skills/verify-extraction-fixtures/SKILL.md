---
name: verify-extraction-fixtures
description: Vérifie le moteur d'extraction PDF contre les six fixtures de référence et leurs valeurs attendues. À utiliser après toute modification du moteur d'extraction (backend), avant de considérer la tâche terminée.
---

# Vérifier l'extraction contre les fixtures de référence

Procédure à suivre après toute modification touchant à l'analyse structurelle des PDF, à la détection de grille, aux parseurs de type A/B/C/E, ou au rapprochement couleur → DMC.

## 1. Identifier les fixtures concernées

Six PDF réels couvrent les types A/B/C/E connus (voir `fixtures/README.md` pour la liste complète des valeurs attendues, et `docs/cahier-des-charges.md` §4 pour le détail de chaque cas) :

- `fixtures/cafe-brasserie-charting-export/` — type A (police de symboles embarquée, légende texte) → `backend/app/type_a.py`.
- `fixtures/winter-wreath-dmc/`, `fixtures/summer-flight-dmc/` — type C, cas piège : la page couleur porte déjà ses propres tracés de symbole, ne jamais superposer une deuxième page à l'aveugle → `backend/app/type_bc.py`.
- `fixtures/botanical-citrus-dmc/`, `fixtures/cucurbit-dmc/` — type C, superposition à deux pages réellement nécessaire → `backend/app/type_bc.py`.
- `fixtures/river-and-mountains-laserarts/` — type E (catalogue fermé d'images bitmap réutilisées, couleur+symbole déjà combinés) → `backend/app/type_e.py`. Sert aussi à vérifier l'absence de faux positif des connecteurs A/B/C sur ce fichier structurellement très différent.

N'importe lequel de ces six fichiers peut, à l'œil, sembler suivre une structure différente de sa réalité mesurée (`winter-wreath-dmc` en est la preuve directe, corrigée au Lot 5 après une première description erronée dans le cahier des charges) — ne jamais faire confiance à un premier examen visuel ou à une description déjà écrite sans la revérifier par la mesure sur le fichier réel.

## 2. Lancer l'extraction sur chaque fixture concernée par le changement

Utiliser le point d'entrée du moteur d'extraction backend concerné (`detect_type_a`, `detect_type_bc`, `detect_type_e`) — voir `docs/cahier-des-charges.md` §8 pour le détail des étapes du pipeline : analyse structurelle → détection de grille → parseur spécifique → rapprochement couleur → assemblage.

## 3. Comparer aux valeurs attendues

Les valeurs exactes (dimensions, nombre de couleurs, comptages, stratégie de page) sont dans `fixtures/README.md` — ne pas les recopier ici, un seul endroit par information (voir `CLAUDE.md`). Les suites `backend/tests/test_type_a.py`, `backend/tests/test_type_bc.py` et `backend/tests/test_type_e.py` les vérifient déjà automatiquement ; les relancer est le moyen le plus rapide de faire cette comparaison.

## 4. En cas d'écart

- Si l'écart est mineur et documenté (score de confiance bas, ou case listée dans `uncertain_cells`, signalés correctement) : c'est attendu, l'assistant d'import doit permettre la correction manuelle — vérifier que le signalement de confiance fonctionne, pas que le résultat est parfait.
- Si l'écart est silencieux (valeur fausse sans signalement de confiance bas ni case incertaine) : c'est un bug à corriger avant de considérer la tâche terminée. Ne jamais laisser une extraction incorrecte non signalée.

## 5. Si le changement couvre un cas non représenté par les six fixtures

Envisager l'ajout d'une nouvelle fixture (voir le skill `add-import-connector`) plutôt que de valider uniquement par inspection manuelle ponctuelle — les fixtures sont ce qui empêche une régression silencieuse plus tard.
