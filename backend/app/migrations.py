"""Programmatic application of Alembic migrations.

On a self-hosted instance, nobody wants to run a migration command by hand
after every image update. The container therefore applies migrations itself
at startup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.config import get_settings

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def build_alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def upgrade_to_head() -> None:
    settings = get_settings()
    settings.ensure_directories()
    logger.info("Applying migrations to %s", settings.database_path)
    command.upgrade(build_alembic_config(), "head")
