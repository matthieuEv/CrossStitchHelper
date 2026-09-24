"""Configuration of the self-hosted instance.

Every setting can be overridden by an environment variable prefixed with
``CSH_`` (for example ``CSH_DATA_DIR=/var/lib/crossstitchhelper``), which
makes it possible to configure a container without touching the code or a
mounted file.

Guiding principle: **a single directory contains all user data**. It is the
only path the user needs to back up, and the only volume to declare in
``docker-compose.yml``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend runtime settings."""

    model_config = SettingsConfigDict(
        env_prefix="CSH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    """Single directory containing the SQLite database and user files."""

    app_version: str = "v0.0.0-dev"
    """Version shown in the interface and by `/api/health`.

    Injected when the Docker image is built (`ARG VERSION` in the
    `Dockerfile`) from the git tag that triggers
    `.github/workflows/release.yml` — never maintained by hand in the code.
    Defaults to ``v0.0.0-dev``, including in development, as long as no
    version has been injected.
    """

    frontend_dist: Path | None = None
    """Directory of the built frontend.

    Absent in development: the Vite server serves the frontend and the
    backend only answers on ``/api``. Set in the Docker image, where the same
    process serves the API and the static files (a single image, a single
    port — see specification §3).
    """

    database_filename: str = "crossstitchhelper.db"

    run_migrations_on_startup: bool = True
    """Apply Alembic migrations at startup.

    True by default: on a self-hosted instance, nobody wants to have to run a
    migration command by hand after every update.
    """

    import_max_upload_mb: int = 40
    """Maximum size of a file dropped into the import wizard (Lot 2)."""

    run_auto_backup_loop: bool = True
    """Start the daily automatic backup loop (Lot 8, `app/auto_backup.py`)
    when the process launches.

    True by default, on the same principle as ``run_migrations_on_startup``:
    only the tests disable it, so as not to run a background loop in each of
    them."""

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_filename

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    @property
    def imports_dir(self) -> Path:
        """Temporary drop area for files being imported.

        The source PDF or photo is never kept beyond extraction (CLAUDE.md):
        each ``<job_id>/`` subdirectory is deleted as soon as the
        corresponding job is validated (``commit``).
        """
        return self.data_dir / "imports"

    @property
    def backups_dir(self) -> Path:
        """Snapshots written by the daily automatic backup (Lot 8,
        `app/auto_backup.py`) — in the same single volume as everything else
        (`database_path`), so that backing up `data_dir` (README) covers them
        too with no extra configuration."""
        return self.data_dir / "backups"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Settings cached for the lifetime of the process.

    Tests call ``get_settings.cache_clear()`` after changing the
    environment.
    """
    return Settings()
