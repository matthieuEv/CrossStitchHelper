"""Application FastAPI.

Un seul processus sert l'API **et** le frontend construit : c'est ce qui permet
de livrer une image Docker unique, sur un seul port, sans reverse proxy à
configurer (cahier des charges §3). En développement, ``frontend_dist`` est
absent : le serveur Vite sert le frontend et ce processus ne répond que sur
``/api``.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api.backup import router as backup_router
from app.api.health import router as health_router
from app.api.imports import router as imports_router
from app.api.patterns import router as patterns_router
from app.api.recipes import router as recipes_router
from app.auto_backup import run_auto_backup_loop
from app.config import get_settings
from app.db import get_session_factory
from app.migrations import upgrade_to_head

logger = logging.getLogger(__name__)

# Vite écrit les fichiers d'application sous `assets/` avec un condensat dans
# le nom : leur contenu ne change jamais pour une URL donnée.
_IMMUTABLE_PREFIXES = ("assets/",)

# Ces fichiers pilotent la mise à jour de la PWA. Les mettre en cache
# empêcherait un appareil déjà installé de recevoir une nouvelle version.
_NEVER_CACHED = frozenset(
    {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest", "workbox-window.prod.es5.js"}
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_directories()
    if settings.run_migrations_on_startup:
        upgrade_to_head()
    logger.info(
        "CrossStitchHelper %s prêt — données dans %s", settings.app_version, settings.data_dir
    )

    task: asyncio.Task[None] | None = None
    if settings.run_auto_backup_loop:
        task = asyncio.create_task(
            run_auto_backup_loop(get_session_factory(), settings.backups_dir)
        )

    yield

    if task is not None:
        task.cancel()
        await task


def _cache_headers(relative_path: str) -> dict[str, str]:
    if relative_path in _NEVER_CACHED:
        return {"Cache-Control": "no-cache"}
    if relative_path.startswith(_IMMUTABLE_PREFIXES):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    return {"Cache-Control": "public, max-age=3600"}


def _register_frontend(app: FastAPI, dist_dir: Path) -> None:
    # Sans cet enregistrement, le manifeste est servi en `text/plain` et Safari
    # refuse d'installer la PWA sur l'écran d'accueil.
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    dist = dist_dir.resolve()

    @app.get("/{requested_path:path}", include_in_schema=False)
    def serve_frontend(requested_path: str) -> FileResponse:
        # Une route API inexistante doit rester une erreur JSON. Sans ce
        # garde-fou, elle renverrait la coquille HTML de l'application et le
        # client verrait une erreur de parsing JSON incompréhensible.
        if requested_path == "api" or requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Route API inconnue")

        candidate = (dist / requested_path).resolve()
        if candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate, headers=_cache_headers(requested_path))

        # Toute autre URL est une route applicative gérée côté client.
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=404,
                detail="Frontend non construit : lancez `npm run build` dans frontend/.",
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CrossStitchHelper",
        version=settings.app_version,
        summary="API locale de suivi de grilles de point de croix.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(patterns_router, prefix="/api")
    app.include_router(imports_router, prefix="/api")
    app.include_router(recipes_router, prefix="/api")
    app.include_router(backup_router, prefix="/api")

    # Enregistré en dernier : la route attrape-tout ne doit jamais masquer
    # une route d'API.
    if settings.frontend_dist is not None:
        _register_frontend(app, settings.frontend_dist)
    else:
        logger.info("Aucun frontend construit configuré — le backend ne sert que /api.")

    return app


app = create_app()
