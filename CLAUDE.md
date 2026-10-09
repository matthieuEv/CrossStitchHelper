# CLAUDE.md — guide to working on CrossStitchHelper

This file is the entry point for any Claude Code session working on this repository. Read it before starting, and re-read `docs/specification.md` before any architecture decision not covered here.

## In one sentence

CrossStitchHelper is a free, open-source, **self-hosted** web app (PWA) that turns a cross-stitch chart PDF into a trackable pattern, with cell checking, exact colour per cell and statistics. Primary target: iPhone/iPad via Safari.

## Reference documents (read in this order)

1. `docs/features-and-limits.md` — what the app does and never does, in plain language. Serves as a scope guard: if a requested feature is not in it, check before adding it.
2. `docs/specification.md` — the full specification: architecture, data model, API, extraction engine, non-functional requirements, decisions made. **It is the technical source of truth.**
3. `docs/roadmap.md` — split into independently deliverable lots, with "done when" criteria. Always place a task within its lot before starting it.

Never duplicate or rephrase the content of these documents elsewhere in the code (no second roadmap in a subfolder README, for example) — one place per piece of information.

## Non-negotiable decisions (condensed reminder — details in specification §3 and §13)

- **Everything self-hosted.** No mandatory network call to a third-party service. No telemetry.
- **Separate frontend + backend.** Heavy computation (PDF parsing, vision) stays server-side (Python/FastAPI). The React client must never embed heavy PDF processing.
- **Tracking progress is stored separately from the source grid.** Never change the structure of `grids` and `progress` in a coupled way — a re-import must never be able to overwrite existing progress.
- **No pattern content is ever shared between users**, neither in import "recipes" (which contain only geometric/structural parameters) nor anywhere else.
- **The source PDF is not kept** beyond extraction, unless the user explicitly enables the option.
- **No multi-service installation.** No Redis, no Postgres, no task broker. SQLite + one application container. Any proposal to add an infrastructure dependency must be justified by a real need, not by habit.
- **Grid rendering is in `<canvas>`, never one DOM element per cell.** A reference pattern has 45,900 cells (see `fixtures/`) — every rendering component must be tested with a pattern of that size before being considered done.
- **All documentation, code comments and docstrings are written in English** (decision of 2026-09-24, specification §13). User-facing strings are unaffected: they go through i18n, French and English.

## Repository layout

```
backend/        FastAPI API, PDF extraction engine, SQLite database
frontend/       React/TypeScript PWA, canvas rendering, import wizard
docs/           specifications (see above)
fixtures/       reference PDFs for extraction tests (see below)
.claude/
  agents/       specialised sub-agents for this repository
  skills/       reusable procedures (adding a connector, verifying fixtures)
```

`backend/` and `frontend/` were empty at the start of Lot 0 — see `docs/roadmap.md`.

## Reference test set (`fixtures/`)

Six real PDFs serve as ground truth for the whole extraction engine, covering the four active types A/B/C/E from `docs/specification.md` §4.4 (type D was abandoned, see below). Every parser change must be verified against these known values before being considered correct — full details in `fixtures/README.md`.

- **`cafe-brasserie-charting-export/` — type A.** Custom embedded font (one glyph = one symbol), complete text legend. Expected dimensions: 255 × 180 cells, 34 colours, exact per-colour counts on page 11.
- **`botanical-citrus-dmc/`, `cucurbit-dmc/` — type C, clean overlay.** Two DMC charts where the colour page has few vector paths and the symbol page has many — the two-page split is reliable.
- **`winter-wreath-dmc/`, `summer-flight-dmc/` — type C, trap case.** Same DMC visual template as the two fixtures above, but **the colour page itself already carries its symbol paths** (measured in Lot 5, not visible to the eye for `winter-wreath-dmc` — see `fixtures/README.md`): never assume "page 1 = colour only" without measuring path density per page first. These two files must make any connector that blindly makes that assumption fail.
- **`river-and-mountains-laserarts/` — type E.** Third-party publisher, entirely different structure: the grid is made of small reused bitmap images (colour + symbol already combined in each image, 20 distinct images measured in Lot 7 — not the ~531 first assumed, see `docs/roadmap.md`), no coloured rectangles or vector paths. Page 1 (photorealistic preview) and page 18 (page assembly map) are excluded from extraction by structural measurement, not by assumed page position.

