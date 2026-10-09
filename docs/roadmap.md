# Roadmap — CrossStitchHelper

*Actionable extract of `docs/specification.md` §11. This is the file that gets checked off as work progresses; the specification remains the narrative reference — in case of divergence, it is authoritative on substance, and this file on sequencing.*

Each lot is independently deliverable and usable: there is no lot that is "useless until the next one is done". Lots 0 to 3 form the usable V1. Lots 4 and 5 form the differentiating V2. Lots 6 to 9 are amplifiers.

---

## Lot 0 — Technical foundation

- [x] FastAPI + SQLite + Alembic skeleton
- [x] React/Vite/TypeScript frontend as an installable PWA (manifest + service worker)
- [x] Single Docker image (the backend also serves the built frontend)
- [x] Example `docker-compose.yml` with a data volume
- [x] Test suite and basic continuous integration
- [x] Self-hosting `README.md` (installation, updating, backup)

**Done when:** `docker compose up` gives an application installable on an iPhone home screen, with an empty home page and an API that responds.

> `npm install && npm run build` (frontend) and `pip install -e ".[dev]" && pytest` (backend) have now run for real — a real typing bug was found and fixed along the way (see the history), and the resulting `package-lock.json` is committed. `docker compose up --build` was also verified for real: build, `/api/health` answers `ok`, the built frontend is served at the root, the icons and the PWA manifest respond, and progress survives a `docker compose down` followed by an `up` (the `./data` volume really does all the backup work it claims to do).

---

## Lot 1 — Rendering and tracking core

- [x] Complete data model (`patterns`, `palette_entries`, `grids`, `progress`, `progress_events`) — SQLAlchemy + Alembic migration (`backend/app/models.py`, `alembic/versions/0002_pattern_model.py`), read/sync API (`backend/app/api/patterns.py`), 26 tests (`backend/tests/test_patterns.py`, `test_codec.py`)
- [x] `<canvas>` rendering with its three levels of detail (fills / colour+grid lines / colour+symbol+grid)
- [x] Cell marking (tap, drag, rectangular selection, "all of this colour in the visible area" via the colour filter + area fill)
- [x] Smooth touch pan/zoom (Pointer Events) — drag to pan, zoom by buttons and **two-finger pinch** (`frontend/src/state/useTracker.ts` `zoomTo`, `frontend/src/screens/TrackScreen.tsx`) all done — verified geometrically (midpoint anchoring), by code review, **and by `PointerEvent`s of type `touch` replayed in a real browser** (pinch out and pinch in up to the `MIN_CELL`/`MAX_CELL` bounds, one-finger drag, one-finger tap — no cell checked by accident during a pinch)
- [x] Versioned-delta synchronisation — `frontend/src/state/useSyncedTracker.ts` (local IndexedDB queue → `POST /api/patterns/{id}/progress`, reconciliation via `missing_ops`), verified end to end against a real backend (not just in unit tests)
- [x] Offline cache (IndexedDB via Dexie) — `frontend/src/lib/db.ts`: pattern, last known progress and pending operation queue; `frontend/src/state/usePatternLibrary.ts` falls back server → cache → demo depending on what is available
- [x] 255 × 180 demo grid injected directly into the database for performance tests — `backend/app/seed.py` / `backend/scripts/seed_demo_pattern.py` (procedural pattern, idempotent, never real creative content)

> The complete interface of the five screens has been in place since Lot 0 (port of the mockups). Persistence now exists: the pattern, its grid and progress live in the SQLite database, synchronised by versioned deltas with an offline fallback to IndexedDB. The client demo pattern (`frontend/src/demo/`) remains as the last fallback if neither the server nor the local cache responds (first offline launch, or no backend during development).

**Done when:** you can check cells on 45,900 cells with smooth pan/zoom on iPhone, offline, and find your progress again after a reload and on another device.

