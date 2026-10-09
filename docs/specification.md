# Specification — CrossStitchHelper

*Version 1.0 — 2026-09-13. This document replaces the initial discovery note: it keeps every actionable finding from it and turns them into build specifications. It is the reference for building the application.*

---

## 1. Goal

CrossStitchHelper is a free, open-source, self-hostable web application that lets a stitcher:

1. **import** a cross-stitch chart as a PDF (or image) and convert it into usable structured data (a "machine file");
2. **track their progress** by checking off cells as they stitch;
3. **know exactly which colour goes in which cell**, with reliable row-by-row orientation;
4. **view statistics** on progress and thread consumption.

The product targets real-world use on **iPhone and iPad** (stitching in hand, phone alongside), without going through the App Store.

### Positioning

The closest commercial equivalent is Markup R-XP (paid, closed, ~£15/year), which claims automatic symbol and colour detection with no public documentation of its reliability. Pattern Keeper, the free reference, detects nothing: the user aligns a grid themselves and reads colours by eye off the original PDF.

CrossStitchHelper differentiates itself with a **transparent semi-automatic import**: the application pre-fills everything it can guess, and the user fixes whatever is wrong in a step-by-step wizard. Neither a black box nor manual drudgery. A defunct third-party app (Cross Stitch Markup) provides the opposite lesson, not to be repeated: it depended on an unobtainable proprietary `.chart` format — we must accept the file the user actually has in hand.

---

## 2. Scope

### 2.1 Included

| Area | Content |
|---|---|
| Import | Vector PDF (software export and editorial publication), image/scan in assisted mode, step-by-step correction wizard, multi-page assembly |
| Grid | Full stitches, half stitches, quarter stitches, backstitches, French knots, beads |
| Tracking | Checking cell by cell, by area, by colour; undo; multi-device resume |
| Colours | DMC palette (codes, names, approximate RGB), symbol → thread mapping, colour filtering |
| Statistics | Overall and per-colour progress, remaining stitches, skein estimate, history |
| Deployment | One-command self-hosting (`docker compose up`), data stays with the user |

### 2.2 Excluded (explicitly out of scope)

- **Creating** patterns (photo → chart conversion): that is the job of Stitch Fiddle and the like, not ours.
- **Shared pattern library**: no pattern is distributed, stored with a third party or shared between users (see §3.3).
- **Native** iOS/Android apps: deliberately ruled out (paid Apple developer account, contrary to the free goal).
- **Multi-user with accounts and permissions**: out of V1. The data model must not preclude it, though.
- **Marketplace, payment, advertising**: none.

---

## 3. Structural constraints

### 3.1 Technical constraints

- **Fully self-hosted and local.** No dependency on any third-party service (no proprietary cloud, no mandatory external API). The instance runs at the user's place: NAS, Raspberry Pi, personal machine, small VPS.
- **Heavy computation is server-side.** PDF extraction and, later, computer vision run on the backend — this is the whole reason for the chosen frontend + backend architecture: don't bog down an iPhone with PDF parsing or OCR.
- **The client must remain usable offline** for tracking: once a pattern is loaded, checking cells must not require any network.
- **One-command installation.** No Redis, no Postgres, no broker to administer: one application container and one data volume.

### 3.2 Platform constraints

- Primary target: **Safari on iPhone and iPad**, installed as a **PWA** ("Add to Home Screen") — full screen, icon, offline, no App Store.
- Browser storage (IndexedDB) is treated as a **cache**, never as the source of truth: Safari applies an eviction policy to site data after inactivity, and the behaviour has varied across iOS versions. The source of truth is the self-hosted server's database.
- Access from outside the local network (Tailscale/WireGuard-style tunnel, or HTTPS reverse proxy) is a **documentation** topic, not application code.

### 3.3 Legal constraints

A cross-stitch chart is a copyrighted work. The application is a **personal tracking tool**: the user imports files they already own.

- No imported pattern is shared between users or sent to a third party.
- The source PDF is not kept beyond import (automatic deletion after extraction, enabled by default).
- Reusable import "recipes" (§8.7) contain **only geometric and structural parameters** — never the creative content of the pattern.
- The DMC → RGB mapping tables used are unofficial community data: to be credited as such, and presented in the interface as an approximation.
- The terms of use must state that the application provides no patterns.

