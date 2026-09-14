"""Application programmatique des migrations Alembic.

Sur une instance auto-hébergée, personne ne veut lancer une commande de
migration à la main après chaque mise à jour de l'image. Le conteneur applique
donc lui-même les migrations au démarrage.
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
    logger.info("Application des migrations sur %s", settings.database_path)
    command.upgrade(build_alembic_config(), "head")
