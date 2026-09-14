# frontend/

PWA React/TypeScript : bibliothèque de motifs, assistant d'import, écran de
suivi (rendu `<canvas>`), statistiques, réglages. Voir
`docs/cahier-des-charges.md` §5.3 et §7.

## Lancer en développement

```bash
npm install
npm run dev     # http://127.0.0.1:5173, /api transmis vers le backend
```

Le backend doit tourner en parallèle sur le port 8000 (voir `backend/README.md`),
sinon l'application s'affiche mais signale « serveur injoignable ».

```bash
npm run typecheck
npm run build   # produit dist/, servi tel quel par le backend en production
```

## Organisation

| Chemin | Rôle |
| --- | --- |
| `src/index.css` | Système de design : jetons, thème clair/sombre, classes de composants. |
| `src/i18n/` | Traductions FR/EN. `fr.ts` définit les clés, `en.ts` est typé d'après lui. |
| `src/pattern/` | Noyau motif : types, comptages, rendu canvas. Sans dépendance à React. |
| `src/state/useTracker.ts` | État de suivi : progression, vue, outil, annulation. |
| `src/screens/` | Les cinq écrans. |
| `src/components/` | Coquille de navigation, liste des couleurs, vignettes, icônes. |
| `src/demo/` | Motifs de démonstration. À supprimer quand l'import réel existera. |
| `src/lib/` | Thème, routage, client d'API, formatage, verrou d'écran. |

## Règles à respecter

- **Jamais un élément DOM par case.** Le motif de référence fait 45 900 cases :
  toute la grille passe par `<canvas>`, et seules les cases visibles sont
  dessinées (`src/pattern/render.ts`).
- **Aucune chaîne en dur dans un composant.** Tout passe par `useT()` et les
  clés de `src/i18n/`. Ajouter une clé dans `fr.ts` casse la compilation tant
  que `en.ts` n'est pas complété — c'est voulu.
- **Aucune couleur de thème en dur en JavaScript.** Le rendu canvas relit les
  variables CSS (`readGridTheme`), donc `index.css` reste la seule source.
- **Aucun appel réseau vers un tiers.** Toutes les requêtes sont relatives à
  l'origine qui sert l'application.
- **Cibles tactiles d'au moins 44 px**, et taille de police d'au moins 16 px
  dans les champs de saisie — en dessous, iOS zoome à la mise au point.

## Typographie

Les maquettes utilisaient Caprasimo et Figtree, chargées depuis Google Fonts.
Une instance auto-hébergée ne doit dépendre d'aucun service tiers ni cesser de
fonctionner hors ligne : les piles système sont donc utilisées par défaut. Pour
retrouver la typographie exacte des maquettes, déposer les `.woff2` dans
`src/assets/fonts/`, les déclarer en `@font-face` dans `src/index.css`, et
changer `--font-heading` / `--font-body`. Les polices seront alors incluses dans
le précache du service worker (voir `vite.config.ts`).