---

## 4. Initial technical findings

Six real PDFs were analysed in depth (internal structure, fonts, vector paths, fill colours, embedded images). They look alike visually and are **very different internally**. This is the finding that shapes the entire design of the extraction engine.

### 4.1 "Winter Wreath" PDF (official DMC, 5 pages)

- Grid drawn as **~6,800 vector rectangles per page**, each carrying its fill colour → **each cell's colour is extractable without OCR**.
- Symbols (T, Z, U…) are **vector paths** (~3,300–3,700 lines/curves per page), **not text** → unreadable by text extraction, they require shape recognition.
- Pattern spread over **two visually similar twin grids** of the same dimensions: to the eye, page 1 = colours, page 2 = black-and-white symbols. **Lot 5 correction, measured rather than assumed (`backend/app/type_bc.py`):** page 1 actually already carries its own small symbol paths on top of each colour fill (~3,362 curves measured, spread over the whole grid, not a localised ornament — confirmed by visually rendering an extracted symbol); page 2 (all black, ~2,466 curves) is therefore just a redundant duplicate, not the only usable source of symbols. In practice this file behaves like the trap case `summer-flight-dmc` (§4.3) rather than like `botanical-citrus-dmc`/`cucurbit-dmc`, which genuinely overlay two pages — **so the lesson of §4.3 applies to this very file too: never assume without measuring, even here.**
- Legend on page 4: DMC codes as text (3345, 3346, 471…), colour swatches as fills.
- No bitmap images: 100% vector.

### 4.2 "Cafe Brasserie" PDF (charting software export, 11 pages)

- Each symbol is a **character from a custom embedded font (`CROSSSTICH6`)**, positioned cell by cell → **real text, directly extractable**.
- Complete, unambiguous text legend (pages 9–11): symbol, strands, DMC code, name, and **exact stitch count per colour** (e.g. DMC 310 = 3,839 full stitches).
- Dimensions stated plainly: **255 × 180 stitches = 45,900 cells**, sizes in cm for 14/16/18-count fabric.
- Separate tables for full, half, quarter stitches, knots, backstitches.
- Column and row numbers printed in the margin of every grid page (10, 20, 30…) → **reliable landmark for automatic multi-page assembly**.

### 4.3 Four additional samples (widening the test base)

Four additional PDFs were analysed to check whether the A/B/C/D typology held on a wider sample. Three come from the same publisher (DMC) as Winter Wreath, one from a completely different publisher.

**"Botanical Citrus" and "Cucurbit"** (DMC, 4 pages each) — same visual template as Winter Wreath, and they confirm the type C pattern: on both, the colour page has very few vector paths (103 and 31 curves) while the symbol page has many (1981 and 1072) — the colour/symbol split between the two pages is clean and reliable.

**"Summer Flight / Envolée estivale"** (DMC, 5 pages) — same visual template, but **the split is not the same**: its page 1 (colour) already contains a very large number of vector paths (2220 curves, as many as the usual symbol page), a sign that the symbols are probably already drawn on the colour page itself, and page 2 is just a redundant black-and-white duplicate rather than an essential source of symbols. **Direct consequence for the extraction engine: even within a single publisher (DMC) and a single visual template, the relationship between pages is not guaranteed to be the same from one pattern to the next.** The type C connector must never blindly assume "page 1 = colour only, page 2 = symbols": it must measure the vector-path density of each candidate page before deciding whether a two-page overlay is really needed, or whether a single page is already enough.

