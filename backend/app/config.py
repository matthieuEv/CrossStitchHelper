"""Configuration de l'instance auto-hébergée.

Chaque réglage est surchargeable par une variable d'environnement préfixée
``CSH_`` (par exemple ``CSH_DATA_DIR=/var/lib/crossstitchhelper``), ce qui
permet de configurer un conteneur sans toucher au code ni à un fichier monté.

Principe directeur : **un seul répertoire contient toute la donnée
utilisateur**. C'est le seul chemin que l'utilisateur doit sauvegarder, et le
seul volume à déclarer dans ``docker-compose.yml``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Réglages d'exécution du backend."""

    model_config = SettingsConfigDict(
        env_prefix="CSH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    """Répertoire unique contenant la base SQLite et les fichiers utilisateur."""

    frontend_dist: Path | None = None
    """Répertoire du frontend construit.

    Absent en développement : le serveur Vite sert le frontend et le backend ne
    répond que sur ``/api``. Renseigné dans l'image Docker, où le même
    processus sert l'API et les fichiers statiques (une seule image, un seul
    port — voir le cahier des charges §3).
    """

    database_filename: str = "crossstitchhelper.db"

    run_migrations_on_startup: bool = True
    """Applique les migrations Alembic au démarrage.

    Vrai par défaut : sur une instance auto-hébergée, personne ne veut avoir à
    lancer une commande de migration à la main après chaque mise à jour.
    """

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_filename

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Réglages mis en cache pour la durée du processus.

    Les tests appellent ``get_settings.cache_clear()`` après avoir modifié
    l'environnement.
    """
    return Settings()
