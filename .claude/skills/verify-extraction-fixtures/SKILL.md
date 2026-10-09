---
name: verify-extraction-fixtures
description: Verifies the PDF extraction engine against the six reference fixtures and their expected values. Use after any change to the extraction engine (backend), before considering the task done.
---

# Verifying extraction against the reference fixtures

Procedure to follow after any change touching PDF structural analysis, grid detection, the type A/B/C/E parsers, or colour → DMC matching.

## 1. Identify the relevant fixtures

Six real PDFs cover the known A/B/C/E types (see `fixtures/README.md` for the full list of expected values, and `docs/specification.md` §4 for the details of each case):

- `fixtures/cafe-brasserie-charting-export/` — type A (embedded symbol font, text legend) → `backend/app/type_a.py`.
- `fixtures/winter-wreath-dmc/`, `fixtures/summer-flight-dmc/` — type C, trap case: the colour page already carries its own symbol paths, never blindly overlay a second page → `backend/app/type_bc.py`.
- `fixtures/botanical-citrus-dmc/`, `fixtures/cucurbit-dmc/` — type C, two-page overlay genuinely needed → `backend/app/type_bc.py`.
- `fixtures/river-and-mountains-laserarts/` — type E (closed catalogue of reused bitmap images, colour+symbol already combined) → `backend/app/type_e.py`. Also serves to check that the A/B/C connectors produce no false positive on this structurally very different file.

Any of these six files can, to the eye, seem to follow a structure different from its measured reality (`winter-wreath-dmc` is the direct proof, corrected in Lot 5 after an initially wrong description in the specification) — never trust a first visual examination or an already written description without re-checking it by measurement on the real file.

## 2. Run the extraction on each fixture affected by the change

Use the relevant backend extraction engine entry point (`detect_type_a`, `detect_type_bc`, `detect_type_e`) — see `docs/specification.md` §8 for the details of the pipeline stages: structural analysis → grid detection → specific parser → colour matching → assembly.

## 3. Compare with the expected values

The exact values (dimensions, number of colours, counts, page strategy) are in `fixtures/README.md` — do not copy them here, one place per piece of information (see `CLAUDE.md`). The `backend/tests/test_type_a.py`, `backend/tests/test_type_bc.py` and `backend/tests/test_type_e.py` suites already check them automatically; re-running them is the fastest way to do this comparison.

## 4. If there is a discrepancy

- If the discrepancy is minor and documented (low confidence score, or cell listed in `uncertain_cells`, correctly flagged): this is expected, the import wizard must allow manual correction — check that confidence flagging works, not that the result is perfect.
- If the discrepancy is silent (wrong value with no low confidence score or uncertain cell): it is a bug to fix before considering the task done. Never leave an incorrect extraction unflagged.

## 5. If the change covers a case not represented by the six fixtures

Consider adding a new fixture (see the `add-import-connector` skill) rather than validating only by one-off manual inspection — fixtures are what prevent a silent regression later.