**"River And Mountains"** (third-party publisher, LaserArtsDesigns, 18 pages) — structure radically different from the DMC PDFs, and one that **fits none of the four existing types**:
- Page 1 is a photorealistic preview image of the finished piece (not a working chart) — a case to detect and discard before even looking for a grid.
- The grid pages (from page 2 on) are neither text, nor coloured vector rectangles, nor vector paths: they are **thousands of small reused bitmap images** (531 is the number of *placements* on page 2 alone, not the number of distinct images — see the correction measured in Lot 7 below), each already combining a background colour and a symbol icon, placed tens of thousands of times to compose the grid.
- A cell's colour and symbol are therefore obtained by identifying which image from the reused catalogue is placed at that position — an image classification problem over a small closed catalogue of icons, very different from reading a vector fill (type B/C). **Lot 7 correction, measured rather than assumed (`backend/app/type_e.py`):** the number of genuinely distinct images used by the grid pages (2 to 16) is **20**, not ~531 — measured by accumulating the content fingerprints (`digest`, already computed by PyMuPDF) of the images placed on those exact pages; convergence stabilises from page 5, with no new image on later pages. The figure of 531 came from confusing the number of *placements* on page 2 alone (531 is correct as a placement count) with the number of distinct images. These 20 images also match exactly the 20 DMC colours in the file's legend (one image per colour, never two variants per colour) — each combines a flat background fill (the thread colour) and a symbol drawn on top in a contrasting colour, confirmed by rendering several images from the catalogue.

This last case justifies adding a **type E** to the typology (§4.4): grids composed of reused bitmap images, neither purely vector nor text.

### 4.4 Typology adopted for the extraction engine

| Type | Description | Colour | Symbol | Example |
|---|---|---|---|---|
| **A** | Structured software export: embedded symbol font + text legend | Auto | Auto | Cafe Brasserie |
| **B** | Editorial vector, colour only (symbols ignored or absent from the page) | Auto | Not handled | DMC, magazines |
| **C** | One or two vector grids with colour + symbols, path density to be measured per page to know whether an overlay is needed | Auto | Shape recognition | DMC Winter Wreath, Botanical Citrus, Cucurbit, Summer Flight |
| **E** | Grid composed of small reused bitmap images (closed catalogue of colour+symbol icons) | Auto (image classification over a closed catalogue) | Auto (same) | River And Mountains |

**Major design consequence:** no universal parser is possible, and this diversity shows up **even within a single publisher** (§4.3). Auto-detection does not need to be perfect — it must produce a **good starting proposal** that the user corrects. The manual import wizard (Lot 2) remains the **universal safety net** for any file no automatic connector recognises: cropping, dimensions, palette and painting by hand, which at a minimum matches what Pattern Keeper does today.

**Type D abandoned (decision of 2026-09-18, see §13):** the typology originally planned a type D — automatic computer-vision recognition of a free-form photo of a paper chart, with photo capture built into the wizard. Abandoned before any implementation started, for lack of a real reference file to verify such detection against (unlike every other type, always verified against a known file) and given the size of the full-frame vision problem (lighting, angle, blur) compared with the rest of the extraction engine, which all exploit a PDF's internal structure. The photo capture button has been removed from the wizard; dropping an existing image (scan, screenshot) is still possible and then follows the universal manual path above, with no attempt at automatic recognition.

---

## 5. Technical architecture

### 5.1 Overview

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  React PWA (iPhone/iPad)    │  HTTPS  │  FastAPI backend (Python)    │
│  - import wizard            │ ◄─────► │  - PDF structural analysis   │
│  - <canvas> grid rendering  │  JSON   │  - A/B/C extraction engines  │
│  - offline tracking         │  +blob  │  - vision (D, V3)            │
│  - IndexedDB cache          │         │  - stats, recipes            │
└─────────────────────────────┘         └──────────────┬───────────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │ SQLite + volume │
                                              └─────────────────┘
