/**
 * Français — langue source du projet.
 *
 * Ce fichier définit l'ensemble des clés : `en.ts` est typé d'après lui, donc
 * une clé ajoutée ici provoque une erreur de compilation tant que l'anglais
 * n'est pas complété. C'est ce qui garantit qu'aucune traduction ne manque
 * silencieusement.
 */
export const fr = {
  "app.name": "CrossStitchHelper",
  "app.tagline": "Auto-hébergé",

  "nav.library": "Bibliothèque",
  "nav.libraryShort": "Motifs",
  "nav.track": "Suivi",
  "nav.stats": "Statistiques",
  "nav.statsShort": "Stats",
  "nav.settings": "Réglages",
  "nav.import": "Importer",

  "library.title": "Bibliothèque",
  "library.summary": "{count} motifs · {active} en cours",
  "library.sort": "Trier",
  "library.importCta": "Importer un motif",
  "library.patternMeta": "{size} · {colors} couleurs",
  "library.empty": "Aucun motif pour l'instant. Commencez par en importer un.",

  "import.title": "Importer un motif",
  "import.cancel": "Annuler",
  "import.step.file": "Fichier",
  "import.step.crop": "Cadrage",
  "import.step.palette": "Palette",
  "import.step.recap": "Récap",
  "import.drop.title": "Déposez le PDF ici",
  "import.drop.hint":
    "PDF, PNG ou JPEG. Le fichier reste sur votre serveur, rien n'est envoyé ailleurs.",
  "import.drop.choose": "Choisir un fichier",
  "import.drop.uploading": "Envoi en cours…",
  "import.drop.error": "Échec de l'envoi : {message}",
  "import.photo": "Prendre une photo",
  "import.photo.hint":
    "Photo : posez la grille à plat, bien éclairée, sans ombre portée. Le cadrage se corrige à l'étape suivante.",
  "import.crop.hint":
    "Faites glisser les quatre bords pour ne garder que la grille, puis indiquez ses dimensions en cases.",
  "import.crop.hintDetected":
    "Ce fichier a été reconnu automatiquement : chaque case vient directement de son contenu, pas d'un cadrage. Naviguez entre les pages pour vérifier si besoin.",
  "import.crop.hintDetecting":
    "Analyse automatique en cours… Le cadrage manuel apparaîtra ici si elle ne trouve rien.",
  "import.detection.running": "Analyse automatique en cours… Vous pouvez déjà saisir les dimensions à la main si vous ne voulez pas attendre.",
  "import.detection.title": "Détection automatique : type {type}, confiance {confidence} %",
  "import.detection.hint": "Vérifiez et corrigez si besoin — rien n'est jamais figé.",
  "import.detection.multiPage":
    "Ces dimensions couvrent le motif assemblé depuis les {pageCount} pages du fichier, pas seulement celle affichée ci-dessous.",
  "import.crop.page": "Page {page} / {total}",
  "import.crop.prevPage": "Page précédente",
  "import.crop.nextPage": "Page suivante",
  "import.crop.columns": "Colonnes",
  "import.crop.rows": "Lignes",
  "import.legend.code": "Code",
  "import.legend.name": "Nom du fil",
  "import.legend.symbol": "Sym.",
  "import.legend.color": "Couleur",
  "import.palette.title": "Palette",
  "import.palette.add": "Ajouter une couleur",
  "import.palette.remove": "Retirer",
  "import.palette.empty": "Ajoutez au moins une couleur pour commencer à peindre la grille.",
  "import.paint.hint":
    "Choisissez une couleur, puis dessinez une zone sur la grille pour la peindre.",
  "import.paint.filled": "{filled} / {total} cases peintes",
  "import.paint.tool.paint": "Peindre",
  "import.paint.tool.pan": "Déplacer",
  "import.paint.eraser": "Gomme",
  "import.recap.incomplete":
    "Configuration incomplète : dimensions et palette sont nécessaires avant de continuer.",
  "import.recap.name": "Nom du motif",
  "import.recap.fabric": "Toile (fils au pouce)",
  "import.recap.size": "Taille",
  "import.recap.stitches": "Cases peintes",
  "import.recap.colors": "Couleurs",
  "import.back": "Retour",
  "import.continue": "Continuer",
  "import.finish": "Ajouter et commencer",
  "import.finish.error": "Échec de la création du motif : {message}",

  "track.back": "Retour",
  "track.position": "Ligne {row} · Colonne {col}",
  "track.remaining": "{count} restants",
  "track.colors": "Couleurs",
  "track.zoom.symbols": "Symboles · {size} px/case",
  "track.zoom.blocks": "Blocs · {size} px/case",
  "track.selection": "Zone {cols} × {rows}",
  "track.fillSelection": "Cocher la zone",
  "track.emptySelection": "Décocher la zone",
  "track.dropSelection": "Abandonner la zone",
  "track.filter": "Filtre DMC {dmc}",
  "track.clearFilter": "Retirer le filtre",
  "track.zoomIn": "Zoomer",
  "track.zoomOut": "Dézoomer",
  "track.undo": "Annuler",
  "track.hideDone": "Masquer les cases faites",
  "track.showDone": "Réafficher les cases faites",
  "track.tool.stitch": "Cocher",
  "track.tool.pan": "Déplacer",
  "track.tool.select": "Sélectionner une zone",
  "track.drawer.title": "Couleurs du motif",
  "track.drawer.hint": "Touchez une couleur pour la surligner",
  "track.close": "Fermer",
  "track.remainingStitches": "{count} points restants · {skeins} écheveaux",
  "track.remainingLabel": "restants",

  "stats.title": "Statistiques",
  "stats.export": "Exporter (.cshp)",
  "stats.progress": "Progression",
  "stats.doneOf": "{done} points brodés sur {total}",
  "stats.remaining": "Points restants",
  "stats.skeins": "Écheveaux restants (est.)",
  "stats.time": "Temps restant (est.)",
  "stats.hours": "{count} h",
  "stats.basis":
    "Base : 1 écheveau ≈ 1 800 points sur toile 14 ct, 420 points brodés par heure.",
  "stats.byColor": "Par couleur",
  "stats.skeinsShort": "{count} éch.",
  "stats.activity": "Activité",

  "settings.title": "Réglages",
  "settings.brand": "Marque de fil par défaut",
  "settings.brand.hint": "Utilisée pour nommer les couleurs détectées à l'import.",
  "settings.theme": "Thème",
  "settings.theme.hint": "Le mode sombre baisse aussi la luminosité de la toile.",
  "settings.theme.light": "Clair",
  "settings.theme.dark": "Sombre",
  "settings.theme.system": "Système",
  "settings.language": "Langue",
  "settings.language.hint": "S'applique immédiatement à toute l'interface.",
  "settings.keepAwake": "Garder l'écran allumé pendant la broderie",
  "settings.data": "Données",
  "settings.data.export": "Exporter (.json)",
  "settings.data.restore": "Restaurer une sauvegarde",
  "settings.data.autoBackup": "Sauvegarde automatique quotidienne",
  "settings.data.erase": "Effacer toutes les données",
  "settings.about":
    "CrossStitchHelper {version} — logiciel libre, auto-hébergé. Aucune donnée ne quitte votre serveur. Ajoutez l'app à l'écran d'accueil pour l'utiliser hors ligne.",

  "server.ok": "Serveur joignable",
  "server.unreachable": "Serveur injoignable — les modifications resteront locales.",
  "server.checking": "Connexion au serveur…",

  "demo.notice":
    "Motif de démonstration. L'import réel de fichiers arrivera avec le moteur d'extraction.",
} as const;

export type TranslationKey = keyof typeof fr;
