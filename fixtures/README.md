# Fixtures — reference test set

Six real PDFs used as ground truth to develop and validate the extraction engine (see `docs/specification.md` §4 and §8, and the `.claude/skills/verify-extraction-fixtures/` skill). Five come from DMC (two different internal structures despite a shared visual template — see specification §4.3), one comes from a third-party publisher (LaserArtsDesigns) with an entirely different structure.

## `cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf` — type A

Export from charting software (custom embedded font `CROSSSTICH6`, one glyph = one symbol). Complete text legend on pages 9–11.

**Expected values to verify in tests:**
- Dimensions: 255 × 180 cells (45,900 cells in total)
- 34 DMC colours used
- Exact per-colour counts on page 11 (e.g. DMC 310 "Black" = 3839 full stitches, DMC 3031 "Mocha Brown-VY DK" = 3756 full stitches + 4 quarters + 128.8 cm of backstitch)
- Reference fabric: Aida 16, white

**Special stitches — measured in Lot 9 (`backend/tests/test_type_a.py`), not assumed:**
- The legend does not stop at full stitches: on pages 9–10, five "Floss Used for ..." sections follow one another — *Full* (34 rows), *Half* (762, 3756, B5200), *Quarter* (3031), *French Knots* (742), *Back Stitches* (310, 640, 642, 742, 814, 839, 938, 3031). The last two sections have **no** symbol glyph: their "Symbol" column is a vector swatch drawn in the exact colour used on the grid pages — that is the colour → DMC code matching key, measured in the file, and not a colorimetric resemblance (a Lab nearest neighbour gets this file wrong: it swaps 938 and 3031, and never assigns 310, drawn in (35, 40, 29) rather than in black).
- Every backstitch is drawn **twice** at the same place (dark 2.4 pt pass then light 2.08 pt pass): counting it twice doubles the length. On top of that, each page redraws in washed-out shades the strip it shares with the neighbouring page — 8 extra shades that must never be added to the total (they only overlay strokes already counted).
- Backstitch endpoints: all on the half-cell lattice (5,120 on cell corners, 52 on midpoints), often diagonal — and 36 of the 56 diagonals on page 1 are *descending*, hence unreadable from the pdfplumber bbox alone (`pts` is required).
- The "Back(cm)" column on page 11 is actually expressed in **inches**: its value is exactly the length in cells divided by the declared fabric count (Aida 16). All eight codes match within 0.1% with this conversion.
- The 4 quarter stitches (DMC 3031) are drawn small **in a corner of a cell already occupied** by a DMC 3756 half stitch, with the same glyph and the same background colour as the 3031 full stitch: only their offset within the cell tells them apart (48,310 glyphs out of 48,314 are exactly centred).
- The 3 knots (DMC 742) are on page 1 only. Not to be confused with two other shapes present on the grid pages: the **page landmark arrows** (small solid black shape exactly one cell in size, in the margin, on every page) and **manual annotations** left in the file (system-blue `#007AFF` freehand strokes on pages 2 and 6, not aligned with the cells at all).

## `winter-wreath-dmc/PATASS117_2C_2.pdf` — type C

Official DMC chart ("Winter Wreath / Couronne d'hiver"), 5 pages, 100% vector.

**Characteristics to verify in tests:**
- Page 1: colour grid (~6800 coloured vector rectangles) — **measured in Lot 5 (`backend/tests/test_type_bc.py`): this page actually already carries ~3362 path curves spread over the whole grid (a small symbol on top of each colour fill), not "few paths" as a first glance suggests**
- Page 2: separate black-and-white symbol grid, same dimensions as page 1 (~2466 curves) — measured in Lot 5: redundant with the symbols already present on page 1, never the only usable source
- Page 4: text legend with DMC codes (3345, 3346, 471, 472, 11, 18, 3821, 726, 3853, 3854, white, 351, 814, E321)
- Stated design size: 16 × 15.81 cm on 14-count Aida
- **Actually behaves like the trap case `summer-flight-dmc` below** (contrary to what a first visual examination suggests): `botanical-citrus-dmc` and `cucurbit-dmc` are the only two DMC fixtures in this set that really overlay a second symbol page — see specification §4.1 for the details of this correction measured in Lot 5.

## `botanical-citrus-dmc/agrumes_-_planche_botanique.pdf` — type C

Official DMC chart ("Botanical Citrus / Agrumes - planche botanique"), 4 pages, 100% vector.

**Characteristics to verify in tests:**
- Page 1 (colour): 2827 rectangles, only 103 vector paths — a "clean" colour page, little symbol noise
- Page 2 (symbols): 1643 rectangles, 1981 vector paths — dense symbol page
- Clean colour/symbol page split, like Winter Wreath
- Legend on page 4, 17 DMC colours