```

### 5.2 Backend

- **Python 3.12 + FastAPI** (REST API, automatic OpenAPI documentation).
- **PDF extraction: `pdfplumber` (structure: rectangles, colours, characters, fonts) + `PyMuPDF` (raster preview rendering, performance)** — both were concretely validated on the two test PDFs.
- **Vision (lot 7 only): `opencv-python-headless` + `numpy`.**
- **SQLite + SQLAlchemy + Alembic** (migrations). No separate database server.
- **Long-running tasks: FastAPI `BackgroundTasks` + a jobs table in the database**, polled by the client. Deliberately no Celery/Redis: one fewer service to self-host.
- **V1 authentication**: single-user instance, optional single password (environment variable) protecting the whole API. The data model provides a nullable `owner_id` so as not to close the door on multi-user.

### 5.3 Frontend

- **React + TypeScript + Vite**, PWA via `vite-plugin-pwa` (manifest + service worker).
- **Grid rendering: hand-written 2D `<canvas>`** (no DOM component per cell), with a WebGL/PixiJS fallback possible if needed.
- **Server state: TanStack Query.** **Local state: Zustand.** **Offline cache: IndexedDB via Dexie.**
- **Touch interactions: Pointer Events** (pinch-zoom, pan, tap, drag-to-paint), without relying on Safari-specific behaviour.

### 5.4 Deployment

- A single Docker image (the backend also serves the built frontend's static files), plus an example `docker-compose.yml` with a volume for `data/` (SQLite database + files).
- Environment variables: port, optional password, source PDF retention, data path.
- A `README` covering: installation, updating, backing up the volume, remote access via a personal tunnel.

---

## 6. Data model

### 6.1 Guiding principle

A 45,900-cell grid is **never** stored as one row per cell: it is read as a whole, never queried cell by cell. It is therefore stored **compacted**, and progress is stored as a **bitmap** (1 bit per cell ≈ 5.7 KB for 45,900 cells).

Essential corollary: **progress is stored separately from the grid**, so that a pattern can be re-imported or corrected without losing tracking work already done.

### 6.2 Tables

```sql
patterns (
  id, owner_id NULL, name, source_filename, source_sha256,
  width, height, fabric_count, created_at, updated_at,
  import_config_json,        -- configuration validated in the wizard
  recipe_id NULL,
  notes
)

palette_entries (
  id, pattern_id, index_in_grid,    -- index used in the grid blob
  brand, code, name, rgb_hex,
  symbol_key, symbol_svg NULL,      -- vector rendering of the symbol if available
  strands_full, strands_back,
  count_full, count_half, count_quarter, count_french, count_beads,
  backstitch_length_cm
)

grids (
  pattern_id PRIMARY KEY,
  layer_full BLOB,        -- Uint16Array w*h, 0 = empty cell, n = palette index
  layer_half BLOB NULL,
  layer_quarter BLOB NULL,
  backstitch_json,        -- [{x1,y1,x2,y2,palette_index}], coordinates at cell corners
  french_knots_json,      -- [{x,y,palette_index}], coordinates at cell centres
  encoding, version
)

progress (
  pattern_id PRIMARY KEY,
  bitmap BLOB,            -- 1 bit per cell (full stitches) — authoritative for stitched_count
  bitmap_half BLOB NULL,       -- 1 bit per cell, same shape as bitmap (Lot 8)
  bitmap_quarter BLOB NULL,    -- same
  bitmap_backstitch BLOB NULL, -- 1 bit per element of grids.backstitch_json, not per cell
  bitmap_knots BLOB NULL,      -- 1 bit per element of grids.french_knots_json
  version INTEGER,        -- incremented on every applied delta
  stitched_count, updated_at
)

progress_events (
  id, pattern_id, ts, ops_json, version_after
)                         -- log for undo and multi-device resume

recipes (
  id, fingerprint, label, grid_type, config_json,
  created_at, usage_count
)