**Lot closed.** No physical iOS device is available in this project's development environment (a lasting constraint, not a temporary one): validation of pan/pinch therefore stopped at real touch events replayed in a desktop browser — see above. This is a deliberate fallback, not a perfect substitute for a real finger on a real screen (Safari iOS-specific behaviours, momentum scrolling, `touch-action` — not covered). If a real device becomes available later, all the better; in the meantime, it no longer blocks what follows.

---

## Lot 2 — Universal assisted import

- [x] Wizard: file upload (PDF or image) — selection, sent to `POST /api/imports` (`backend/app/api/imports.py`)
- [x] Page preview and manual cropping of the grid — real raster preview (PyMuPDF for a PDF, Pillow resizing for an image), cropping handles unchanged
- [x] Manual dimension calibration (columns/rows)
- [x] Manual palette entry and filling colours by area — palette editor + `frontend/src/components/ImportGridPainter.tsx` (rectangular selection then painting, reuses the tracking canvas renderer)
- [x] `.cshp` export (documented open format) — `GET /api/patterns/{id}/export`, self-contained ZIP archive (`backend/app/export_cshp.py`), direct link from the Statistics screen

> No automatic detection engine here (no grid type, dimensions, colours or symbols) — that is the whole subject of Lots 4 to 7. The Lot 2 wizard pre-fills what it technically can (the page preview), the user does the rest by hand, like any computer-assisted paper chart editor.

**Done when:** any PDF or image can be turned into a trackable pattern, entirely by hand. At this point, the application is already a credible alternative to Pattern Keeper. **Done** — verified end to end (real upload → cropping → dimensions → palette → area painting → trackable, synchronised pattern) by `frontend/e2e/lot2-manual-import.spec.ts` against a real backend, not just in unit tests.

> **Changed in Lot 7:** the photo capture button (direct access to the mobile camera) was removed from the wizard, along with the abandonment of type D — see below and `docs/specification.md` §4.4/§13. Dropping an existing image (file picker) is still possible and still follows exactly this manual path.

---

## Lot 3 — Statistics and tracking comfort

- [x] Complete statistics (overall/per-colour progress, estimated skeins, history) — overall/per-colour progress had been real since Lot 1; the history (`stats.activity`, recent sessions) was the last to be fake (`DEMO_ACTIVITY`/`DEMO_SESSIONS` hard-coded in `App.tsx`) — replaced by `GET /api/patterns/{id}/activity` (`backend/app/activity.py`), which aggregates `progress_events` (already written on every sync since Lot 1) rather than duplicating a second history
- [x] Colour filtering (highlighting, dimming the others) — already real since Lot 1 (`useTracker.highlight`, dimming in `pattern/render.ts`)
- [x] Hiding cells already done — new button in the Tracking toolbar (`useTracker.hideDone`), renders a done cell as bare fabric rather than washed out
- [x] Current row/column highlighting — already real since Lot 1 (`drawOverlay` crosshair, `pattern/render.ts`)
- [x] Multi-level undo — already real since Lot 1 (16-state stack in `useTracker.ts`)

**Done when:** the four initial needs (import, tracking, exact colour per cell, stats) are covered, even if import remains manual. **End of V1.**

**Lot closed.** Verified by `frontend/e2e/lot3-stats-and-comfort.spec.ts` against a real backend: a checked area shows up in a real session history (not the fake data), hiding really changes the rendered canvas pixels, and undo goes back over two gestures in a row (not just one).

---

## Lot 4 — Automatic type A extraction

- [x] Structural analysis of PDFs (fonts, rectangles, characters, text) — `backend/app/type_a.py`, symbol font detected by geometry (regular tiling), never by a hard-coded font name
- [x] Grid detection (regular tiling, grid pitch, dimensions) — dimensions stated plainly by the PDF preferred over the reconstructed extent (§7.2 step 6), with a fallback and a warning otherwise
- [x] Embedded symbol font parser (Cafe Brasserie style) — grid/legend matching key = (glyph, colour of the small rectangle under the glyph), not the glyph alone: this reference file reuses the same glyph for two different colours depending on the stitch type (see the engine commit)
- [x] Text legend parser ("Floss Used for…") — symbol → DMC code → name table, from the real text of the "Full Stitches" section
- [x] Multi-page assembly by axis numbers — 8 grid pages stitched back together via the column/row numbers printed in the margin, with a reading-order fallback (reduced confidence + warning) if a page has no usable ones

