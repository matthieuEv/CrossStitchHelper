#!/usr/bin/env python
"""Inject the 255×180 demo pattern into the database (Lot 1).

Usage: from `backend/`, with the virtual environment activated:

    python scripts/seed_demo_pattern.py [--force]

`--force` recreates the pattern if it already exists (losing its progress).
Without this option, the script does nothing if the pattern is already
present — a re-import must never overwrite progress already checked.
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
        "--force", action="store_true", help="Recreate the pattern if it already exists."
    )
    args = parser.parse_args()

    upgrade_to_head()
    with get_session_factory()() as session:
        pattern = seed_demo_pattern(session, force=args.force)
        print(f"Demo pattern ready: {pattern.id} ({pattern.width}×{pattern.height})")


if __name__ == "__main__":
    main()