import_jobs (
  id, status, kind, pattern_id NULL, progress_pct,
  result_json, error, created_at, finished_at
)
```

### 6.3 Grid exchange format

The grid blob is sent to the client as a base64-encoded `Uint16Array`, compressed by the HTTP layer (gzip/brotli). Traversal order: row by row, left to right, top to bottom.

For 255 × 180: 91.8 KB raw, typically 10–20 KB compressed. No pagination needed.

### 6.4 Exportable "machine file" format

An open, documented export must be available from lot 2 onwards, so that the user is never locked into the application (the Cross Stitch Markup lesson): a `.cshp` archive (ZIP) containing `pattern.json` (metadata + palette + segments), `grid.bin` (the full-stitch layer), `progress.bin`, and a `README.txt` describing the format. Since Lot 8 (`format_version` 2), optional files are added when the pattern has that content: `grid_half.bin`/`grid_quarter.bin` (same conventions as `grid.bin`) and `progress_half.bin`/`progress_quarter.bin`/`progress_backstitch.bin`/`progress_knots.bin` — the last two one bit per element of `segments.backstitch`/`french_knots`, never per cell.

---

## 7. Functional specifications

### 7.1 Project library

Home screen: list of imported patterns with thumbnail, dimensions, percentage complete, date of last activity. Actions: open, rename, duplicate, export, delete, import a new pattern.

### 7.2 Import wizard

A step-by-step flow, each step automatically pre-filled and editable, with forward/back navigation without losing input.

**Step 1 — File upload.** PDF or image, by picker or drag-and-drop. The file is sent to the server; an analysis job starts.

**Step 2 — Automatic analysis.** The server computes the file's fingerprint and looks for a known recipe (§8.7). If one exists, all following steps are pre-filled and the user can go straight to the summary. Otherwise it produces its best estimates: nature of each page, probable grid area, grid pitch, dimensions in cells, candidate legend, pagination hints, twin-grid detection.

**Step 3 — Cropping.** Raster preview of the page with a proposed frame, adjustable via handles on all four edges, with zoom for fine-tuning. Goal: exclude margins, titles, interleaved legends, or correct an imprecise detection.

**Step 4 — Grid type.** Choice from the closed list A / B / C (§4.4), pre-selected by detection, with a short, honest description of the consequences of each choice (notably: in type B, symbols are ignored and two very close shades can be confused). Type E (§4.4) is not yet offered as a user choice in V1 — see `docs/roadmap.md`.

**Step 5 — Twin-grid pairing** (type C only). Designation or confirmation of the "colour" page/area and the "symbols" page/area, with fine registration adjustment if the overlay is not exact.

**Step 6 — Dimensions.** Number of columns and rows proposed automatically, editable. When the PDF states its dimensions plainly (Cafe Brasserie case: "255w x 180h stitches"), that value is proposed first and flagged as such.

**Step 7 — Legend.** Editable table mapping symbol/colour → thread: add a missing entry, fix a code, merge two entries wrongly detected as distinct, choose the brand (DMC by default). Each row shows the detected colour next to the thread's theoretical colour, to make any doubtful match visible.

**Step 8 — Multiple pages.** Assembly mosaic proposed automatically (from axis numbers and "1/5"-style mentions), rearrangeable by drag-and-drop, with overlap areas visualised.

**Step 9 — Summary.** Preview of the reconstructed grid, confidence indicators (number of unassigned cells, colours matched by a narrow margin), saving the pattern, and an offer to save the configuration as a reusable recipe.

### 7.3 Tracking screen

This is the most used screen, and the most technically demanding.

- **Navigation**: smooth pan and pinch-zoom, jump to a coordinate, position minimap.
- **Three levels of detail** depending on zoom: colour fills only when zoomed out, colour + grid lines at medium zoom, colour + symbol + decimal grid when zoomed in.
- **Marking**: tap on a cell, drag to mark a run, rectangular selection, "mark all of this colour in the visible area". Multi-level undo.
- **Highlighting**: filter on a colour (the others are dimmed), hide cells already done, highlight the current row and column — this is the direct answer to the need to "know which colour goes in which cell with exact rows".
- **Landmarks**: grid line every 10 stitches, row and column numbers in the margin, centre marker.
- **Offline**: all of this interaction works without network, changes are queued and synchronised when the connection returns.

### 7.4 Statistics

Overall and per-colour progress (done / remaining / percentage), stitch counts by type (full, half, quarter, knots, backstitch length), estimate of skeins needed and remaining depending on fabric and strand count, activity history and average pace. When the PDF itself provides the counts (Cafe Brasserie case), they are used to verify the extraction and any discrepancy is flagged.

### 7.5 Settings

Default thread brand, default fabric, retention or deletion of source PDFs, light/dark theme, language (French and English), data backup and restore.

---

## 8. Extraction engine (backend)

### 8.1 Structural analysis

For each page: count and geometry of rectangles, paths, characters; embedded fonts and their names; bitmap images present; extractable text. Classification as grid page, legend page, instructions page, raster page.

### 8.2 Grid detection

Search for the largest regular tiling of rectangles (or characters) of uniform dimensions. The grid pitch is inferred from the median gap between adjacent elements on each axis; the dimensions in cells follow from the ratio between the area's extent and the pitch. Result: a bounding box and a (columns, rows) pair proposed to the user, never imposed.

### 8.3 Type A parser

Detection of an embedded font serving as a symbol font (many repeated glyphs in a regular tiling). Each character becomes a cell, its grid position inferred from the detected pitch. The text legend is parsed to obtain the symbol → thread code table (landmarks: "Floss Used for", columns Symbol / Strands / Type / Number / Color). The background colour of the underlying rectangle serves as a cross-check.

### 8.4 Type B and C parsers

Each cell's colour is read from its rectangle's fill colour, converted to RGB (beware of CMYK colour spaces). In type C, the symbol grid is overlaid on the colour grid after registration; vector symbol recognition compares a cell's paths with the paths of the legend's symbols (normalisation then shape matching), with a confidence score and a manual fallback when the score is insufficient.

### 8.5 Colour → thread matching

RGB → Lab conversion and nearest-neighbour search in the brand's table, with a distance score. Any match beyond a threshold is flagged to the user at step 7 of the wizard. When the legend provides the codes as text, they are authoritative and matching only serves to associate each grid colour with the right legend entry.

### 8.6 Multi-page assembly

Axis numbers printed in the margin take priority, as they give each page's absolute position in the global grid (mechanism observed on the Cafe Brasserie PDF). Failing that, matching by correlation of the overlap strips. Overlapping areas are deduplicated and any inconsistency between two pages is flagged.

### 8.7 Reusable recipes

A fingerprint is computed from the file's structure — embedded fonts, header text patterns, layout geometry — **and never from the creative content**. After an import is validated, the configuration can be saved as a recipe associated with that fingerprint. A later file with the same fingerprint (same publisher, same software, same shop) is then pre-configured automatically.

For the same reason, the configuration saved in a recipe (Lot 6) is limited to cropping (`crop_by_page`) — never the dimensions or the palette, which are content specific to each pattern and always differ from one file to the next, even within the same publisher (§4.1). Those two are still produced, on every import, by automatic detection (Lots 4-5) on the file itself.

This library stays strictly local. Community sharing had been considered as an open avenue, but was removed from scope (decision of 2026-09-18, §13) — the intended use does not need it.

---

## 9. API

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/imports` | Upload the file, create the analysis job |
| GET | `/api/imports/{id}` | Job status and analysis result |
| GET | `/api/imports/{id}/pages/{n}/preview` | Raster preview of a page (resolution parameter) |
| PATCH | `/api/imports/{id}/config` | Update the wizard configuration |
| POST | `/api/imports/{id}/extract` | Trial extraction with the current configuration |
| POST | `/api/imports/{id}/commit` | Create the final pattern |
| GET | `/api/patterns` | List of patterns |
| GET | `/api/patterns/{id}` | Metadata and palette |
| GET | `/api/patterns/{id}/grid` | Grid layers (compact blob) |
| GET | `/api/patterns/{id}/progress` | Progress bitmap and version |
| POST | `/api/patterns/{id}/progress` | Apply a batch of changes (with version for conflict detection) |
| GET | `/api/patterns/{id}/stats` | Computed statistics |
| GET | `/api/patterns/{id}/export` | `.cshp` export |
| GET/POST/DELETE | `/api/recipes` | Recipe library |

