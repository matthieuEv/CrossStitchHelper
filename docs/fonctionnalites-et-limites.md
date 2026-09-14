# CrossStitchHelper — ce que l'application fera, une fois terminée

*Ce document décrit l'application dans sa version complète, avec toutes les fonctionnalités du cahier des charges construites — pas un état intermédiaire. Objectif : vérifier ensemble s'il manque quelque chose avant de se lancer dans la construction.*

---

## Ce que l'application va faire

### Importer un motif

- Charger un PDF (ou une photo) d'une grille de point de croix et le transformer en un motif que l'app comprend et affiche, via un assistant en plusieurs étapes qui propose automatiquement une configuration complète.
- **Reconnaître automatiquement la couleur et le symbole de chaque case**, quel que soit le style du fichier d'origine : export d'un logiciel de charting, grille dessinée pour une publication (comme les grilles officielles DMC), motif réparti sur deux grilles séparées (une pour les couleurs, une pour les symboles), ou motif étalé sur plusieurs pages à recoller.
- **Reconnaître automatiquement une grille à partir d'une photo** d'un motif papier ou d'un magazine : détection de la zone de la grille, des couleurs et des symboles, avec un signalement clair des cases où la confiance de détection est plus faible, pour une vérification rapide plutôt qu'une ressaisie complète.
- Réutiliser automatiquement la configuration d'un import déjà validé quand un nouveau fichier provient de la même source (même éditeur, même logiciel) — l'import devient quasi instantané pour une personne qui achète régulièrement chez le même vendeur.
- **Garder, à tout moment, la possibilité de corriger à la main** ce que l'assistant a proposé : recadrer la zone, ajuster le nombre de cases, corriger une couleur ou un symbole, compléter la légende. Même terminée, l'application reste un assistant qui propose et que l'on peut corriger, pas une boîte noire qu'il faut croire sur parole.

### Suivre sa broderie

- Cocher les cases au fur et à mesure, case par case, par groupe, ou "toute cette couleur dans la zone visible".
- Se déplacer dans la grille avec les doigts (zoom, déplacement), y compris sur un motif de plusieurs dizaines de milliers de cases, avec une fluidité pensée pour iPhone/iPad.
- Mettre en évidence une couleur précise pour repérer facilement où elle va, masquer ce qui est déjà fait, voir la ligne et la colonne en cours.
- Annuler une action, reprendre où on s'est arrêté, y compris sur un autre appareil (le suivi n'est pas perdu si on change d'iPhone ou de tablette).
- Continuer à cocher même sans connexion internet (les données se remettent à jour automatiquement dès que le réseau revient).

### Savoir quelle couleur utiliser

- Afficher pour chaque case le code de la couleur (DMC par défaut) et son symbole.
- Fournir une légende complète du motif : toutes les couleurs utilisées, leur nom, leur code.
- Gérer les points spéciaux courants : point entier, demi-point, quart de point, point arrière, point de nœud.

### Donner des statistiques

- Pourcentage d'avancement global et par couleur.
- Nombre de points restants, par couleur et par type de point.
- Estimation du nombre d'écheveaux de fil nécessaires (et de ceux qu'il reste à utiliser), selon la toile choisie.
- Historique de la progression dans le temps.

### Rester chez soi

- L'application s'installe sur son propre matériel (ordinateur, NAS, mini-serveur personnel) — aucune donnée n'est envoyée à un service extérieur.
- Les motifs importés et la progression ne sont jamais partagés avec d'autres utilisateurs ni stockés ailleurs que chez l'utilisateur.
- L'app est gratuite et le code est ouvert : rien à payer, rien qui puisse fermer ou devenir payant du jour au lendemain.
- Utilisable comme une vraie app sur iPhone/iPad (icône sur l'écran d'accueil, plein écran), sans passer par l'App Store.

---

## Ce que l'application ne fera jamais

Ce sont des choix de périmètre assumés, pas des fonctionnalités qui manquent encore — ils restent vrais même une fois l'application entièrement terminée.

