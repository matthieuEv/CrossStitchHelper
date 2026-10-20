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
| Grid | Full stitches, half stitches, quarter and three-quarter stitches (each in a corner of its cell), backstitches, French knots, beads |
| Tracking | Checking cell by cell, by area, by colour; undo; multi-device resume |
| Colours | DMC palette (codes, names, approximate RGB), symbol → thread mapping, colour filtering |
| Statistics | Overall and per-colour progress, remaining stitches, skein estimate, history |
| Deployment | One-command self-hosting (`docker compose up`), data stays with the user |

### 2.2 Excluded (explicitly out of scope)

- **Creating** patterns (photo → chart conversion): that is the job of Stitch Fiddle and the like, not ours.
- **Public pattern library**: no pattern is distributed publicly or stored with a third party (see §3.3). Sharing within an instance's group is in scope since Lot 11 (issue #78) — deliberate, by its members, never implicit — and, since Lot 11b, with one other instance its admins deliberately linked.
- **Native** iOS/Android apps: deliberately ruled out (paid Apple developer account, contrary to the free goal).
- **Multi-user with accounts and permissions**: out of V1 — added in Lot 10 as *profiles* of one household or group (issue #77): each profile has its own private library, an admin manages the profiles. Still excluded: self-registration, sending email, any account on a third-party service.
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
- Access from outside the local network (Tailscale/WireGuard-style tunnel, or HTTPS reverse proxy) is a **documentation** topic, not application code. The same goes for linking two instances (Lot 11b): the hosting one must be reachable by the other's server, the application does no NAT traversal of its own.

### 3.3 Legal constraints

A cross-stitch chart is a copyrighted work. The application is a **personal tracking tool**: the user imports files they already own.

- No pattern is ever sent to a third party. Within an instance, a pattern is shared only when a profile deliberately puts it in the shared library (Lot 11, decision of 2026-10-14), with a reminder that whoever shares remains responsible for having the right to; a profile's library stays private, and progress is never shared.
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
- **SQLite + SQLAlchemy**. No separate database server. No migrations while in development: the schema is created from the models and recreated empty when they change (`backend/app/schema.py`, decision of 2026-10-20).
- **Long-running tasks: FastAPI `BackgroundTasks` + a jobs table in the database**, polled by the client. Deliberately no Celery/Redis: one fewer service to self-host.
- **Authentication (Lot 10, issue #77)**: profiles (first name, last name, email, role `admin`/`user`) logged in by password. The V1 plan (single-user instance, optional single password in an environment variable) was never built; `patterns.owner_id`, nullable since V1, now holds the owning profile. Password hashing is delegated to `pwdlib` (Argon2id); the session is an opaque random token in an HttpOnly, `SameSite=Lax` cookie (`Secure` behind HTTPS), stored hashed in `user_sessions` — server-side so that a password change, a reset or a deleted profile ends sessions at once. Every API route except health and the login screen's own routes requires a session; state-changing requests must also carry the `X-CSH-Client` header the frontend adds (cross-site request forgery). A pattern or import job of another profile answers 404, like one that does not exist. No email is ever sent: an admin resets forgotten passwords, or the server owner does from the command line (`python -m app.cli`). OpenID Connect (issue #77, future) would add a second way into the same session.

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
  id, owner_id NULL,         -- users.id (Lot 10); NULL only before the first admin exists,
                             -- and always for shared/proposal patterns
  library,                   -- 'personal' | 'shared' | 'proposal' (Lot 11)
  revision,                  -- content replacements of a shared pattern
  contributed_by NULL,       -- users.id credited for a shared pattern
  origin_pattern_id NULL, origin_revision NULL,  -- a copy's shared original
  source_peer_id NULL, remote_id NULL,  -- Lot 11b: a mirror of a linked host's pattern
  contributed_by_name NULL,  -- credit for a contributor of another instance
  shared_seq NULL,           -- place in this instance's change sequence
  name, source_filename, source_sha256,
  width, height, fabric_count, created_at, updated_at,
  import_config_json,        -- configuration validated in the wizard
  recipe_id NULL,
  notes,
  labels_json                -- JSON list of labels (issue #57), no table of their own
)

palette_entries (
  id, pattern_id, index_in_grid,    -- index used in the grid blob
  brand, code, name, rgb_hex,
  symbol_key, symbol_svg NULL,      -- vector rendering of the symbol if available
  strands_full, strands_back,
  count_full, count_half, count_quarter, count_three_quarter, count_french, count_beads,
  backstitch_length_cm
)

grids (
  pattern_id PRIMARY KEY,
  layer_full BLOB,        -- Uint16Array w*h, 0 = empty cell, n = palette index
  layer_half BLOB NULL,
  quarter_json,           -- [{x,y,corner,palette_index}]: a cell and a corner (tl/tr/bl/br),
  three_quarter_json,     -- several per cell allowed (issue #83) — lists, not layers
  backstitch_json,        -- [{x1,y1,x2,y2,palette_index}], coordinates at cell corners
  french_knots_json,      -- [{x,y,palette_index}], coordinates at cell centres
  encoding, version
)

progress (
  pattern_id PRIMARY KEY,
  bitmap BLOB,            -- 1 bit per cell (full stitches) — authoritative for stitched_count
  bitmap_half BLOB NULL,       -- 1 bit per cell, same shape as bitmap (Lot 8)
  bitmap_quarter BLOB NULL,    -- 1 bit per element of grids.quarter_json (issue #83)
  bitmap_three_quarter BLOB NULL, -- 1 bit per element of grids.three_quarter_json
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
  id, owner_id NULL,         -- users.id (Lot 10), the profile running the wizard
  status, kind, pattern_id NULL, progress_pct,
  result_json, error, created_at, finished_at
)

peers (                      -- Lot 11b: a linked instance
  id, instance_id, name,
  role,                      -- 'host' (we mirror its shared library) | 'subscriber' (it mirrors ours)
  base_url NULL, outbound_token NULL,   -- host: where and how we call it
  inbound_token_hash NULL,   -- subscriber: the token it presents, hashed
  trust_admins,              -- its admins may moderate the host's library
  cursor,                    -- host: last change read
  last_sync_at NULL, last_error NULL, created_at
)

peer_invitations (id, secret_hash, trust_admins, created_by, created_at, expires_at, used_at)
shared_tombstones (pattern_id, seq, deleted_at)   -- removals, in the change sequence

shared_requests (            -- Lot 11, issue #78
  id, kind,                  -- 'removal' | 'replacement'
  status,                    -- 'pending' | 'accepted' | 'rejected' | 'cancelled'
  shared_pattern_id NULL,    -- NULL once that pattern is gone; pattern_name remains
  pattern_name, requested_by NULL, message NULL,
  proposal_pattern_id NULL,  -- frozen proposed content (a 'proposal' pattern)
  resolved_by NULL, created_at, resolved_at NULL
)

users (                      -- Lot 10, issue #77
  id, email UNIQUE,          -- lowercased; a contact detail, not the login identifier
  first_name, last_name,
  role,                      -- 'admin' | 'user' — at least one admin, always
  password_hash,             -- Argon2id (pwdlib)
  created_at, updated_at
)

user_sessions (              -- one row per logged-in device
  id, user_id, token_hash UNIQUE,   -- SHA-256 of the cookie's random token
  created_at, last_seen_at, expires_at, user_agent
)
```

Deleting a profile deletes its patterns with it (its library is private: no admin inherits it). Patterns and import jobs left without an owner — an instance upgraded from a version without profiles, the demo pattern seeded before setup — are handed to the first admin at first-launch setup.

### 6.3 Grid exchange format

The grid blob is sent to the client as a base64-encoded `Uint16Array`, compressed by the HTTP layer (gzip/brotli). Traversal order: row by row, left to right, top to bottom.

For 255 × 180: 91.8 KB raw, typically 10–20 KB compressed. No pagination needed.

### 6.4 Exportable "machine file" format

An open, documented export must be available from lot 2 onwards, so that the user is never locked into the application (the Cross Stitch Markup lesson): a `.cshp` archive (ZIP) containing `pattern.json` (metadata + palette + segments), `grid.bin` (the full-stitch layer), `progress.bin`, and a `README.txt` describing the format. Since Lot 8, optional files are added when the pattern has that content: `grid_half.bin` (same conventions as `grid.bin`) and `progress_half.bin`/`progress_quarter.bin`/`progress_three_quarter.bin`/`progress_backstitch.bin`/`progress_knots.bin` — all but the first one bit per element of `segments.quarter_stitches`/`three_quarter_stitches`/`backstitch`/`french_knots`, never per cell. Since `format_version` 3 (issue #83), 1/4 and 3/4 stitches are those `segments` lists (a cell, a corner, a colour) instead of a `grid_quarter.bin` layer.

---

## 7. Functional specifications

### 7.1 Project library

Home screen: list of imported patterns with thumbnail, dimensions, percentage complete, date of last activity. Actions: open, edit (name and labels), duplicate, share, export, delete, import a new pattern. A row of label filters ("All" by default) narrows the list to the patterns carrying one label; labels are also chosen on the import summary step.

Since Lot 11 (issue #78), two tabs: **My patterns** and **Shared**. The shared tab lists the instance's shared patterns (who added them, whether one has a copy); anyone copies one into their library or asks the admins to remove it or to replace it with their own version (frozen when sent); admins rename, replace or remove, and decide on pending requests, counted on the tab. A copy whose original was replaced shows "Update": updating replaces its palette and grid in place when its progress keeps its meaning (same cells, same backstitches and knots), otherwise adds a new copy next to it — never at the cost of progress. The import summary step offers the destination: my library, shared, or both.

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

Overall and per-colour progress (done / remaining / percentage), stitch counts by type (full, half, quarter, three-quarter, knots, backstitch length), estimate of skeins needed and remaining depending on fabric and strand count, activity history and average pace. When the PDF itself provides the counts (Cafe Brasserie case), they are used to verify the extraction and any discrepancy is flagged.

### 7.5 Settings

Default thread brand, default fabric, retention or deletion of source PDFs, light/dark theme, language (French and English), data backup and restore.

Since Lot 10: **My account** for every profile (own name, email and password, "switch profile"); **Profile management** for admins (add a profile with an initial password, edit any profile including its role, reset a password, delete a profile and its library). Backup, restore, clearing all data and the daily backup setting act on every profile's data: admins only.

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
| PATCH | `/api/patterns/{id}` | Edit a pattern's name and labels |
| DELETE | `/api/patterns/{id}` | Delete a pattern with its palette, grid, progress and activity log |
| POST | `/api/patterns/{id}/duplicate` | Copy a pattern (palette and grid) under a new name, with empty progress |
| GET | `/api/patterns/{id}/grid` | Grid layers (compact blob) |
| GET | `/api/patterns/{id}/progress` | Progress bitmap and version |
| POST | `/api/patterns/{id}/progress` | Apply a batch of changes (with version for conflict detection) |
| GET | `/api/patterns/{id}/stats` | Computed statistics |
| GET | `/api/patterns/{id}/export` | `.cshp` export |
| GET/POST/DELETE | `/api/recipes` | Recipe library (shared by all profiles; deleting: admins only) |
| GET | `/api/auth/status` | Whether the instance still needs its first admin, and the logged-in profile |
| POST | `/api/auth/setup` | First launch: create the first admin (only while no profile exists) |
| GET | `/api/auth/profiles` | Login screen: first name, initials and avatar colour of each profile |
| POST | `/api/auth/login`, `/api/auth/logout` | Open / close this device's session |
| GET/PATCH | `/api/auth/me` | My profile (never its role) |
| POST | `/api/auth/me/password` | Change my password (ends my other sessions) |
| GET/POST | `/api/users` | Admins: list profiles (with their library size), add a profile |
| PATCH/DELETE | `/api/users/{id}` | Admins: edit a profile (role, password reset), delete it with its library |
| POST | `/api/patterns/{id}/share` | Put a copy of my pattern in the shared library (mine stays, linked) |
| POST | `/api/patterns/{id}/update-from-origin` | Bring a copy up to its replaced original (in place, or as a new copy) |
| GET | `/api/shared` | Shared patterns, and the requests I may see |
| GET | `/api/shared/patterns/{id}`, `/grid` | A shared pattern (or a proposal, for admins and its author) |
| POST | `/api/shared/patterns/{id}/copy` | Copy a shared pattern into my library |
| PATCH/DELETE | `/api/shared/patterns/{id}` | Admins: rename / remove a shared pattern |
| POST | `/api/shared/patterns/{id}/replace` | Admins: replace its content with one of my patterns |
| POST | `/api/shared/requests` | Ask for a removal, or propose a replacement |
| POST | `/api/shared/requests/{id}/accept`, `/reject`, `/cancel` | Admins decide; the author withdraws |
| GET | `/api/federation` | Admins: this instance's name and links |
| PUT | `/api/federation/instance` | Admins: this instance's name, shown to linked instances |
| POST/DELETE | `/api/federation/invitations` | Admins: a one-time code for another instance (24 h) |
| POST | `/api/federation/join` | Admins: join a host with its code |
| DELETE | `/api/federation/peers/{id}` | Admins: undo a link (mirrors go, copies stay) |
| POST | `/api/federation/sync` | Pull the linked hosts now (opening the shared tab) |
| — | `/api/federation/v1/*` | Instance-to-instance protocol, peer token only: `info`, `pair`, `changes?since=`, `patterns/{id}`, `shared` (+ rename, replace, delete if trusted), `requests` (+ accept/reject if trusted, cancel) |

Progress synchronisation works with **versioned deltas**: the client sends the changed cells along with the version it knows; on divergence, the server returns the missing operations and the client replays them. Checking a cell is an idempotent operation, which makes conflicts trivial to resolve. Since Lot 8, each operation also carries a stitch category (`layer`: full, 1/2, 1/4, 3/4 since issue #83, backstitch, knot) — a single version index for the whole pattern, but an index space specific to each category (never shared, see §6.2).

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

Lots 0 to 3 make up the **usable V1** and should be carried out in one go. Lots 4 and 5 form the **differentiating V2** — this is where the application surpasses the free competition. Lots 6 to 9 are amplifiers, to be prioritised according to real use. Lots 10 (profiles) and 11 (shared libraries, within an instance then between two paired instances) come from issues #77 and #78 — see `docs/roadmap.md`.

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
| 2026-10-14 | **Profiles (Lot 10, issue #77)** — the household instance becomes a group of profiles, each with a private library; at least one admin, always. Login delegated where it is risky (`pwdlib`/Argon2id for passwords; Authlib for OpenID Connect later), sessions in a small table of our own: `fastapi-users`, the only library covering user management, requires an asynchronous database layer (the whole backend is synchronous) and is in maintenance mode. Login screen lists the profiles ("Who's stitching?") then asks for the password — profile names are visible to anyone who opens the app, accepted for a household. Deleting a profile deletes its library |
| 2026-10-14 | **Shared library within an instance (Lot 11a, issue #78)** — reverses the "nothing shared between users" principle of 2026-09-13 for the group of one instance only: sharing is deliberate (a profile shares a pattern), never implicit; a shared pattern belongs to nobody and has no progress — stitching it means copying it; only admins edit or remove it, others ask (removal, or a replacement frozen when proposed); a copy is told when its original is replaced and is never overwritten nor loses its progress (`backend/app/shared.py::update_copy`). Rights reminder shown wherever a pattern is shared. Sharing with a second, paired instance is Lot 11b |
| 2026-10-14 | **Sharing between two instances (Lot 11b, issue #78)** — every shared pattern has one home instance, the only one that changes it; a subscribed instance keeps a read-only mirror, refreshed by pull (a changes feed: cursor, revision, tombstones), and forwards its users' writes to the home instance. No conflict can arise, and only the host needs to be reachable. Pairing by a one-time invitation code; the host chooses whether the subscriber's admins may moderate. Rejected after research: replication libraries (cr-sqlite has no Python package, Marmot/rqlite need a separate service, Litestream is single-writer, sqlite-sync is not open source), CRDT libraries (overkill for rarely edited, admin-authoritative data), ActivityPub and an embedded OIDC provider (overkill for two trusted peers), Iroh (Python bindings alpha, relays run by a third party by default). Delegated: transport security (HTTPS or the tunnel already used for remote access) and HTTP (`httpx`) |
| 2026-10-20 | **No schema migrations while in development** — the Alembic chain (0001–0009) is removed; the models are the only description of the schema. At startup the database is compared with a fingerprint of the models and, when they changed, every table is dropped and recreated empty (`backend/app/schema.py`). Losing data on such an update is accepted while the app is only used for development; automatic backups are kept on disk. To revisit before a first stable release |