Progress synchronisation works with **versioned deltas**: the client sends the changed cells along with the version it knows; on divergence, the server returns the missing operations and the client replays them. Checking a cell is an idempotent operation, which makes conflicts trivial to resolve. Since Lot 8, each operation also carries a stitch category (`layer`: full, 1/2, 1/4, backstitch, knot) — a single version index for the whole pattern, but an index space specific to each category (never shared, see §6.2).

---

## 10. Non-functional requirements

- **Performance**: smooth pan and zoom (target 60 fps, acceptable floor 30) on a 45,900-cell pattern, on a real iPhone — not just a desktop simulator. Loading a pattern in under 2 seconds on a local network.
- **Extraction**: analysis of a 10-page PDF in under 30 seconds, with progress shown.
- **Offline**: tracking fully functional without network on patterns already opened; automatic synchronisation on return.
- **Robustness**: no import may end in a dead end — the universal manual import is always available as a fallback.
- **Accessibility**: touch targets of at least 44 px, sufficient contrast, interface usable one-handed on iPhone.
- **Internationalisation**: French and English from the start, externalised strings.
- **Tests**: the two analysed PDFs serve as the reference test set; any change to the extraction engine must be verified against the known values (255 × 180 cells, 34 colours, per-colour counts from page 11).

---