- **Elle ne crée pas de motifs.** Elle ne transforme pas une photo personnelle en grille à broder (ce n'est pas un outil de création, uniquement un outil de lecture/suivi d'un motif déjà existant).
- **Elle ne propose ni ne vend de motifs.** Aucune bibliothèque de grilles à télécharger dans l'app : chacun importe les fichiers qu'il possède déjà.
- **Elle ne partage rien entre utilisateurs.** Pas de fonction "voir ce que les autres brodent", pas de motifs mis en commun, pas de réseau social autour de l'app.
- **Elle ne sera pas une app iPhone/iPad "native"** téléchargeable depuis l'App Store — ce sera une page web qu'on installe sur l'écran d'accueil, ce qui revient au même à l'usage mais évite les frais et contraintes d'Apple. *(À valider ensemble : c'est un compromis assumé pour rester gratuit, pas une limitation technique qu'on ne pourrait pas lever plus tard si nécessaire.)*
- **Elle ne gère pas plusieurs comptes/utilisateurs séparés.** Une instance = un usage personnel (ou partagé sans distinction entre les personnes qui l'utilisent).
- **Elle ne se synchronise pas avec un cloud public** (pas d'iCloud, pas de Google Drive) — la sauvegarde et la synchronisation restent internes à l'app, sur le serveur qu'on héberge soi-même.

---

## Limites qui resteront, même une fois l'application terminée

Ce ne sont pas des fonctionnalités inachevées : ce sont des limites inhérentes au problème, qui subsisteront quel que soit le niveau de finition du logiciel.

- **Les couleurs affichées restent des approximations.** Les nuanciers de couleurs de fil utilisés ne sont pas des données officielles du fabricant (DMC ne publie pas ses vraies valeurs de couleur) : la teinte affichée à l'écran reste indicative. Quand le fichier d'origine donne le code exact en texte, ce code fait toujours foi — mais l'app ne peut pas garantir que la couleur *affichée à l'écran* soit un rendu parfaitement fidèle du fil réel.
- **La reconnaissance automatique (couleur et symbole) reste probabiliste, jamais garantie à 100 %.** Sur les PDF dessinés à la main pour publication et sur les photos/scans, l'app vise une fiabilité élevée, mais une petite proportion de cases — signalée comme telle — peut nécessiter une vérification ou une correction manuelle. Ce n'est pas un défaut de jeunesse à corriger avec le temps : c'est une limite inhérente à la reconnaissance automatique de formes et de couleurs à partir d'un document, quel que soit le soin apporté au développement.
- **La qualité d'une photo importée influence directement la qualité de la détection.** Un motif photographié avec un mauvais éclairage, flou ou de travers donnera toujours de moins bons résultats qu'un PDF vectoriel propre, quel que soit le niveau d'aboutissement de l'application.
- **La fluidité sur un très gros motif dépend de l'appareil utilisé.** Un iPhone ancien restera toujours moins fluide qu'un modèle récent sur un motif de plusieurs dizaines de milliers de cases.
- **Accéder à son app depuis l'extérieur du domicile** demande une petite configuration technique (un tunnel ou un accès distant à mettre en place), par choix de conception — ce n'est pas automatique comme un service cloud classique, et ça ne changera pas.
- **Une instance reste pensée pour un usage personnel ou de foyer**, sans distinction entre plusieurs personnes qui l'utiliseraient (progression, statistiques et motifs sont partagés entre tous ceux qui accèdent à l'instance).

---

## Pour la discussion : qu'est-ce qui pourrait manquer ?

Ce document sert justement à vérifier ensemble s'il manque une fonctionnalité importante avant de commencer à construire. Quelques questions ouvertes, pas encore tranchées dans un sens ou dans l'autre :

- Le suivi doit-il gérer plusieurs personnes distinctes sur la même instance (par exemple, un couple qui brode chacun ses propres motifs sur le même serveur, avec une progression bien séparée) ?
- Faut-il pouvoir utiliser l'Apple Pencil sur iPad pour marquer les cases ou annoter la grille ?
- Faut-il un mode "impression" pour sortir une version papier du motif ou de la légende ?
- Faut-il pouvoir partager un motif (juste le fichier, pas via l'app) avec une autre personne qui a sa propre instance ?
- Le support Android est-il nécessaire, ou l'usage reste-t-il strictement iPhone/iPad ?
- Faut-il compter le temps réellement passé à broder (un chronomètre), en plus du pourcentage d'avancement ?
- Faut-il pouvoir gérer plusieurs marques de fil (Anchor, DMC…) et convertir les codes de l'une vers l'autre ?

N'hésite pas à ajouter toute autre fonctionnalité à laquelle tu penses en lisant ce document — c'est le moment le moins coûteux pour le faire.
