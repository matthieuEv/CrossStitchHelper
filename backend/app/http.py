"""Petits utilitaires HTTP partagés entre routes (téléchargements de fichiers)."""

from __future__ import annotations

from urllib.parse import quote


def content_disposition(filename: str) -> str:
    """Un nom de motif est arbitraire (accents, tirets cadratins, etc.) — les
    en-têtes HTTP, eux, ne le sont pas : latin-1 strict. RFC 6266 fournit le
    repli standard (``filename`` ASCII + ``filename*`` UTF-8 pourcent-encodé)
    plutôt que de dégrader silencieusement le nom affiché au téléchargement.
    """
    safe = filename.replace("/", "-").encode("ascii", errors="replace").decode("ascii")
    encoded = quote(filename.replace("/", "-"), safe="")
    return f'attachment; filename="{safe}"; filename*=UTF-8\'\'{encoded}'