## 11. Roadmap

The project is split into independently deliverable lots. Each lot is usable once finished: there is no lot that is "useless until the next one is done".

### Lot 0 — Technical foundation

FastAPI + SQLite + Alembic skeleton, React/Vite/TypeScript frontend as an installable PWA, single Docker image and `docker-compose.yml`, test suite and continuous integration, self-hosting `README`.

*Done when:* `docker compose up` gives an application installable on an iPhone home screen, with an empty home page and an API that responds.

### Lot 1 — Rendering and tracking core

Complete data model, `<canvas>` rendering with its three levels of detail, touch pan/zoom, cell marking, versioned-delta synchronisation, offline cache. Tested on a 255 × 180 demo grid injected directly into the database.

*Done when:* you can check cells on 45,900 cells with smooth pan/zoom on iPhone, offline, and find your progress again after a reload and on another device.

*This is the most technically risky lot: it is deliberately placed early.*

### Lot 2 — Universal assisted import

Wizard: file upload, preview, manual cropping, dimension calibration, manual palette entry, filling colours by area. `.cshp` export.

*Done when:* any PDF or photo can be turned into a trackable pattern, entirely by hand. At this point, the application is already a credible alternative to Pattern Keeper.

### Lot 3 — Statistics and tracking comfort

Complete statistics, colour filtering, hiding done cells, row/column highlighting, multi-level undo, history.

*Done when:* the four initial needs from §1 are covered, even if import remains manual.

### Lot 4 — Automatic type A extraction

Structural analysis, grid detection, symbol font parser, text legend parser, multi-page assembly by axis numbers. Wizard steps 2, 6, 7 and 8 become pre-filled.

*Done when:* the "Cafe Brasserie" PDF imports by simply accepting the proposals, and the per-colour counts obtained match those on its page 11.

### Lot 5 — Automatic type B and C extraction

Colour extraction from rectangle fills, Lab matching against the thread palette, twin-grid overlay, vector symbol recognition with a confidence score.

*Done when:* the "Winter Wreath" PDF imports with its correct colours, its two grids overlaid, and explicit flagging of uncertain cells.

### Lot 6 — Reusable recipes

Fingerprint computation, saving and automatically re-applying validated configurations, local library management.

*Done when:* re-importing a second PDF from the same publisher automatically reuses the cropping already validated the first time, without going through the manual cropping step again. **Clarification settled in Lot 6, not assumed when this section was written:** a recipe never carries the dimensions or the palette (§8.7 — content specific to each pattern, even within the same publisher, cf. §4.1 Winter Wreath/Summer Flight vs Botanical Citrus/Cucurbit); those two are always recomputed by Lots 4-5 on the file itself, never copied from one file to another. "Jumping straight to the summary" is therefore only observable as such for a file already recognised by a type A/B/C connector (cropping then no longer changes anything observable); for a file no automatic connector recognises, the recipe saves only the manual cropping, never entering the dimensions/palette specific to that pattern.

### Lot 7 — Grids made of reused bitmap images (type E)

Detection and exclusion of photorealistic preview pages, extraction of the catalogue of distinct images reused on grid pages, classification of each catalogue image into (colour, symbol), repositioning each cell from those images' placements.

*Done when:* the "River And Mountains" PDF imports with its correct colours and symbols, without the photorealistic preview page being taken for a grid page. **Clarification settled in Lot 7:** this fixture's catalogue actually contains 20 distinct images, not ~531 (see §4.3 and `docs/roadmap.md`); the image → DMC colour matching used (`backend/app/type_e.py`) is the exact placement count per image, not perceptual colour alone (measured as unreliable on this file).

