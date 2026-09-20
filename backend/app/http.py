"""Petits utilitaires HTTP partagés entre routes (téléchargements, erreurs)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException

from app.schemas import ApiErrorDetail


def content_disposition(filename: str) -> str:
    """Un nom de motif est arbitraire (accents, tirets cadratins, etc.) — les
    en-têtes HTTP, eux, ne le sont pas : latin-1 strict. RFC 6266 fournit le
    repli standard (``filename`` ASCII + ``filename*`` UTF-8 pourcent-encodé)
    plutôt que de dégrader silencieusement le nom affiché au téléchargement.
    """
    safe = filename.replace("/", "-").encode("ascii", errors="replace").decode("ascii")
    encoded = quote(filename.replace("/", "-"), safe="")
    return f'attachment; filename="{safe}"; filename*=UTF-8\'\'{encoded}'


def api_error(status_code: int, code: str, **params: str | int | float) -> HTTPException:
    """Construit une `HTTPException` dont le corps est un `ApiErrorDetail`
    (audit des traductions, Lot 8) — jamais un message déjà formaté côté
    serveur, traduit côté client via la clé `error.<code>`
    (`frontend/src/i18n/fr.ts`/`en.ts`)."""
    detail = ApiErrorDetail(code=code, params=params).model_dump()
    return HTTPException(status_code=status_code, detail=detail)
