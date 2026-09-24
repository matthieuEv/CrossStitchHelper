"""Reusable recipe library — Lot 6 (specification §8.7, §9). A recipe
associates a file's fingerprint (`app/fingerprint.py`) with a strictly
geometric/structural subset of the validated import configuration
(`app/schemas.py::RecipeConfig`) — never its creative content. Automatic
matching when a new file with the same fingerprint is uploaded happens in
`app/api/imports.py::_run_auto_detection`, not here: this module only
manages the library's lifecycle (create, list, delete)."""

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
    """The most used recipe for this fingerprint, otherwise the most recent
    — used by `app/api/imports.py` to pre-fill a new job without ever
    imposing a choice when several recipes coexist."""
    return session.execute(
        select(Recipe)
        .where(Recipe.fingerprint == fingerprint)
        .order_by(Recipe.usage_count.desc(), Recipe.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


@router.get("", response_model=list[RecipeOut], summary="Recipe library")
def list_recipes(session: Annotated[Session, Depends(get_session)]) -> list[RecipeOut]:
    recipes = session.execute(select(Recipe).order_by(Recipe.created_at.desc())).scalars().all()
    return [_recipe_out(recipe) for recipe in recipes]


@router.post(
    "",
    response_model=RecipeOut,
    summary="Save an import's configuration as a recipe",
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


@router.delete("/{recipe_id}", status_code=204, summary="Delete a recipe")
def delete_recipe(recipe_id: str, session: Annotated[Session, Depends(get_session)]) -> None:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise api_error(404, "recipe_not_found")
    session.delete(recipe)
    session.commit()
