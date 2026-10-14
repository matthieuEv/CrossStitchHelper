"""Profile management, for admins only (Lot 10, issue #77).

A regular profile never reaches these routes: it only ever sees itself,
through `/api/auth/me`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import accounts
from app.api.auth import user_out
from app.auth import COOKIE_NAME, AdminUser, require_admin
from app.db import get_session
from app.http import api_error
from app.models import Pattern, User
from app.schemas import AdminUserOut, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


def _get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise api_error(404, "user_not_found")
    return user


def _admin_user_out(session: Session, user: User) -> AdminUserOut:
    pattern_count = session.execute(
        select(func.count()).select_from(Pattern).where(Pattern.owner_id == user.id)
    ).scalar_one()
    return AdminUserOut(**user_out(user).model_dump(), pattern_count=pattern_count)


@router.get("", response_model=list[AdminUserOut], summary="All profiles")
def list_users(session: Annotated[Session, Depends(get_session)]) -> list[AdminUserOut]:
    users = session.execute(select(User).order_by(User.first_name, User.created_at)).scalars()
    return [_admin_user_out(session, user) for user in users]


@router.post("", response_model=AdminUserOut, status_code=201, summary="Add a profile")
def create_user(
    payload: UserCreate, session: Annotated[Session, Depends(get_session)]
) -> AdminUserOut:
    user = accounts.create_user(
        session,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role,
        password=payload.password,
    )
    session.commit()
    return _admin_user_out(session, user)


@router.patch("/{user_id}", response_model=AdminUserOut, summary="Edit a profile")
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    admin: AdminUser,
    session: Annotated[Session, Depends(get_session)],
) -> AdminUserOut:
    user = _get_user(session, user_id)
    accounts.update_profile(
        session,
        user,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    if payload.role is not None:
        accounts.set_role(session, user, payload.role)
    if payload.password is not None:
        # An admin resetting their own password keeps the device they are
        # using, like `/api/auth/me/password`; anyone else's sessions all end.
        keep = request.cookies.get(COOKIE_NAME) if user.id == admin.id else None
        accounts.set_password(session, user, payload.password, keep_token=keep)
    session.commit()
    return _admin_user_out(session, user)


@router.delete("/{user_id}", status_code=204, summary="Delete a profile and its library")
def delete_user(user_id: str, session: Annotated[Session, Depends(get_session)]) -> Response:
    accounts.delete_user(session, _get_user(session, user_id))
    session.commit()
    return Response(status_code=204)
