---
name: add-import-connector
description: Procedure for adding support for a new source PDF format (a new publisher or charting software not covered by the existing parsers). Use when a user reports that a PDF imports badly or when widening type A coverage.
---

# Adding an import connector for a new PDF format

Reminder of the guiding principle (`docs/specification.md` §4.3 and §4.4): there is no universal parser. Each new format encountered either attaches to an existing type (A/B/C/E), or reveals a need to refine type detection. The goal is never perfect recognition, but a good starting proposal that the import wizard lets the user correct.

Type D (free-form photo, computer vision) was abandoned before any implementation (specification §4.4/§13) — never propose attaching a new case to it or spending work on it; an essentially bitmap file without a closed catalogue of icons stays in the universal assisted mode (Lot 2), with no dedicated connector.

## 1. Analyse the new PDF's internal structure

Never rely on visual appearance. Inspect:
- the extractable text and embedded fonts (`pdffonts`, or `pdfplumber`: `page.chars`, font names)
- vector rectangles and their fill colours (`page.rects`)
- the presence of bitmap images and their reuse (`pdfimages -list`, or `page.images`/`page.get_image_info()`) — a small number of distinct images reused thousands of times signals a type E, not just a background image
- layout keywords that could serve as a signature (e.g. "Floss Used for", legend column names)

This is exactly the approach that made it possible to tell the existing fixtures apart — see `docs/specification.md` §4.1, §4.2 and §4.3 for complete examples of this diagnosis, including the River And Mountains case (type E).

## 2. Determine the type (A/B/C/E)

- Embedded font with many glyphs repeated in a regular tiling + structured text legend → **type A**, eligible for a dedicated parser.
- Coloured rectangles + symbols as vector paths, a single grid → **type B**.
- Two grid areas of the same dimensions, one colour, the other symbols → **type C**.
- Grid composed of a small closed catalogue of bitmap images (colour+symbol already combined in each image), reused thousands of times → **type E** (`backend/app/type_e.py`): an image classification problem over a closed catalogue, not free-form vision.

## 3. Create the fixture

Add the PDF (or an anonymised excerpt if it raises a rights issue — never commit a pattern whose origin/licence is uncertain) in a new subdirectory of `fixtures/`, with a `README.md` documenting the expected values, modelled on the existing `fixtures/README.md`.

## 4. Write or adapt the parser

- Type A: add the font/layout signature to the existing detection, reuse the text legend parsing pipeline rather than writing a new one each time.
- Type B/C: first check whether the generic grid detection and colour matching heuristics are already enough — a new B/C case should almost never need publisher-specific code, only threshold adjustments.
- Type E: first check whether `backend/app/type_e.py` (image catalogue, deduplication, colour+symbol classification per image) applies as is — a new type E publisher should only need deduplication threshold adjustments, not a new pipeline.

## 5. Verify with the `verify-extraction-fixtures` skill

Never consider a connector done without going through this verification, fixture by fixture, including the existing fixtures (non-regression).

## 6. Consider a recipe

If this format comes from a source likely to produce other similar PDFs (a publisher, a shop), the reusable recipes feature (specification §8.7, Lot 6, `backend/app/fingerprint.py`/`backend/app/api/recipes.py`) already applies with nothing specific to write — it relies on a generic structural fingerprint (page size, fonts, labels), not on per-publisher logic.