## `cucurbit-dmc/Cucurbitaces.pdf` — type C

Official DMC chart ("Cucurbitacées / Cucurbit"), 4 pages, 100% vector.

**Characteristics to verify in tests:**
- Page 1 (colour): 1922 rectangles, only 31 vector paths
- Page 2 (symbols): 886 rectangles, 1072 vector paths
- Clean colour/symbol split, smaller pattern (13.2 × 9.8 cm)
- Legend on page 4, 18 DMC colours (6 swatches in the legend not used in the pattern — check the filtering down to colours actually used)

## `summer-flight-dmc/vol_de_te.pdf` — type C, variant where an overlay is not guaranteed

Official DMC chart ("Summer Flight / Envolée estivale"), 5 pages, 100% vector. **Same visual template as the three DMC fixtures above, but a different internal structure — a deliberately tricky test case.**

**Characteristics to verify in tests:**
- Page 1: 10224 rectangles **and 2220 vector paths** — unlike the other DMC fixtures, the colour page already contains an amount of paths comparable to a full-fledged symbol page
- Page 2: 7960 rectangles, 1730 vector paths — also dense, probably a black-and-white duplicate rather than an essential source of symbols
- **This case must make any connector fail that would blindly assume "page 1 = colour only, page 2 = symbols only"** — the extraction engine must measure path density per page before deciding whether to overlay two pages or extract everything from a single one
- Legend on pages 4–5, 12 DMC colours + French knots

## `river-and-mountains-laserarts/RiverAndMountains-CS.pdf` — type E

Chart from a third-party publisher (LaserArtsDesigns, "River And Mountains - Color Symbol"), 18 pages. **Structure radically different from the DMC PDFs — no coloured rectangles, no vector symbol paths, no symbol font.**

**Characteristics to verify in tests:**
- Page 1: photorealistic preview image of the finished pattern (40084 image placements on this page) — **to be detected and excluded from extraction**. **Clarification measured in Lot 7 (`backend/app/type_e.py`), not assumed when this entry was first written:** these placements are not all identical — 21 distinct images (mixed 48×48 and 64×64 px sizes), an impasto-style texture for a photorealistic rendering, entirely disjoint from the grid pages' catalogue (no image in common). It is the fraction of placements at the dominant size (69.8% here, never 100% as on a real grid page) that allows it to be excluded reliably, not its "page 1" position on its own.
- Grid pages (2 to 16): composed of reused bitmap images (64×64 px), tiled on a regular grid with absolute axis numbers in the margin (same multi-page assembly mechanism as `cafe-brasserie-charting-export`, 5 pages wide x 3 pages high). **Lot 7 correction, measured rather than assumed: only 20 genuinely distinct images, not ~531** (531 is the number of *placements* on page 2 alone, not the number of distinct images — see `docs/specification.md` §4.3 for the details of this correction). These 20 images match exactly the 20 DMC colours in the legend (page 17): one image per colour, already combining a flat background fill and a symbol drawn on top in a contrasting colour — confirmed visually (`doc.extract_image` + Pillow).
- Page 17: complete text legend (like page 11 of `cafe-brasserie-charting-export`), 20 DMC colours with code, name and **exact stitch count per colour**, and the dimensions stated plainly ("217x206 Stitches"). Reuses the same 20 images as the grid pages (as a preview, one per row) — it is neither its image size nor its reuse rate that excludes it from grid extraction, but the absence of two-dimensional axis numbers (its images are aligned in a single vertical column, never tiled on a grid).
- Page 18: assembly map of the 15 grid pages (not a working page), with 15 much larger (207×294 pt), non-square (ratio ≈ 0.70) images, each used only once — **to be excluded as well**, by the same kind of structural measurement as page 1 (size/shape of the placed images), never an exclusion assumed from page position.
- **No extraction by coloured rectangle or vector path will work on this file** — this is the test case that checks that the type E connector (closed catalogue of images to classify) is invoked instead of the B/C connectors.
- **Matching each catalogue image's background colour to the nearest DMC code (even restricted to the legend's 20 codes) turns out to be unreliable on this file** (12 of the 20 images misidentified, measured): the reliable signal, verified exact, used by `detect_type_e` is each image's total number of placements, which matches very exactly the stitch count declared by the legend for each colour — perceptual colour only serves as an explicit fallback, never as a primary signal, for this particular connector.

## Adding a new fixture

See the `.claude/skills/add-import-connector/` skill — every new PDF type encountered in production and not covered by these six cases should ideally become a new fixture here, with its expected values documented in the same way.
