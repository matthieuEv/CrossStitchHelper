"""Modèles SQLAlchemy.

Modèle métier complet du Lot 1 (voir ``docs/roadmap.md`` et le cahier des
charges §6) : ``patterns``, ``palette_entries``, ``grids``, ``progress``,
``progress_events``. Contrainte structurante rappelée dans ``CLAUDE.md`` :
**la progression est stockée séparément de la grille**, dans des tables
distinctes reliées uniquement par ``pattern_id`` — un ré-import ne touche
jamais à ``progress``.

``recipes`` (aussi présente au §6.2 du cahier des charges) n'existe pas
encore : elle appartient au Lot 6, qui n'a pas commencé.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class Pattern(Base):
    """Un motif importé (ou, avant le Lot 2, injecté directement en base).

    ``owner_id`` est nullable dès la V1 mono-utilisateur, pour ne pas fermer
    la porte au multi-utilisateurs plus tard (cahier des charges §5.2).
    """

    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fabric_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    import_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipe_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    palette_entries: Mapped[list[PaletteEntry]] = relationship(
        back_populates="pattern",
        cascade="all, delete-orphan",
        order_by="PaletteEntry.index_in_grid",
    )
    grid: Mapped[Grid | None] = relationship(back_populates="pattern", cascade="all, delete-orphan")
    progress: Mapped[Progress | None] = relationship(
        back_populates="pattern", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"Pattern(id={self.id!r}, name={self.name!r}, {self.width}x{self.height})"


class PaletteEntry(Base):
    """Une couleur de la palette d'un motif.

    ``index_in_grid`` est l'entier utilisé dans le blob de grille (§6.3) :
    0 signifie « case vide », donc les index de palette réelle commencent à 1.
    """

    __tablename__ = "palette_entries"
    __table_args__ = (UniqueConstraint("pattern_id", "index_in_grid"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index_in_grid: Mapped[int] = mapped_column(Integer, nullable=False)

    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rgb_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol_svg: Mapped[str | None] = mapped_column(Text, nullable=True)

    strands_full: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strands_back: Mapped[int | None] = mapped_column(Integer, nullable=True)

    count_full: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_half: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_quarter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_french: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_beads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backstitch_length_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    pattern: Mapped[Pattern] = relationship(back_populates="palette_entries")

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"PaletteEntry(pattern_id={self.pattern_id!r}, code={self.code!r})"


class Grid(Base):
    """Les couches de la grille d'un motif, compactées (§6.1).

    Une ligne par motif : ``pattern_id`` est à la fois clé primaire et clé
    étrangère (relation un-à-un stricte).
    """

    __tablename__ = "grids"

    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    layer_full: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    layer_half: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    layer_quarter: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    backstitch_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    french_knots_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    encoding: Mapped[str] = mapped_column(String(16), nullable=False, default="uint16le")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    pattern: Mapped[Pattern] = relationship(back_populates="grid")

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"Grid(pattern_id={self.pattern_id!r}, version={self.version})"


class Progress(Base):
    """Bitmap de progression d'un motif — séparé de ``Grid`` (§6.1).

    ``version`` est incrémenté à chaque delta appliqué (voir
    :mod:`app.api.patterns`) ; c'est la valeur comparée par le client pour
    détecter s'il a manqué des changements faits depuis un autre appareil.
    """

    __tablename__ = "progress"

    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    bitmap: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stitched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    pattern: Mapped[Pattern] = relationship(back_populates="progress")

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"Progress(pattern_id={self.pattern_id!r}, version={self.version})"


class ProgressEvent(Base):
    """Journal des deltas de progression appliqués, pour annulation et reprise
    multi-appareils (§6.2).

    ``version_after`` correspond à ``Progress.version`` immédiatement après
    l'application de cet événement : un client qui connaît une version plus
    ancienne peut donc récupérer, en une requête, tous les événements à
    rejouer pour rattraper l'état courant.
    """

    __tablename__ = "progress_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    ops_json: Mapped[str] = mapped_column(Text, nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return (
            f"ProgressEvent(pattern_id={self.pattern_id!r}, version_after={self.version_after})"
        )


class ImportJob(Base):
    """L'état d'un import en cours (assistant, Lot 2 — cahier des charges §6.2, §9).

    ``result_json`` porte à la fois ce que l'utilisateur a saisi dans
    l'assistant (``config`` : cadrage, dimensions, palette, zones peintes) et
    ce qui en a été calculé (``preview`` : la grille assemblée). Le Lot 2
    n'a aucun moteur de détection automatique — ``config`` est donc
    entièrement manuel, jamais déduit d'une analyse du fichier.
    """

    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    pattern_id: Mapped[str | None] = mapped_column(
        ForeignKey("patterns.id", ondelete="SET NULL"), nullable=True
    )
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"ImportJob(id={self.id!r}, status={self.status!r}, kind={self.kind!r})"
