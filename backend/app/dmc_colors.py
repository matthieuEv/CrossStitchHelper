"""Colour → DMC thread reference table (specification §8.5).

For type A (`app/type_a.py`), the PDF legend gives the DMC code as real
text — it is authoritative, so this module is **not** used for matching by
colorimetric distance here (that is type B/C, Lot 5). Its only role is to
provide an approximate display colour for the interface: the PDF carries no
explicit RGB value for each thread, only its name and code.

Deliberately limited to the codes encountered so far rather than a complete
DMC catalogue rebuilt from memory (risk of unverifiable errors) — a code
missing from this table is an explicitly handled case (`dmc_hex` returns
`None`), never a colour silently made up (mandatory rule of the
`pdf-extraction-specialist`, see `.claude/agents/`).
"""

from __future__ import annotations

# Usual RGB approximations for display — never used to identify a colour,
# only to represent it on screen once the code is already known from the
# legend text.
_DMC_HEX: dict[str, str] = {
    "157": "#abc1e1",
    "159": "#c4cfdd",
    "160": "#8da0bc",
    "161": "#7b93b4",
    "300": "#7b3f00",
    "301": "#b56132",
    "304": "#b0000c",
    "310": "#050505",
    "402": "#f0aa7d",
    "413": "#66686c",
    "608": "#fd5b27",
    "613": "#dfcdb6",
    "640": "#837156",
    "642": "#93805f",
    "666": "#e31d3c",
    "740": "#ff8c00",
    "741": "#ffa023",
    "742": "#ffc93c",
    "743": "#ffd965",
    "762": "#e9e9e9",
    "793": "#5c71ad",
    "794": "#8fa3d3",
    "814": "#6c000f",
    "839": "#5a4a3a",
    "840": "#8c7355",
    "938": "#372018",
    "946": "#f0521a",
    "3031": "#4b3423",
    "3756": "#e6f0f7",
    "3766": "#3e93a8",
    "3776": "#c6774f",
    "3856": "#f5c9a0",
    "b5200": "#ffffff",
}

FALLBACK_HEX = "#9a9a9a"
"""Neutral grey for a code unknown to the table — never a colour made up
from the name: the presence of this code in the result must always come with
a confidence warning on the caller's side."""


def dmc_hex(code: str) -> str | None:
    """`None` if the code is not in the table — up to the caller to flag it
    rather than hide the gap behind `FALLBACK_HEX`."""
    return _DMC_HEX.get(code.strip().lower())
