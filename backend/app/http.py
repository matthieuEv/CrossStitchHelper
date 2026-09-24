"""Small HTTP helpers shared between routes (downloads, errors)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException

from app.schemas import ApiErrorDetail


def content_disposition(filename: str) -> str:
    """A pattern name is arbitrary (accents, em dashes, etc.) — HTTP headers
    are not: strict latin-1. RFC 6266 provides the standard fallback (ASCII
    ``filename`` + percent-encoded UTF-8 ``filename*``) rather than silently
    degrading the name shown on download.
    """
    safe = filename.replace("/", "-").encode("ascii", errors="replace").decode("ascii")
    encoded = quote(filename.replace("/", "-"), safe="")
    return f'attachment; filename="{safe}"; filename*=UTF-8\'\'{encoded}'


def api_error(status_code: int, code: str, **params: str | int | float) -> HTTPException:
    """Build an `HTTPException` whose body is an `ApiErrorDetail`
    (translation audit, Lot 8) — never a message already formatted on the
    server, translated on the client via the `error.<code>` key
    (`frontend/src/i18n/fr.ts`/`en.ts`)."""
    detail = ApiErrorDetail(code=code, params=params).model_dump()
    return HTTPException(status_code=status_code, detail=detail)
