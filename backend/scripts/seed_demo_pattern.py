#!/usr/bin/env python
"""Injecte le motif de démonstration 255×180 en base (Lot 1).

Usage : depuis `backend/`, avec l'environnement virtuel activé :

    python scripts/seed_demo_pattern.py [--force]

`--force` recrée le motif s'il existe déjà (perd sa progression). Sans cette
option, le script ne fait rien si le motif est déjà présent — un ré-import
ne doit jamais écraser une progression déjà cochée.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_session_factory  # noqa: E402
from app.migrations import upgrade_to_head  # noqa: E402
from app.seed import seed_demo_pattern  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Recrée le motif s'il existe déjà."
    )
    args = parser.parse_args()

    upgrade_to_head()
    with get_session_factory()() as session:
        pattern = seed_demo_pattern(session, force=args.force)
        print(f"Motif de démonstration prêt : {pattern.id} ({pattern.width}×{pattern.height})")


if __name__ == "__main__":
    main()
