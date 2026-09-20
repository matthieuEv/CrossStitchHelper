import type { TranslationKey } from "./fr";

/** English — every key of `fr.ts` must appear here (enforced by the type). */
export const en: Record<TranslationKey, string> = {
  "app.name": "CrossStitchHelper",
  "app.tagline": "Self-hosted",

  "nav.library": "Library",
  "nav.libraryShort": "Patterns",
  "nav.track": "Stitch",
  "nav.stats": "Statistics",
  "nav.statsShort": "Stats",
  "nav.settings": "Settings",
  "nav.import": "Import",

  "library.title": "Library",
  "library.summary": "{count} patterns · {active} in progress",
  "library.sort": "Sort",
  "library.importCta": "Import a pattern",
  "library.patternMeta": "{size} · {colors} colours",
  "library.empty": "No patterns yet. Start by importing one.",

  "import.title": "Import a pattern",
  "import.cancel": "Cancel",
  "import.step.file": "File",
  "import.step.crop": "Crop",
  "import.step.palette": "Palette",
  "import.step.recap": "Review",
  "import.drop.title": "Drop the PDF here",
  "import.drop.hint":
    "PDF, PNG or JPEG. The file stays on your server — nothing is sent anywhere else.",
  "import.drop.choose": "Choose a file",
  "import.drop.uploading": "Uploading…",
  "import.drop.error": "Upload failed: {message}",
  "import.crop.hint": "Drag the four edges to keep only the grid, then set its size in cells.",
  "import.crop.hintDetected":
    "This file was recognized automatically: every cell comes straight from its content, not from cropping. Browse the pages to double-check if you'd like.",
  "import.crop.hintDetecting":
    "Automatic analysis running… Manual cropping will show up here if it finds nothing.",
  "import.detection.running": "Automatic analysis running… You can already type in the dimensions by hand if you don't want to wait.",
  "import.detection.title": "Automatic detection: type {type}, {confidence}% confidence",
  "import.detection.hint": "Check and correct as needed — nothing here is final.",
  "import.detection.multiPage":
    "These dimensions cover the pattern assembled from all {pageCount} pages of the file, not just the one shown below.",
  "import.detection.recipeApplied":
    "Cropping pre-filled from the \"{label}\" recipe (this file was already recognised).",
  "import.crop.page": "Page {page} / {total}",
  "import.crop.prevPage": "Previous page",
  "import.crop.nextPage": "Next page",
  "import.crop.columns": "Columns",
  "import.crop.rows": "Rows",
  "import.legend.code": "Code",
  "import.legend.name": "Thread name",
  "import.legend.symbol": "Sym.",
  "import.legend.color": "Colour",
  "import.palette.title": "Palette",
  "import.palette.add": "Add a colour",
  "import.palette.remove": "Remove",
  "import.palette.empty": "Add at least one colour to start painting the grid.",
  "import.paint.hint": "Pick a colour, then drag over the grid to paint an area.",
  "import.paint.filled": "{filled} / {total} cells painted",
  "import.paint.uncertainHint":
    "{count} cell(s) marked with a ⚠: automatic detection was unsure, check these first.",
  "import.paint.tool.paint": "Paint",
  "import.paint.tool.pan": "Move",
  "import.paint.eraser": "Eraser",
  "import.recap.incomplete": "Incomplete configuration: dimensions and palette are required to continue.",
  "import.recap.name": "Pattern name",
  "import.recap.fabric": "Fabric (count)",
  "import.recap.size": "Size",
  "import.recap.stitches": "Painted cells",
  "import.recap.colors": "Colours",
  "import.recap.saveRecipe": "Save this cropping as a reusable recipe",
  "import.recap.saveRecipe.hint":
    "A future file from the same editor (same template) can pick up this cropping automatically. Never this pattern's colours or dimensions.",
  "import.recap.saveRecipe.label": "Recipe name (e.g. the editor or shop)",
  "import.recap.saveRecipe.error": "Failed to save the recipe: {message}",
  "import.back": "Back",
  "import.continue": "Continue",
  "import.finish": "Add and start",
  "import.finish.error": "Failed to create the pattern: {message}",

  "track.back": "Back",
  "track.position": "Row {row} · Column {col}",
  "track.remaining": "{count} left",
  "track.colors": "Colours",
  "track.zoom.symbols": "Symbols · {size} px/cell",
  "track.zoom.blocks": "Blocks · {size} px/cell",
  "track.selection": "Area {cols} × {rows}",
  "track.fillSelection": "Mark the area",
  "track.emptySelection": "Unmark the area",
  "track.dropSelection": "Discard the area",
  "track.filter": "DMC {dmc} filter",
  "track.clearFilter": "Clear filter",
  "track.zoomIn": "Zoom in",
  "track.zoomOut": "Zoom out",
  "track.undo": "Undo",
  "track.hideDone": "Hide stitched cells",
  "track.showDone": "Show stitched cells",
  "track.tool.stitch": "Mark",
  "track.tool.pan": "Pan",
  "track.tool.select": "Select an area",
  "track.layer.title": "Stitch category",
  "track.layer.full": "Full stitch",
  "track.layer.half": "Half stitch",
  "track.layer.quarter": "Quarter stitch",
  "track.layer.backstitch": "Backstitch",
  "track.layer.knot": "French knot",
  "track.layer.zoomHint": "Zoom in to mark backstitch and French knots",
  "track.drawer.title": "Pattern colours",
  "track.drawer.hint": "Tap a colour to highlight it",
  "track.close": "Close",
  "track.remainingStitches": "{count} stitches left · {skeins} skeins",
  "track.remainingLabel": "left",

  "stats.title": "Statistics",
  "stats.export": "Export (.cshp)",
  "stats.progress": "Progress",
  "stats.doneOf": "{done} stitches done out of {total}",
  "stats.remaining": "Stitches left",
  "stats.skeins": "Skeins left (est.)",
  "stats.time": "Time left (est.)",
  "stats.hours": "{count} h",
  "stats.basis":
    "Based on: 1 skein ≈ 1,800 stitches on 14 ct fabric, 420 stitches per hour.",
  "stats.byColor": "By colour",
  "stats.skeinsShort": "{count} sk.",
  "stats.activity": "Activity",

  "settings.title": "Settings",
  "settings.brand": "Default thread brand",
  "settings.brand.hint": "Used to name the colours detected during import.",
  "settings.theme": "Theme",
  "settings.theme.hint": "Dark mode also dims the fabric.",
  "settings.theme.light": "Light",
  "settings.theme.dark": "Dark",
  "settings.theme.system": "System",
  "settings.language": "Language",
  "settings.language.hint": "Applies to the whole interface immediately.",
  "settings.keepAwake": "Keep the screen awake while stitching",
  "settings.data": "Data",
  "settings.data.export": "Export (.json)",
  "settings.data.restore": "Restore a backup",
  "settings.data.restore.confirm":
    "Restoring this file will replace ALL patterns, all progress, and all recipes currently on this server — this cannot be undone. Continue?",
  "settings.data.restore.invalidFile":
    "This file isn't valid JSON — check that it's really a CrossStitchHelper export.",
  "settings.data.restore.success": "{patterns} pattern(s) and {recipes} recipe(s) restored.",
  "settings.data.restore.error": "Restore failed: {message}",
  "settings.data.autoBackup": "Daily automatic backup",
  "settings.data.autoBackup.error": "Setting unavailable offline.",
  "settings.data.erase": "Erase all data",
  "settings.data.erase.confirm":
    "Permanently erase all patterns, all progress, and all recipes on this server — this cannot be undone. Continue?",
  "settings.data.erase.done": "All data has been erased.",
  "settings.recipes": "Reusable recipes",
  "settings.recipes.hint":
    "Cropping reused automatically on a future file from the same editor — never a pattern's colours or dimensions.",
  "settings.recipes.empty": "No recipe saved yet.",
  "settings.recipes.usage": "{count} use(s)",
  "settings.recipes.delete": "Delete",
  "settings.about":
    "CrossStitchHelper {version} — free software, self-hosted. No data leaves your server. Add the app to your home screen to use it offline.",

  "server.ok": "Server reachable",
  "server.unreachable": "Server unreachable — changes will stay on this device.",
  "server.checking": "Connecting to the server…",

  "demo.notice":
    "Demonstration pattern. Real file import arrives with the extraction engine.",

  "error.unknown": "Something went wrong.",
  "error.backup_unexpected_format": "Unexpected backup format: {got} (expected {expected}).",
  "error.backup_unsupported_version":
    "Unsupported backup version: {got} (this instance can read version {expected}).",
  "error.import_not_found": "Import not found.",
  "error.import_already_committed":
    "This import has already been finalised and can no longer be edited.",
  "error.import_unsupported_file_type":
    "Unsupported format: only PDF, PNG and JPEG are accepted.",
  "error.import_file_too_large": "File too large (> {max_mb} MB).",
  "error.import_file_unreadable": "Unreadable file.",
  "error.import_source_missing": "Source file not found (was this import already finalised?).",
  "error.import_page_out_of_range": "Page {page} out of range (1..{count}).",
  "error.import_photo_single_page": "A photo only has a single page.",
  "error.import_config_incomplete": "Incomplete configuration: dimensions and palette are required.",
  "error.recipe_no_fingerprint":
    "This file has no reusable fingerprint (non-PDF format, or analysis failed).",
  "error.recipe_not_found": "Recipe not found.",
  "error.pattern_not_found": "Pattern not found.",
  "error.pattern_grid_not_found": "Grid not found for this pattern.",
  "error.pattern_progress_not_found": "Progress not found for this pattern.",
  "error.pattern_grid_or_progress_not_found": "Grid or progress not found.",
  "error.pattern_progress_index_out_of_range":
    'Index out of range for category "{layer}": {index} >= {bound}.',

  "import.warning.unknown": "Something here is worth double-checking (details unavailable).",

  "import.warning.type_a.missing_full_stitches_legend":
    'No "Floss Used for Full Stitches" section found in the legend: the colour palette could not be reconstructed automatically.',
  "import.warning.type_a.unknown_dmc_codes":
    "DMC code(s) missing from the local colour table: {codes} — an approximate display colour was used (the code and name are still those printed in the PDF).",
  "import.warning.type_a.ambiguous_dmc_codes":
    "DMC code(s) whose symbol and swatch colour match another legend row, making their cells indistinguishable: {codes} — cells assigned to the first matching row.",
  "import.warning.type_a.axis_numbers_missing_on_page":
    "Page {page}: axis numbers not found — cells positioned approximately by reading order instead of skipping the page.",
  "import.warning.type_a.dimensions_inferred":
    "Dimensions not explicitly stated in the PDF: inferred from the assembled grid's extent.",
  "import.warning.type_a.dimensions_mismatch":
    "The dimensions stated in the PDF ({declared_columns}×{declared_rows}) don't exactly match the reconstructed extent ({seen_columns}×{seen_rows}) — kept the stated dimensions.",
  "import.warning.type_a.unmapped_symbols":
    '{count} symbol(s)/colour(s) with no match in the legend ({cells} cell(s) affected) — added to the palette as "Unrecognised symbol".',

  "import.warning.type_bc.border_inferred":
    "Grid border not explicitly detected: dimensions inferred from the extent of coloured cells — potentially underestimated if the pattern doesn't reach the edges of the printed grid.",
  "import.warning.type_bc.symbol_page_unusable":
    "A symbol page was detected but no shape could be grouped into cells (uncertain alignment): fell back to colour only (type B).",
  "import.warning.type_bc.symbol_recognition_unreliable":
    "Symbol recognition too unreliable across the whole file (shapes too fragmented from one cell to another): fell back to colour only (type B).",
  "import.warning.type_bc.no_symbol_page":
    "No usable symbol page found (insufficient vector-trace density on every candidate page): only colour could be extracted automatically.",
  "import.warning.type_bc.background_color_excluded":
    "A background colour covering an implausible fraction of the grid ({cells} cell(s)) was automatically excluded — likely a page background fill rather than an actual thread.",
  "import.warning.type_bc.uncertain_dmc_match":
    "Uncertain DMC match (high perceptual distance) for {count} colour(s) — worth checking at the legend step of the assistant.",
  "import.warning.type_bc.uncertain_cells":
    "{count} cell(s) flagged as uncertain (doubtful colour and/or ambiguous symbol) — manual correction recommended.",

  "import.warning.type_e.pages_without_axis_numbers":
    "{count} page(s) carrying catalogue images but without usable axis numbers could not be positioned and were skipped.",
  "import.warning.type_e.overlapping_pages":
    "{count} cell(s) where two pages overlap with different images — the last page processed wins.",
  "import.warning.type_e.missing_legend":
    'No DMC colour legend recognised in the PDF: the catalogue images remain unidentified ("Unrecognised symbol").',
  "import.warning.type_e.dimensions_inferred":
    "Dimensions not explicitly stated in the PDF: inferred from the extent of placed images.",
  "import.warning.type_e.dimensions_mismatch":
    "The dimensions stated in the PDF ({declared_columns}×{declared_rows}) don't exactly match the reconstructed extent ({seen_columns}×{seen_rows}) — kept the stated dimensions.",
  "import.warning.type_e.count_match_ambiguous":
    "{count} catalogue image(s) could not be unambiguously matched by exact count (duplicate counts) — fell back to perceptual colour matching, which is less reliable.",
  "import.warning.type_e.unmatched_catalog_images":
    '{count} catalogue image(s) with no matching legend row — added to the palette as "Unrecognised symbol".',

  "import.warning.detection.unexpected_failure":
    "Unexpected failure during automatic detection: {error}",
  "import.warning.detection.manual_config_kept":
    "Configuration was already changed by hand before the analysis finished: the automatic proposal was not applied.",
};