**Done when:** the `fixtures/cafe-brasserie-charting-export/` PDF imports by simply accepting the proposals, and the per-colour counts obtained match those on its page 11 (see `fixtures/README.md`). **Done** — the legend's 34 colours match exactly the counts on page 11 "Usage Summary" (re-parsed from the PDF on every test run, never copied by hand), verified both in unit tests (`backend/tests/test_type_a.py`) and end to end against a real instance (`frontend/e2e/lot4-automatic-detection.spec.ts`: upload of the real PDF → dimensions and palette already pre-filled → validation without building anything by hand → trackable pattern). No regression on the other five fixtures (types B/C/E): `detect_type_a` cleanly steps aside (`None`) on each, no false positive.

**Lot closed.** Detection runs as a background task (`BackgroundTasks`) rather than in the upload request — necessary in practice: analysing this fixture (11 pages) took 41.6 s before a performance fix (spatial indexing of colour rectangles rather than a per-glyph scan, see the history), and still takes ~9.5 s after, still too long for a synchronous HTTP request. The Lot 2 manual path remains fully available and is never forcibly bypassed — a correction painted by hand always wins over the automatic proposal.

---

## Lot 5 — Automatic type B and C extraction

- [x] Colour extraction from rectangle fills (CMYK/RGB handling)
- [x] Lab matching against the DMC palette
- [x] Measuring vector-path density per page to decide whether a two-page overlay is needed (never assume "page 1 = colour, page 2 = symbols" by default — see `docs/specification.md` §4.3, Summer Flight case)
- [x] Twin-grid overlay when it turns out to be needed
- [x] Vector symbol recognition with a confidence score
- [x] Explicit manual fallback when the score is insufficient

**Done when:** the four DMC fixtures (`winter-wreath-dmc`, `botanical-citrus`, `cucurbit`, `summer-flight`) each import with their correct colours, the right page strategy detected automatically, and explicit flagging of uncertain cells. **End of V2.**

**Lot closed.** `backend/app/type_bc.py` measures path density per page before deciding on an overlay — a counter-intuitive finding, measured (not assumed): `winter-wreath-dmc` behaves like the trap case `summer-flight-dmc` (its colour page already carries its symbols), only `botanical-citrus-dmc` and `cucurbit-dmc` overlay a genuine second page. `summer-flight-dmc` honestly falls back to type B (shape recognition too fragmented on its shaded illustration) rather than producing an unusable palette. Community DMC→RGB colour catalogue in `backend/app/dmc_catalog.py` (228 shades), distinct from `app/dmc_colors.py` (type A, where the legend text is already authoritative). Uncertain cells (`uncertain_cells`) are flagged both in the detection banner and by a visual marker on each affected cell in the wizard's brush (`ImportGridPainter`, `pattern/render.ts`).

---

## Lot 6 — Reusable recipes

- [x] File fingerprint computation (fonts, header text patterns, geometry — never the creative content)
- [x] Saving a validated configuration as a recipe
- [x] Automatic re-application on a file with the same fingerprint
- [x] Local recipe library management

**Done when:** re-importing a second PDF from the same publisher automatically reuses the cropping already validated, without going through the manual cropping step again.