**Lesson to remember:** even within a single publisher (DMC) and an identical visual template, the internal structure varies from one file to the next (`winter-wreath-dmc`/`summer-flight-dmc` vs `botanical-citrus-dmc`/`cucurbit-dmc`) — and that real structure is not always what a first look at the PDF suggests, `winter-wreath-dmc` being the direct proof. Never code an extraction heuristic that assumes a fixed structure without verifying it on the file at hand — always measure before deciding.

Before considering a change to the extraction engine done, run the `verify-extraction-fixtures` skill procedure (see `.claude/skills/`).

## Code conventions

- **Backend**: Python 3.12, FastAPI, `pdfplumber`/`PyMuPDF` for extraction, SQLAlchemy + Alembic for the database, strict typing (clean mypy), tests with `pytest`.
- **Frontend**: strict TypeScript, React, hand-written `<canvas>` grid rendering (no heavy generic virtualised-grid dependency — the level-of-detail logic is domain-specific).
- **Documentation and comments**: English only, everywhere — Markdown docs, code comments, docstrings, agent and skill definitions.
- **User-facing strings**: always go through i18n keys (French + English from the start), never hard-coded text in components.
- **Commits**: messages in French or English as you prefer, but consistent within a lot; reference the `docs/roadmap.md` lot number when relevant.
- **Tests**: any feature touching extraction or the grid data model must have a test using the fixtures above.

## Current status

**Lots 0 and 1 done.** The FastAPI + SQLite + Alembic backend, the React/TypeScript PWA frontend, the single Docker image, CI and the self-hosting README are in place. The five mockup screens are implemented and tracking is genuinely interactive (checking, panning, zoom including two-finger pinch, colour filter, area selection, undo), persisted in the database and synchronised between devices by versioned deltas (`backend/app/api/patterns.py`), with an offline fallback to IndexedDB (`frontend/src/state/useSyncedTracker.ts`). **No physical iOS device is available in this development environment** (a lasting constraint): pan/pinch is validated by real touch events replayed in a desktop browser, not on a real iPhone — see `docs/roadmap.md` Lot 1 for exactly what that covers and does not cover.

**Lot 2 done.** The import wizard (`backend/app/api/imports.py`, `frontend/src/screens/ImportScreen.tsx`) really reads the dropped file: real raster preview (with page navigation for a multi-page PDF), cropping, dimensions, palette and painting by area by hand (`frontend/src/components/ImportGridPainter.tsx`, reuses the tracking canvas renderer), up to a genuinely trackable pattern. No automatic detection — that remains Lots 4 to 7. `.cshp` export available from the Statistics screen. `frontend/src/demo/` remains useful beyond that: it is the offline first-launch fallback when neither the server nor the IndexedDB cache has a pattern yet.

**Lot 3 done — end of V1.** Statistics (`frontend/src/screens/StatsScreen.tsx`) are now entirely real: the activity history comes from `GET /api/patterns/{id}/activity` (`backend/app/activity.py`), which aggregates the `progress_events` log already written on every sync (Lot 1) rather than duplicating a second history. Colour filtering, row/column highlighting and multi-level undo already existed since Lot 1; the only genuinely new comfort addition is hiding cells already stitched (`useTracker.hideDone`, button in the Tracking toolbar).