### Lot 8 — Finishing touches

Full fractional and special stitches in the tracking interface, backup/restore, dark theme, translations. Assumes `backstitch_json`/`french_knots_json` (§6.2) are already populated — see Lot 9 for their actual extraction from the PDF.

### Lot 9 — Special stitch extraction (backstitch, knots, fractional)

Spotted while testing Lot 5 for real: some PDFs (including "Cafe Brasserie") draw backstitches and French knots directly on top of the counted-stitch grid, never extracted by any connector (A/B/C) so far. Detection of backstitch paths (a line crossing several cells, unlike a full-stitch symbol or the printed grid) and of French knots (an isolated shape outside the regular tiling), with a mandatory distinction between decorative backstitch (cover page, outside the working grid) and real backstitch meant to be stitched. For type A, cross-checking with the "Backstitch"/"French Knots" legend tables ignored since Lot 4, on the same principle as full-stitch verification (§7.3).

*Done when:* the backstitches and French knots of "Cafe Brasserie" are extracted with counts consistent with its legend, checkable in tracking, without any decorative off-grid backstitch being wrongly imported as part of the pattern.

### Recommended sequencing

Lots 0 to 3 make up the **usable V1** and should be carried out in one go. Lots 4 and 5 form the **differentiating V2** — this is where the application surpasses the free competition. Lots 6 to 9 are amplifiers, to be prioritised according to real use.

---

## 12. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Rendering 45,900 cells too slow on iPhone | High — it is the main screen | Addressed in lot 1, before everything else; canvas with tiles and levels of detail; WebGL fallback |
| PDF heterogeneity: every new format breaks the parser | High | Semi-automatic wizard (the user corrects), universal assisted mode always available, recipes to capitalise on |
| Confusion between two close thread shades | Medium — ruins the stitching | Lab perceptual distance, confidence threshold, explicit flagging, legend text codes take priority over colour |
| Storage eviction by Safari | Medium — loss of progress | The server is the source of truth, IndexedDB is only a cache, replayable deltas |
| Vector symbol recognition with no existing solution to reuse | Medium | Deferred to lot 5, non-blocking; type B (colour only) remains usable in the meantime |
| Decorative backstitch (text, cover-page border) confused with a real pattern backstitch | Medium — would import an element not meant to be stitched | Deferred to lot 9; explicit distinction between working grid and off-grid pages before any backstitch extraction |
| Intellectual property of patterns | Medium — legal | Strictly local processing, no pattern sharing, recipes without creative content, explicit terms of use |
| Off-putting self-hosting complexity | Low to medium | A single container, no external dependency, careful documentation |

---

## 13. Decisions made

| Date | Decision |
|---|---|
| 2026-09-13 | **Guided semi-automatic** import rather than fully automatic or fully manual |
| 2026-09-13 | **No native app**: installable PWA web app, iPhone/iPad as the primary target |
| 2026-09-13 | **Self-hosted frontend + backend**: PDF computation and vision stay on the server |
| 2026-09-13 | **React + FastAPI + SQLite + Docker**, with no external service or cloud dependency |
| 2026-09-13 | **Progress stored separately from the grid**, to survive a re-import |
| 2026-09-14 | Addition of **type E** (grids made of reused bitmap images) to the typology, after analysing 4 additional PDFs — out of Lot 5's scope, to be repositioned in the roadmap |
| 2026-09-18 | **Type D abandoned** (automatic computer-vision recognition of a free-form photo) and the photo capture button removed from the wizard, before any implementation started — see §4.4. The universal manual import (Lot 2) remains the safety net for any file, images included, that no automatic connector recognises |
| 2026-09-23 | **MIT licence** chosen over AGPL — priority on distribution and adoption for a small project, no identified need to prevent a closed fork. See `LICENSE` at the root. |
| 2026-09-18 | **Community recipe sharing removed from scope** — mentioned as a possible avenue in §8.7, never a commitment; the intended use does not need it |
| 2026-09-24 | **All documentation, code comments and docstrings are written in English.** French doc filenames renamed (`docs/specification.md`, `docs/features-and-limits.md`). User-facing strings are unaffected: they stay in i18n, French and English |
