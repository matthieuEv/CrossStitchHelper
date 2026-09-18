"""Schémas Pydantic de l'API (cahier des charges §9)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PaletteEntryOut(BaseModel):
    index_in_grid: int
    brand: str
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_svg: str | None = None
    strands_full: int | None = None
    strands_back: int | None = None
    count_full: int
    count_half: int
    count_quarter: int
    count_french: int
    count_beads: int
    backstitch_length_cm: float | None = None

    model_config = {"from_attributes": True}


class PatternSummary(BaseModel):
    """Ce qu'il faut pour une vignette de la bibliothèque (§7.1)."""

    id: str
    name: str
    width: int
    height: int
    palette_count: int
    stitched_count: int
    cell_count: int
    percent: int
    created_at: datetime
    updated_at: datetime


class PatternDetail(BaseModel):
    id: str
    owner_id: str | None
    name: str
    source_filename: str | None
    fabric_count: int | None
    width: int
    height: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    palette: list[PaletteEntryOut]

    model_config = {"from_attributes": True}


class BackstitchSegment(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    palette_index: int


class FrenchKnot(BaseModel):
    x: float
    y: float
    palette_index: int


class GridOut(BaseModel):
    pattern_id: str
    width: int
    height: int
    encoding: str
    version: int
    layer_full: str = Field(description="Uint16Array encodée en base64, ligne par ligne.")
    layer_half: str | None = None
    layer_quarter: str | None = None
    backstitch: list[BackstitchSegment]
    french_knots: list[FrenchKnot]


class ProgressOut(BaseModel):
    pattern_id: str
    version: int
    stitched_count: int
    cell_count: int
    bitmap: str = Field(description="1 bit par case, encodé en base64, ligne par ligne.")


class ProgressOp(BaseModel):
    """Une modification de case, exprimée en état absolu — donc idempotente
    (cahier des charges §9 : « cocher une case est une opération idempotente,
    ce qui rend les conflits triviaux à résoudre »)."""

    index: int = Field(ge=0)
    stitched: bool


class ProgressSyncRequest(BaseModel):
    base_version: int = Field(ge=0, description="Dernière version de progression connue du client.")
    ops: list[ProgressOp] = Field(default_factory=list)


class ProgressSyncResponse(BaseModel):
    version: int
    stitched_count: int
    conflict: bool = Field(
        description="Vrai si le client avait manqué des changements faits par un autre appareil."
    )
    missing_ops: list[ProgressOp] = Field(
        description=(
            "Opérations appliquées par d'autres appareils depuis `base_version`, "
            "à rejouer côté client."
        )
    )


# --- Historique d'activité (Lot 3, cahier des charges §11) -----------------
#
# Dérivé de `progress_events`, jamais stocké séparément : le journal des
# deltas déjà écrit pour la synchronisation multi-appareils (Lot 1) est la
# seule source de vérité de « qui a brodé quand ».


class ActivityDayOut(BaseModel):
    """Cases brodées un jour donné des 7 derniers jours glissants."""

    weekday: int = Field(ge=0, le=6, description="0 = lundi, ISO.")
    stitches: int


class ActivitySessionOut(BaseModel):
    """Une séance = des événements de progression sans coupure de plus de 30 min."""

    hours_ago: float
    stitches: int
    minutes: int


class PatternActivityOut(BaseModel):
    activity: list[ActivityDayOut]
    sessions: list[ActivitySessionOut]


# --- Assistant d'import (Lot 2, cahier des charges §7.2, §9) ---------------
#
# Lot 2 : aucune détection automatique, `ImportCrop`, dimensions et palette
# sont entièrement saisis par l'utilisateur dans l'assistant.
#
# Lot 4 (`detected_cells`, `ImportDetection`) : pour un PDF de type A
# reconnu, `app/type_a.py` pré-remplit `columns`/`rows`/`palette` et une
# grille de fond — l'utilisateur corrige toujours via le même mécanisme de
# zones peintes (`fills`) qu'en Lot 2, jamais une proposition imposée
# (cahier des charges §4.4 : « jamais un résultat imposé »).


class ImportCrop(BaseModel):
    """Cadrage de la page, en pourcentage de chaque bord (0-49)."""

    left: float = Field(ge=0, le=49)
    top: float = Field(ge=0, le=49)
    right: float = Field(ge=0, le=49)
    bottom: float = Field(ge=0, le=49)


class ImportPaletteEntry(BaseModel):
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_svg: str | None = None
    """Symbole réel découpé depuis le PDF (Lot 4, `detect_type_a`) — absent
    pour une entrée saisie à la main (Lot 2), qui reste rendue via
    `symbol_key`. Voir `app.type_a.SymbolGlyphLocation`."""


class ImportFillZone(BaseModel):
    """Une zone peinte d'un même index de palette — voir `app.imports_engine.apply_fills`.

    ``palette_index`` à 0 efface la zone (la ramène à « case vide »), même
    convention que le blob de grille (§6.3) : c'est ce qui permet de corriger
    une zone mal peinte sans avoir à retirer l'entrée de la liste.
    """

    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    palette_index: int = Field(ge=0)


class ImportConfig(BaseModel):
    crop_by_page: dict[str, ImportCrop] = Field(
        default_factory=dict,
        description=(
            "Cadrage manuel, par numéro de page (clé str car JSON) — une page non "
            "présente n'a pas encore été cadrée par l'utilisateur. Repère purement "
            "visuel pour aider à compter les cases, jamais consommé par l'extraction."
        ),
    )
    columns: int | None = Field(default=None, ge=1, le=1000)
    rows: int | None = Field(default=None, ge=1, le=1000)
    palette: list[ImportPaletteEntry] = Field(default_factory=list)
    fills: list[ImportFillZone] = Field(default_factory=list)
    detected_cells: list[int] | None = Field(
        default=None,
        description=(
            "Grille proposée par la détection automatique (Lot 4), même convention "
            "que le blob de grille : longueur columns*rows, 0 = case vide, n = index "
            "1-based dans `palette`. `fills` s'applique par-dessus, jamais en dessous."
        ),
    )
    uncertain_cells: list[int] | None = Field(
        default=None,
        description=(
            "Index (0-based, dans `detected_cells`) des cases que la détection "
            "automatique de type B/C (Lot 5) signale explicitement comme incertaines "
            "— couleur douteuse et/ou symbole ambigu. Jamais consommé par "
            "l'extraction elle-même, purement indicatif pour l'assistant d'import : "
            "une case incertaine n'est jamais fausse en silence (règle impérative du "
            "`pdf-extraction-specialist`)."
        ),
    )


class ImportConfigPatch(BaseModel):
    """Comme `ImportConfig`, mais chaque champ fourni remplace entièrement
    l'existant plutôt que de le fusionner finement — le client renvoie
    toujours l'état complet qu'il détient (mêmes principes que `done` côté
    suivi), ce qui rend une resynchronisation triviale après une navigation
    avant/arrière dans l'assistant."""

    crop_by_page: dict[str, ImportCrop] | None = None
    columns: int | None = Field(default=None, ge=1, le=1000)
    rows: int | None = Field(default=None, ge=1, le=1000)
    palette: list[ImportPaletteEntry] | None = None
    fills: list[ImportFillZone] | None = None
    detected_cells: list[int] | None = None
    uncertain_cells: list[int] | None = None


class ImportPreview(BaseModel):
    """La grille assemblée à partir de la configuration courante — absente
    tant que `columns`/`rows`/`palette` ne sont pas encore renseignés."""

    width: int
    height: int
    cell_count: int
    filled_count: int
    layer_full: str = Field(description="Uint16Array encodée en base64, comme `GridOut`.")
    palette: list[ImportPaletteEntry]


class ImportDetection(BaseModel):
    """Résumé de la détection automatique (Lots 4-5) — jamais une certitude,
    toujours un score exploitable pour que l'assistant d'import invite à
    vérifier plutôt qu'à faire confiance aveuglément (§4.4)."""

    grid_type: str = Field(description='"A", "B", "C" ou "E" — voir cahier des charges §4.4.')
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class ImportAppliedRecipe(BaseModel):
    """Recette (Lot 6) dont `crop_by_page` a été repris pour ce job — jamais
    les dimensions ni la palette, voir `app/models.py::Recipe`."""

    id: str
    label: str


class ImportJobOut(BaseModel):
    id: str
    status: str
    kind: str
    page_count: int
    source_filename: str
    pattern_id: str | None
    config: ImportConfig
    preview: ImportPreview | None
    detection: ImportDetection | None = None
    detecting: bool = Field(
        default=False,
        description="Détection automatique (Lot 4) en cours en tâche de fond pour ce PDF.",
    )
    applied_recipe: ImportAppliedRecipe | None = None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class ImportCommitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fabric_count: int | None = Field(default=None, ge=1, le=64)


class ImportCommitResponse(BaseModel):
    pattern_id: str


# --- Recettes réutilisables (Lot 6, cahier des charges §8.7, §6.2) ---------


class RecipeConfig(BaseModel):
    """Le sous-ensemble de `ImportConfig` qu'une recette peut porter —
    volontairement restreint aux paramètres géométriques/structurels
    (`CLAUDE.md` : jamais le contenu créatif du motif). Ni dimensions, ni
    palette, ni zones peintes : elles diffèrent toujours d'un motif à
    l'autre, même au sein d'un même éditeur."""

    crop_by_page: dict[str, ImportCrop] = Field(default_factory=dict)


class RecipeCreate(BaseModel):
    job_id: str
    label: str = Field(min_length=1, max_length=200)


class RecipeOut(BaseModel):
    id: str
    fingerprint: str
    label: str
    grid_type: str
    config: RecipeConfig
    created_at: datetime
    usage_count: int
