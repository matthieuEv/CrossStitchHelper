"""Bibliothèque de recettes réutilisables — Lot 6 (cahier des charges §8.7,
§9). Une recette associe l'empreinte d'un fichier (`app/fingerprint.py`) à
un sous-ensemble strictement géométrique/structurel de la configuration
d'import validée (`app/schemas.py::RecipeConfig`) — jamais son contenu
créatif. Le rapprochement automatique à l'upload d'un nouveau fichier de
même empreinte se fait dans `app/api/imports.py::_run_auto_detection`, pas
ici : ce module ne fait que gérer le cycle de vie de la bibliothèque
(créer, lister, supprimer)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.http import api_error
from app.models import ImportJob, Recipe
from app.schemas import RecipeConfig, RecipeCreate, RecipeOut

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _recipe_out(recipe: Recipe) -> RecipeOut:
    return RecipeOut(
        id=recipe.id,
        fingerprint=recipe.fingerprint,
        label=recipe.label,
        grid_type=recipe.grid_type,
        config=RecipeConfig(**json.loads(recipe.config_json)),
        created_at=recipe.created_at,
        usage_count=recipe.usage_count,
    )


def find_matching_recipe(session: Session, fingerprint: str) -> Recipe | None:
    """La recette la plus utilisée pour cette empreinte, à défaut la plus
    récente — utilisé par `app/api/imports.py` pour pré-remplir un nouveau
    job sans jamais imposer un choix quand plusieurs recettes coexistent."""
    return session.execute(
        select(Recipe)
        .where(Recipe.fingerprint == fingerprint)
        .order_by(Recipe.usage_count.desc(), Recipe.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


@router.get("", response_model=list[RecipeOut], summary="Bibliothèque de recettes")
def list_recipes(session: Annotated[Session, Depends(get_session)]) -> list[RecipeOut]:
    recipes = session.execute(select(Recipe).order_by(Recipe.created_at.desc())).scalars().all()
    return [_recipe_out(recipe) for recipe in recipes]


@router.post(
    "",
    response_model=RecipeOut,
    summary="Enregistre la configuration d'un import comme recette",
)
def create_recipe(
    payload: RecipeCreate, session: Annotated[Session, Depends(get_session)]
) -> RecipeOut:
    job = session.get(ImportJob, payload.job_id)
    if job is None:
        raise api_error(404, "import_not_found")

    result: dict[str, Any] = json.loads(job.result_json)
    fingerprint = result.get("source_fingerprint")
    if fingerprint is None:
        raise api_error(400, "recipe_no_fingerprint")

    detection = result.get("detection") or {}
    grid_type = detection.get("grid_type")
    if grid_type not in ("A", "B", "C"):
        grid_type = "D"

    config = RecipeConfig(crop_by_page=result["config"].get("crop_by_page") or {})

    recipe = Recipe(
        id=uuid.uuid4().hex,
        fingerprint=fingerprint,
        label=payload.label,
        grid_type=grid_type,
        config_json=config.model_dump_json(),
        created_at=datetime.now(UTC),
        usage_count=0,
    )
    session.add(recipe)
    session.commit()
    return _recipe_out(recipe)


@router.delete("/{recipe_id}", status_code=204, summary="Supprime une recette")
def delete_recipe(recipe_id: str, session: Annotated[Session, Depends(get_session)]) -> None:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise api_error(404, "recipe_not_found")
    session.delete(recipe)
    session.commit()
