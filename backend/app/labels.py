"""Pattern labels (issue #57): free text a user sorts their library with.

Labels have no table of their own — a label exists only through the patterns
that carry it, so an unused label disappears by itself. They are user
organisation, never pattern content: they stay out of `.cshp` exports and
import recipes.
"""

from __future__ import annotations

import json

MAX_LABEL_LENGTH = 40
MAX_LABELS_PER_PATTERN = 20


def normalize_labels(labels: list[str]) -> list[str]:
    """Trimmed, inner whitespace collapsed, empty ones dropped, duplicates
    removed ignoring case (the first spelling wins), in the order given."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        label = " ".join(raw.split())[:MAX_LABEL_LENGTH]
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            result.append(label)
    return result[:MAX_LABELS_PER_PATTERN]


def labels_from_json(value: str | None) -> list[str]:
    if not value:
        return []
    loaded = json.loads(value)
    return [label for label in loaded if isinstance(label, str)] if isinstance(loaded, list) else []


def labels_to_json(labels: list[str]) -> str:
    return json.dumps(normalize_labels(labels), ensure_ascii=False)
