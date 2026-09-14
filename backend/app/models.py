"""Modèles SQLAlchemy.

Au Lot 0, ce module ne contient délibérément qu'une table de métadonnées
d'instance. Le modèle métier complet — ``patterns``, ``palette_entries``,
``grids``, ``progress``, ``progress_events`` — arrive au Lot 1 (voir
``docs/roadmap.md``), avec la contrainte structurante rappelée dans
``CLAUDE.md`` : **la progression est stockée séparément de la grille**, pour
qu'un ré-import ne puisse jamais écraser le travail déjà coché.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AppMeta(Base):
    """Métadonnées de l'instance, sous forme clé/valeur.

    Sert deux besoins concrets : donner une première migration non vide (donc
    une chaîne Alembic réellement vérifiée de bout en bout), et permettre au
    point de santé de prouver que la base répond en lecture, pas seulement
    que le fichier existe.
    """

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"AppMeta(key={self.key!r}, value={self.value!r})"
