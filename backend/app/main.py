"""FastAPI application.

A single process serves the API **and** the built frontend: that is what
makes it possible to ship a single Docker image, on a single port, with no
reverse proxy to configure (specification §3). In development,
``frontend_dist`` is absent: the Vite server serves the frontend and this
process only answers on ``/api``.
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

# Vite writes application files under `assets/` with a hash in the name:
# their content never changes for a given URL.
_IMMUTABLE_PREFIXES = ("assets/",)

# These files drive the PWA update. Caching them would prevent an already
# installed device from receiving a new version.
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
        "CrossStitchHelper %s ready — data in %s", settings.app_version, settings.data_dir
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
    # Without this registration, the manifest is served as `text/plain` and
    # Safari refuses to install the PWA on the home screen.
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    dist = dist_dir.resolve()

    @app.get("/{requested_path:path}", include_in_schema=False)
    def serve_frontend(requested_path: str) -> FileResponse:
        # A non-existent API route must remain a JSON error. Without this
        # guard, it would return the application's HTML shell and the client
        # would see an incomprehensible JSON parsing error.
        if requested_path == "api" or requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Unknown API route")

        candidate = (dist / requested_path).resolve()
        if candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate, headers=_cache_headers(requested_path))

        # Any other URL is an application route handled on the client.
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=404,
                detail="Frontend not built: run `npm run build` in frontend/.",
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CrossStitchHelper",
        version=settings.app_version,
        summary="Local API for tracking cross-stitch charts.",
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

    # Registered last: the catch-all route must never shadow an API route.
    if settings.frontend_dist is not None:
        _register_frontend(app, settings.frontend_dist)
    else:
        logger.info("No built frontend configured — the backend only serves /api.")

    return app


app = create_app()
