/**
 * French — the project's source language.
 *
 * This file defines the full set of keys: `en.ts` is typed from it, so a key
 * added here causes a compilation error until the English is completed. That
 * is what guarantees that no translation silently goes missing.
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
  "import.detection.recipeApplied":
    "Cadrage pré-rempli depuis la recette « {label} » (fichier déjà reconnu).",
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
  "import.paint.uncertainHint":
    "{count} case(s) marquée(s) d'un repère ⚠ : détection automatique incertaine, à vérifier en priorité.",
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
  "import.recap.saveRecipe": "Enregistrer le cadrage comme recette réutilisable",
  "import.recap.saveRecipe.hint":
    "Un prochain fichier du même éditeur (même gabarit) pourra reprendre automatiquement ce cadrage. Jamais les couleurs ni les dimensions de ce motif.",
  "import.recap.saveRecipe.label": "Nom de la recette (ex. l'éditeur ou la boutique)",
  "import.recap.saveRecipe.error": "Échec de l'enregistrement de la recette : {message}",
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
  "track.layer.title": "Catégorie de point",
  "track.layer.full": "Point entier",
  "track.layer.half": "Point 1/2",
  "track.layer.quarter": "Point 1/4",
  "track.layer.backstitch": "Point arrière",
  "track.layer.knot": "Nœud",
  "track.layer.zoomHint": "Zoomez pour cocher le point arrière et les nœuds",
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
  "settings.data.restore.confirm":
    "Restaurer ce fichier remplacera TOUS les motifs, toute la progression et toutes les recettes actuellement sur ce serveur — action irréversible. Continuer ?",
  "settings.data.restore.invalidFile":
    "Ce fichier n'est pas un JSON valide — vérifiez qu'il s'agit bien d'un export CrossStitchHelper.",
  "settings.data.restore.success": "{patterns} motif(s) et {recipes} recette(s) restauré(s).",
  "settings.data.restore.error": "Restauration impossible : {message}",
  "settings.data.autoBackup": "Sauvegarde automatique quotidienne",
  "settings.data.autoBackup.error": "Réglage indisponible hors ligne.",
  "settings.data.erase": "Effacer toutes les données",
  "settings.data.erase.confirm":
    "Effacer définitivement tous les motifs, toute la progression et toutes les recettes de ce serveur — action irréversible. Continuer ?",
  "settings.data.erase.done": "Toutes les données ont été effacées.",
  "settings.recipes": "Recettes réutilisables",
  "settings.recipes.hint":
    "Cadrage réutilisé automatiquement sur un prochain fichier du même éditeur — jamais les couleurs ni les dimensions d'un motif.",
  "settings.recipes.empty": "Aucune recette enregistrée pour l'instant.",
  "settings.recipes.usage": "{count} utilisation(s)",
  "settings.recipes.delete": "Supprimer",
  "settings.about":
    "CrossStitchHelper {version} — logiciel libre, auto-hébergé. Aucune donnée ne quitte votre serveur. Ajoutez l'app à l'écran d'accueil pour l'utiliser hors ligne.",

  "server.ok": "Serveur joignable",
  "server.unreachable": "Serveur injoignable — les modifications resteront locales.",
  "server.checking": "Connexion au serveur…",

  "demo.notice":
    "Motif de démonstration. L'import réel de fichiers arrivera avec le moteur d'extraction.",

  // --- API errors (translation audit, Lot 8) --------------------------------
  // Translations of the `ApiErrorDetail.code` codes (backend/app/schemas.py) —
  // never a message already composed on the server. `error.unknown` is the
  // fallback if the server returns a code this frontend does not know yet
  // (version skew).
  "error.unknown": "Une erreur est survenue.",
  "error.backup_unexpected_format": "Format de sauvegarde inattendu : {got} (attendu {expected}).",
  "error.backup_unsupported_version":
    "Version de sauvegarde non prise en charge : {got} (cette instance sait lire la version {expected}).",
  "error.import_not_found": "Import introuvable.",
  "error.import_already_committed":
    "Cet import a déjà été validé et ne peut plus être modifié.",
  "error.import_unsupported_file_type":
    "Format non pris en charge : seuls PDF, PNG et JPEG le sont.",
  "error.import_file_too_large": "Fichier trop volumineux (> {max_mb} Mo).",
  "error.import_file_unreadable": "Fichier illisible.",
  "error.import_source_missing": "Fichier source introuvable (import déjà validé ?).",
  "error.import_page_out_of_range": "Page {page} hors limites (1..{count}).",
  "error.import_photo_single_page": "Une photo n'a qu'une seule page.",
  "error.import_config_incomplete":
    "Configuration incomplète : dimensions et palette sont requises.",
  "error.recipe_no_fingerprint":
    "Ce fichier n'a pas d'empreinte réutilisable (format non-PDF, ou analyse échouée).",
  "error.recipe_not_found": "Recette introuvable.",
  "error.pattern_not_found": "Motif introuvable.",
  "error.pattern_grid_not_found": "Grille introuvable pour ce motif.",
  "error.pattern_progress_not_found": "Progression introuvable pour ce motif.",
  "error.pattern_grid_or_progress_not_found": "Grille ou progression introuvable.",
  "error.pattern_progress_index_out_of_range":
    "Index hors limites pour la catégorie « {layer} » : {index} >= {bound}.",

  // --- Automatic detection warnings (translation audit, Lot 8) --------------
  // Translations of the `DetectionWarning.code` codes (backend/app/schemas.py),
  // shown in the import wizard (ImportScreen.tsx). Parameter names
  // (`{declared_columns}`, `{max_mb}`…) are snake_case: they come as is from
  // the backend (`params: dict[str, ...]`), never renamed along the way.
  "import.warning.unknown": "Un point mérite vérification (détails indisponibles).",

  "import.warning.type_a.missing_full_stitches_legend":
    "Aucune section « Floss Used for Full Stitches » trouvée dans la légende : la palette de couleurs n'a pas pu être reconstruite automatiquement.",
  "import.warning.type_a.unknown_dmc_codes":
    "Code(s) DMC absent(s) de la table de couleurs locale : {codes} — couleur d'affichage approximative utilisée (le code et le nom restent ceux imprimés dans le PDF).",
  "import.warning.type_a.ambiguous_dmc_codes":
    "Code(s) DMC dont le symbole et la couleur de repère sont identiques à une autre ligne de la légende, rendant leurs cases indistinguables : {codes} — cases attribuées à la première ligne correspondante.",
  "import.warning.type_a.axis_numbers_missing_on_page":
    "Page {page} : numéros d'axe introuvables, positionnement approximatif par ordre de lecture plutôt qu'abandon de la page.",
  "import.warning.type_a.dimensions_inferred":
    "Dimensions non annoncées explicitement dans le PDF : déduites de l'étendue de la grille assemblée.",
  "import.warning.type_a.dimensions_mismatch":
    "Les dimensions annoncées par le PDF ({declared_columns}×{declared_rows}) ne correspondent pas exactement à l'étendue reconstruite ({seen_columns}×{seen_rows}) — dimensions annoncées conservées.",
  "import.warning.type_a.unmapped_symbols":
    "{count} symbole(s)/couleur(s) sans correspondance dans la légende ({cells} case(s) concernée(s)) — ajouté(s) à la palette comme « Symbole non reconnu ».",

  "import.warning.type_bc.border_inferred":
    "Bordure de grille non détectée explicitement : dimensions déduites de l'étendue des cases coloriées, potentiellement sous-estimées si le motif ne touche pas les bords de la grille imprimée.",
  "import.warning.type_bc.symbol_page_unusable":
    "Page de symboles détectée mais aucune forme n'a pu être regroupée par case (recalage incertain) : repli sur la couleur seule (type B).",
  "import.warning.type_bc.symbol_recognition_unreliable":
    "Reconnaissance de symboles trop peu fiable sur l'ensemble du fichier (formes trop fragmentées d'une case à l'autre) : repli sur la couleur seule (type B).",
  "import.warning.type_bc.no_symbol_page":
    "Aucune page de symboles exploitable trouvée (densité de tracés vectoriels insuffisante sur toutes les pages candidates) : seule la couleur a pu être extraite automatiquement.",
  "import.warning.type_bc.background_color_excluded":
    "Une couleur de fond couvrant une fraction implausible de la grille ({cells} case(s)) a été écartée automatiquement — probablement un aplat de fond de page plutôt qu'un fil à broder.",
  "import.warning.type_bc.uncertain_dmc_match":
    "Rapprochement DMC incertain (distance perceptuelle élevée) pour {count} couleur(s) — à vérifier à l'étape légende de l'assistant.",
  "import.warning.type_bc.uncertain_cells":
    "{count} case(s) signalée(s) comme incertaine(s) (couleur douteuse et/ou symbole ambigu) — correction manuelle recommandée.",

  "import.warning.type_e.pages_without_axis_numbers":
    "{count} page(s) porteuse(s) d'images de catalogue mais sans numéros d'axe exploitables n'ont pas pu être positionnées et sont ignorées.",
  "import.warning.type_e.overlapping_pages":
    "{count} case(s) où deux pages se recouvrent avec des images différentes — la dernière page traitée l'emporte.",
  "import.warning.type_e.missing_legend":
    "Aucune légende de couleurs DMC reconnue dans le PDF : les images du catalogue restent non identifiées (« Symbole non reconnu »).",
  "import.warning.type_e.dimensions_inferred":
    "Dimensions non annoncées explicitement dans le PDF : déduites de l'étendue des images placées.",
  "import.warning.type_e.dimensions_mismatch":
    "Les dimensions annoncées par le PDF ({declared_columns}×{declared_rows}) ne correspondent pas exactement à l'étendue reconstruite ({seen_columns}×{seen_rows}) — dimensions annoncées conservées.",
  "import.warning.type_e.count_match_ambiguous":
    "{count} image(s) du catalogue n'ont pas pu être rapprochées sans ambiguïté par comptage exact (comptages en doublon) — rapprochement par couleur perceptuelle utilisé en repli, moins fiable.",
  "import.warning.type_e.unmatched_catalog_images":
    "{count} image(s) du catalogue sans ligne de légende correspondante — ajoutée(s) à la palette comme « Symbole non reconnu ».",

  "import.warning.detection.unexpected_failure":
    "Échec inattendu de la détection automatique : {error}",
  "import.warning.detection.manual_config_kept":
    "Configuration déjà modifiée manuellement avant la fin de l'analyse : la proposition automatique n'a pas été appliquée.",
} as const;

export type TranslationKey = keyof typeof fr;