**Lot closed.** `backend/app/fingerprint.py` computes the fingerprint from the page size, the embedded fonts (PDF subset prefix removed — never stable from one export to the next) and generic charting-software labels found in the text ("Floss Used for", "Symbol"... never the pattern's title). Verified against the six reference fixtures: `botanical-citrus-dmc` and `cucurbit-dmc`, two real official DMC charts with the same export template but different patterns, get the **same** fingerprint (a measured finding, not engineered — see `backend/tests/test_fingerprint.py`); the other four fixtures each remain distinct. It is this real pair, not a synthetic fixture, that serves as the end-to-end case for Lot 6 (`backend/tests/test_recipes.py`, `frontend/e2e/lot6-recettes.spec.ts`).

A recipe (`backend/app/models.py::Recipe`, `backend/app/api/recipes.py`) carries only `crop_by_page` — never the dimensions or the palette, content specific to each pattern even within the same publisher (cf. Winter Wreath/Summer Flight vs Botanical Citrus/Cucurbit above): see the clarification settled in specification §8.7. Automatic matching runs in the same background task as type A/B/C detection (`_run_auto_detection`, `backend/app/api/imports.py`) rather than in the upload request — the fingerprint had at first been computed there by mistake before this move, a bug found thanks to a regression observed on the Lot 4-5 e2e suites run in parallel (locally), then confirmed in CI ("Docker image + e2e" job going from ~9 min to ~20 min). Moving it alone was not enough: `app/fingerprint.py` initially used `pdfplumber` (like `app/type_a.py`) to list the fonts, whose `page.chars` rebuilds a per-glyph layout even for a simple list of names — measured at ~2 s **per page** on `cafe-brasserie-charting-export` (dense symbol font), i.e. ~14 s over its eleven pages alone, an addition of more than double the detection time already in place. Replaced with PyMuPDF (`page.get_fonts()`/`page.get_text()`, no geometric reclustering): under 0.15 s on the same file, with nothing lost in discriminating the six reference fixtures (`backend/tests/test_fingerprint.py`). A recipe never overwrites cropping already started by hand. Library managed from the frontend's Settings screen (list, delete); offered for saving at the import wizard's summary step.

---

## Lot 7 — Grids made of reused bitmap images (type E)

Type D (free-form scan/photo, full-frame computer vision) was removed from this lot and abandoned before any implementation started — see `docs/specification.md` §4.4/§13 (decision of 2026-09-18): no real reference file to verify it, unlike every other type, and a vision problem far more open-ended than the rest of the extraction engine. The photo capture button is removed from the wizard (Lot 2); the universal manual import remains available for any image dropped otherwise.

**Type E — grids composed of reused bitmap images** (see `docs/specification.md` §4.3 and §4.4, River And Mountains case):
- [x] Detection and exclusion of photorealistic preview pages (not working charts)
- [x] Extraction of the catalogue of distinct images reused on grid pages (20 on the reference fixture, not the ~531 initially assumed — see below)
- [x] Classification of each catalogue image into (colour, symbol) — a closed classification problem over a small catalogue, simpler than free-form recognition
- [x] Repositioning each cell from those images' placements

**Done when:** the `fixtures/river-and-mountains-laserarts/` PDF imports with its correct colours and symbols, without its photorealistic preview page being taken for a grid page.

**Lot closed.** `backend/app/type_e.py` tells a grid page from a page to exclude by structural measurement (dominant, near-square image size) rather than by assumed position: page 1 (photorealistic preview) mixes two image sizes for an impasto-style texture rendering (only 69.8% at the dominant size, versus 100% on a real grid page), and page 18 (page assembly map, not a working page) places much larger, non-square images — two widely separated regimes, never a threshold tuned by guesswork. Multi-page assembly by axis numbers (same mechanism as type A) over the 15 remaining grid pages.

**Correction measured along the way, not assumed** (`docs/specification.md` §4.3, `fixtures/README.md`): the reference fixture's image catalogue actually contains **20** distinct images, not ~531 as documented before this lot — 531 was the number of *placements* on a single page, confused with a number of distinct images. These 20 images match exactly the 20 DMC colours in its text legend (page 17, exact counts per colour — the same ground-truth role as page 11 of `cafe-brasserie-charting-export` in Lot 4). Notable finding: matching each image's background colour to the nearest DMC code turns out to be unreliable on this file (12 of the 20 misidentified, measured) — the signal actually used by `detect_type_e` is each image's total number of placements, which matches exactly the stitch count declared by the legend for each colour; perceptual colour (`nearest_dmc_among`, `backend/app/dmc_catalog.py`) only serves as an explicit fallback, flagged uncertain, for images the count cannot tell apart unambiguously.

---

## Lot 8 — Finishing touches

Sub-projects independent enough to be delivered as separate PRs (decision of 2026-09-18) rather than as one big commit.

- [x] Full fractional and special stitches in the interface (quarter, half, backstitch, French knot, beads)
- [x] Data backup/restore
- [x] Dark theme
- [x] Complete FR/EN translations

> **Community recipe sharing removed from scope (decision of 2026-09-18):** mentioned as a possibility in specification §8.7, never a commitment. The user has no use for it — the recipe library stays local (Lot 6), full stop.

**Fractional and special stitches — done.** Progress model extended to five categories (`backend/app/models.py::Progress.bitmap_half`/`_quarter`/`_backstitch`/`_knots`, migration 0005) instead of one, each with its own index space — never shared between categories. `stitched_count`/the overall percentage remain based on full stitches only (§7.1, unchanged). Coordinate convention settled for `Grid.backstitch_json`/`french_knots_json` (never specified before this lot): cell corners for a segment, cell centre for a knot — see `backend/app/schemas.py::BackstitchSegment`/`FrenchKnot`. Canvas rendering and touch interaction added (`frontend/src/pattern/render.ts`, `state/useTracker.ts`, new category selection bar in `TrackScreen.tsx`): backstitch/knots interactive only from the same zoom threshold at which symbols appear (`SYMBOL_MIN_CELL`), a cell below it being too few pixels to tell two neighbouring elements apart with a finger. **Correction after real-use feedback (2026-09-20)**: rendering, however, must not depend on that threshold — on a paper diagram, backstitch stays visible even on a zoomed-out overview. Only the interaction (checking) remains reserved for close zoom; `frontend/src/pattern/render.ts` was fixed accordingly (see `frontend/e2e/backstitch-visible-zoomed-out.spec.ts`). Beads: already covered by the existing full-stitch mechanism (`PaletteEntry.count_beads`) — a "bead" cell is a `layer_full` cell whose referenced palette entry represents a bead, never a separate geometry or index space, so nothing new to build for this particular category. No extraction connector produces this data from a real PDF yet (Lot 9, not started): the demo pattern (`backend/app/seed.py`) now carries a small synthetic content in all four categories so the feature is genuinely verifiable in the meantime.

**Data backup/restore — done.** A single JSON document (`backend/app/backup.py`, `csh-backup` format) covers the whole instance — all patterns, their palette, their grid, their progress (the five categories from the previous sub-project included), the `progress_events` log (without it the activity history, §11, would vanish on restore) and the reusable recipes (Lot 6). Deliberately out of scope: `ImportJob` (transient state of an import wizard in progress, never durable data) and `AppMeta` (internal bookkeeping). Two new routes (`backend/app/api/backup.py`): `GET /api/backup` (direct download, `Content-Disposition` header like the Lot 2 `.cshp` export) and `POST /api/backup/restore`, a **full replacement** — never a merge, the expected semantics of a restore — which the settings' "Clear all data" button reuses as is with an empty document rather than duplicating a separate deletion logic. Daily automatic backup (`backend/app/auto_backup.py`): an asyncio loop inside the application process (no new infrastructure dependency — `CLAUDE.md`: "no multi-service installation"), toggled from the settings (`AppMeta`, a server setting, not a browser preference), a snapshot written to `data/backups/` at every startup then every 24h, keeping only the 14 most recent (older ones purged on every write). On the frontend side (`frontend/src/screens/SettingsScreen.tsx`), a restore or a wipe also empties the offline cache (`frontend/src/lib/db.ts::clearOfflineCache`) before reloading the page — without that, a queue of pending progress operations (`pendingOps`, offline) could replay a stale change on top of the freshly restored data.

**Dark theme — done.** The infrastructure (`frontend/src/lib/theme.tsx`, `data-theme` attribute, ported from the mockups) already existed but was incomplete: audited case by case (numbered CSS variables consumed directly outside the already-covered `.tag-*` classes, hard-coded colours) rather than assumed correct. Three real bugs found and fixed (`frontend/src/index.css`): `--color-neutral-200`/`-300`/`-400` and `--color-accent-700` had no dark override (a thumbnail inset and the text of the "Clear all data" button stayed in their light shades, the latter almost unreadable on a dark background); `.crop-stage` (import wizard) had a hard-coded `#cfc4ae` background rather than a variable. Canvas rendering (`pattern/render.ts::readGridTheme`, `--canvas-fabric`/`-ground`/`-ink`) already followed the theme correctly, verified rather than assumed. Flash of the wrong theme on load fixed: a blocking script in `frontend/index.html` applies `data-theme` and the system bar colour (`<meta name="theme-color">`, until then driven only by the system preference, never by an explicit choice disagreeing with it) before the first render, deliberately duplicating the logic of `theme.tsx` — no CSS variable is loaded yet at that point to factor it any other way.

**Complete FR/EN translations — done.** The infrastructure (`frontend/src/i18n/`, compile-time guard between `fr.ts`/`en.ts`) already guarantees that no key is missing on either side — the audit therefore focused on what that guard cannot see. Three categories of real bugs found and fixed, none assumed: (1) `frontend/src/screens/StatsScreen.tsx` built its `Intl.DateTimeFormat`/`RelativeTimeFormat` formatters with the **browser's** locale rather than the language chosen in Settings (weekdays and relative dates in the statistics could show in the wrong language despite an explicit choice) — centralised in `frontend/src/lib/format.ts` (`useWeekdayLabel`, `useSessionRelativeTime`), with `<html lang>` now applied from the blocking script in `index.html`, like the theme; (2) a much wider discovery than expected: **all** API error messages (18 `HTTPException` sites) and **all** automatic detection warnings (21 sites in `type_a.py`/`type_bc.py`/`type_e.py`, plus 2 in `api/imports.py`) were hard-coded French strings on the server side, displayed as is on the client even in English — restructured into `code` + `params` (`backend/app/schemas.py::ApiErrorDetail`/`DetectionWarning`), translated on the client (`frontend/src/lib/api.ts::translateApiError`/`translateDetectionWarning`, keys `error.<code>`/`import.warning.<code>`) with an explicit fallback if a code is unknown to the frontend, never a crash. The restructuring of the extraction engine (delegated to the `pdf-extraction-specialist` agent, verified independently by a full review of the diff, clean `ruff`/`mypy`/`pytest`, and re-measurement on the six real fixtures: dimensions, palette, confidence, uncertain cells and number of warnings strictly identical before/after, only the format changes) illustrates the project's guiding principle — measure rather than assume, even for a fix that has nothing to do with extraction itself. A real bug found along the way by a systematic check of parameter names: `error.import_file_too_large` used `{maxMb}` on the translation side against `max_mb` sent by the server (camelCase vs snake_case), which would have left the text uninterpolated.

---

## Lot 9 — Special stitch extraction (backstitch, knots, fractional)

Spotted while testing Lot 5 for real on `cafe-brasserie-charting-export`: some PDFs draw backstitches (lines) and French knots (small isolated shapes) directly on top of the counted-stitch grid — `backstitch_json`/`french_knots_json` already exist in the data model (§6.2) but no connector (A/B/C) ever fills them today, they always stay empty. Lot 8 assumes this data is already present to complete the tracking *interface* (checking a backstitch) — this lot is what actually produces it from the PDF.

- [x] Detection of backstitch paths: a line that **crosses several cells** (unlike a full-stitch symbol, always contained in a single cell, and the printed grid, always axis-aligned — see `backend/app/type_bc.py::_is_grid_ruling`, generalised in `backend/app/grid_lines.py` rather than duplicated)
- [x] Detection of French knots: small isolated shape, not aligned with the regular tiling of coloured cells
- [x] Distinction between **decorative** backstitch (text or border of a cover/legend page, outside the working grid) and **real** backstitch (part of the pattern, to be flagged to the thread) — never extract the former as if it had to be stitched
- [x] Type A: cross-check with the legend tables already present but ignored since Lot 4 ("Floss Used for Backstitch"/"French Knots", distinct from "Full Stitches") to validate the counts, as already done for full stitches (§7.3)
- [x] Explicitly verify (existing fixtures, not just new ones) that this extraction never degrades the full-stitch recognition already in place (Lots 4-5) — a backstitch crossing a cell of the type B/C symbol grid must never wrongly turn that cell into an uncertain cell

**Done when:** the backstitches and French knots documented in the legend of `cafe-brasserie-charting-export` are extracted with counts consistent with that legend, checkable in tracking (Lot 8), without any decorative off-grid backstitch being imported as part of the pattern to stitch.

**Lot 9 done.** Third and final stage of the type A extraction engine (`backend/app/type_a.py`): all five legend sections ("Full/Half/Quarter Stitches", "French Knots", "Back Stitches") are now parsed, not just the first — a colour declared in several sections (e.g. DMC 742: full stitch + backstitch + knot) keeps a single palette index. Colour→DMC matching by **exact colour** of the legend's vector swatch (measured identical to the pattern's stroke, RGB to RGB — a Lab-distance fallback exists but proved measurably unreliable: 938/3031 confusions, never assigning 310) rather than by symbol font, since those two sections have none. Backstitch/grid-ruling distinction generalised in `backend/app/grid_lines.py` (extracted from `type_bc.py::_is_grid_ruling`, Lot 5 behaviour preserved bit for bit with no length criterion): a backstitch also starts from a cell corner like a ruling, only length and orientation (diagonal, never possible for a ruling) really tell them apart. A backstitch is drawn twice in this fixture (dark pass + lighter pass): deduplicated. Each grid page also carries washed-out shades from the overlap strip duplicated with the neighbouring page — never counted, exact-colour matching naturally excludes them since they match no legend swatch. Quarter stitches (4 cases, DMC 3031) cannot be told apart by glyph+background colour (identical to those of the full stitch): only their off-centre position in the cell (measured, never an assumed tiling) identifies them. Backstitch length converted to cm only when the user has entered a fabric count at validation (`ImportRecapForm`) — never a conversion invented without it; the fabric count read from the PDF text ("Fabric: Aida 16") pre-fills this field without ever imposing it (`ImportConfig.detected_fabric_count`, `frontend/src/screens/ImportScreen.tsx`). No manual correction UI for these four detected layers (unlike `detected_cells`+`fills` since Lot 2): out of scope for this lot, which covers detection only — a manual correction after import is still done directly by checking/unchecking from tracking (Lot 8). Verified against the reference fixture (`backend/tests/test_type_a.py`, values re-parsed independently from page 11 "Usage Summary" — including the "Back(cm)" column, actually in **inches**, measured at under 0.1% deviation over the 8 codes) and against the other five fixtures (no regression, `backend/tests/test_type_bc.py`/`test_type_e.py`/`test_grid_lines.py`, 82 extraction tests). Work delegated to the `pdf-extraction-specialist` agent for the extraction engine proper (`type_a.py`, `grid_lines.py`), verified independently (diff fully reviewed, `ruff`/`mypy`/six fixtures re-measured); wiring into the validation pipeline (`backend/app/api/imports.py::commit`, `ImportConfig`/`ImportConfigPatch`) and pre-filling the fabric count in the wizard were done separately, verified by an end-to-end test (`frontend/e2e/lot9-special-stitches-extraction.spec.ts`) against the real fixture.