**Lot 4 done — start of V2.** First automatic extraction engine (`backend/app/type_a.py`, type A — structured software export with an embedded symbol font). Runs as a background task (`BackgroundTasks`, `POST /api/imports`) rather than in the request: structural analysis of a real PDF takes several seconds, never suited to a synchronous HTTP request (specification §5.2). The result only pre-fills the same editable configuration as in Lot 2 (`ImportConfig.detected_cells`, under the areas painted by hand via `apply_fills(..., base=...)`) — never an imposed result, a manual correction always wins. Verified against the six reference fixtures: the 34 colours of `cafe-brasserie-charting-export` match exactly the counts on its page 11, and `detect_type_a` cleanly steps aside (no false positive) on the five fixtures of another type.

**Lot 5 done.** Second automatic extraction engine (`backend/app/type_bc.py`, types B/C — DMC vector charts without a symbol font). `POST /api/imports` tries `detect_type_a` then, if it recognises nothing, `detect_type_bc` (`_run_auto_detection`, `backend/app/api/imports.py`): a single detection result per file. Each cell's colour comes from a vector rectangle's fill, matched against `backend/app/dmc_catalog.py` (community DMC→RGB catalogue, 228 shades, distinct from type A's `app/dmc_colors.py`) by Lab distance — never raw RGB. Vector-path density is measured per page before deciding on a two-page overlay: measured (not assumed) finding that `winter-wreath-dmc` behaves like the trap case `summer-flight-dmc` (its colour page already carries its symbols), only `botanical-citrus-dmc` and `cucurbit-dmc` genuinely overlay a second one. `summer-flight-dmc` honestly falls back to type B (shape recognition too unreliable on its shaded illustration) rather than producing an unusable palette. Uncertain cells (`ImportConfig.uncertain_cells`) are flagged both in the detection banner and by a visual marker on each affected cell in the wizard's brush.

**Lot 6 done.** Reusable recipes (`backend/app/fingerprint.py`, `backend/app/api/recipes.py`): a file fingerprint (page size, embedded fonts without their subset prefix, generic charting-software labels — never the creative content) associated with a recipe that carries only `crop_by_page`, never a pattern's dimensions or palette (content specific to each file, even within the same publisher — cf. Winter Wreath/Summer Flight vs Botanical Citrus/Cucurbit above). Verified with those last two fixtures, which really do get the same fingerprint (same official DMC export template, different patterns): no synthetic pair engineered for the occasion. Automatic matching runs in the same background task as type A/B/C detection, never in the upload request — two real performance bugs were found and fixed before the lot ended: the fingerprint computation initially synchronous in the request, then, once moved, still too slow (`pdfplumber` rebuilds a per-glyph layout, ~14 s on the Cafe Brasserie fixture) and replaced with PyMuPDF (`get_fonts()`/`get_text()`, no geometric reclustering, <0.15 s).

**Lot 7 done.** Third automatic extraction engine (`backend/app/type_e.py`, type E — closed catalogues of reused bitmap images, third-party publishers). `POST /api/imports` tries `detect_type_a`, then `detect_type_bc`, then as a last resort `detect_type_e`. Type D (free-form photo, computer vision) was **abandoned before any implementation** — decision of 2026-09-18 (`docs/specification.md` §4.4/§13) for lack of a real reference file to verify it; the photo capture button was removed from the import wizard, which otherwise remains universal for any dropped image. Grid page detected by structural measurement (dominant, square image size), never by assumed page position. Image → DMC colour matching by exact placement count (primary signal, verified reliable) rather than by perceptual colour alone (explicit fallback, flagged uncertain): measured as clearly less reliable on the reference fixture. Correction measured along the way: this fixture's image catalogue really contains 20 distinct images, not ~531 as documented before this lot.

**Lot 8 done** ("Finishing touches" — four fairly independent sub-projects delivered as separate PRs, decision of 2026-09-18; community recipe sharing was removed from it, the user has no use for it). Fractional and special stitches **done**: the progress model now tracks five categories (full stitch, 1/2, 1/4, backstitch, knot) instead of one, each with its own bitmap and its own index space (`backend/app/models.py::Progress`) — the overall completion percentage remains based on full stitches only. Canvas rendering and touch interaction added (`frontend/src/pattern/render.ts`, `state/useTracker.ts`): backstitch/knots stay **visible at every zoom level** (fixed on 2026-09-20 after real-use feedback — as on a paper diagram), only the interaction (checking) remaining reserved for the same zoom threshold at which symbols appear. Data backup/restore **done**: a single JSON document (`backend/app/backup.py`, `GET`/`POST /api/backup*`) covers the whole instance — patterns, palette, grid, progress (the five categories above included), activity log and recipes — never `ImportJob` (transient) or `AppMeta` (internal bookkeeping). A restore is a full replacement, never a merge; "Clear all data" (settings) reuses the same mechanism with an empty document. Daily automatic backup as a background task of the process (`backend/app/auto_backup.py`, no extra infrastructure dependency), toggled from the settings. Dark theme **done**: the infrastructure already existed (ported from the mockups) but was incomplete — audited case by case rather than assumed correct, three real bugs fixed (`frontend/src/index.css`) and the flash of the wrong theme on load eliminated by a blocking script in `frontend/index.html`. FR/EN translations **done**: the compile-time guard between `fr.ts`/`en.ts` already guarantees no key is missing, so the audit focused on what it cannot see — `Intl` locale following the browser rather than the chosen language (`StatsScreen.tsx`, fixed), and above all **all** API error messages and **all** automatic detection warnings (type_a/bc/e) that were hard-coded French strings on the server side: restructured into `code` + `params` (`backend/app/schemas.py::ApiErrorDetail`/`DetectionWarning`), translated on the client (`frontend/src/lib/api.ts`). The extraction engine restructuring was delegated then verified independently (diff fully reviewed, clean tests, six real fixtures re-measured identical before/after).

**Lot 9 done.** Fourth and final type A extraction engine stage (`backend/app/type_a.py`): backstitches, knots and fractional stitches (1/2, 1/4) are now extracted from the PDF, not just the full stitches since Lot 4 — all five legend sections are parsed, a colour declared in several sections (full stitch + backstitch + knot) keeping a single palette index. Colour→DMC matching by exact colour of the legend's vector swatch (measured identical to the pattern's stroke) rather than by symbol font, since those two sections have none. Backstitch/grid-ruling distinction generalised in `backend/app/grid_lines.py` (extracted from `type_bc.py::_is_grid_ruling`, Lot 5 — behaviour preserved bit for bit): a backstitch also starts from a cell corner, only length and diagonal orientation (never possible for a ruling) really tell them apart. Length converted to cm only if the user has entered a fabric count; the one read from the PDF text pre-fills that field without ever imposing it (`ImportConfig.detected_fabric_count`). No manual correction UI for these detected layers, unlike `detected_cells`+`fills` since Lot 2 — out of scope, a correction is still possible by checking from tracking (Lot 8). Verified against the six reference fixtures (82 extraction tests, no regression on types B/C/E) and by an end-to-end test (`frontend/e2e/lot9-special-stitches-extraction.spec.ts`).

The installation chain (`npm install`, `pip install`, `docker compose up --build`) has now run for real — see `docs/roadmap.md` for the details of what was verified.

See `docs/roadmap.md` for what comes next.

## What porting the mockups settled

- **The design system lives in `frontend/src/index.css`**, as CSS variables. Canvas rendering reads these variables back (`readGridTheme`): never write a theme colour hard-coded in JavaScript.
- **The mockups loaded Caprasimo and Figtree from Google Fonts.** Replaced with system font stacks, because a self-hosted instance must not depend on any third-party service or stop working offline. To get the original typography back, self-host the `.woff2` files (procedure in `frontend/README.md`).
- **The mockups distinguished iPhone and iPad by a prop; the application follows the available width** (`useWideLayout`, 768 px threshold), so that an iPad's Split View is treated as the narrow screen it is.
- **No hard-coded string in a component.** Adding a key to `src/i18n/fr.ts` breaks compilation until `en.ts` is completed: this is the guard that prevents a translation from silently going missing.
