"""Login, first-launch setup and "my account" routes (Lot 10, issue #77).

The only API routes reachable without a session, besides `/api/health`, are
here: the status the frontend reads at startup, the first-launch setup (only
while no profile exists), the profile list of the login screen, and the
login itself.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import accounts
from app.auth import (
    CurrentUser,
    client_address,
    close_session,
    login_throttle,
    open_session,
    require_client_header,
    session_token,
    user_for_request,
    verify_password,
)
from app.db import get_session
from app.http import api_error
from app.models import User
from app.schemas import (
    AuthStatus,
    LoginRequest,
    MeUpdate,
    PasswordChange,
    ProfileCard,
    SetupRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def initials_of(user: User) -> str:
    return (user.first_name[:1] + user.last_name[:1]).upper()


def avatar_hue_of(user_id: str) -> int:
    return int(hashlib.sha256(user_id.encode("ascii")).hexdigest()[:8], 16) % 360


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role="admin" if user.role == "admin" else "user",
        initials=initials_of(user),
        avatar_hue=avatar_hue_of(user.id),
        created_at=user.created_at,
    )


@router.get("/status", response_model=AuthStatus, summary="Setup state and current profile")
def status(request: Request, session: Annotated[Session, Depends(get_session)]) -> AuthStatus:
    user = user_for_request(session, request)
    return AuthStatus(
        setup_required=not accounts.has_users(session),
        user=user_out(user) if user is not None else None,
    )


@router.post(
    "/setup",
    response_model=UserOut,
    status_code=201,
    summary="First launch: create the first admin",
    dependencies=[Depends(require_client_header)],
)
def setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> UserOut:
    admin = accounts.create_first_admin(
        session,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password=payload.password,
    )
    open_session(session, admin, request, response)
    return user_out(admin)


@router.get("/profiles", response_model=list[ProfileCard], summary="Profiles of the login screen")
def profiles(session: Annotated[Session, Depends(get_session)]) -> list[ProfileCard]:
    users = session.execute(select(User).order_by(User.first_name, User.created_at)).scalars()
    return [
        ProfileCard(
            id=user.id,
            first_name=user.first_name,
            initials=initials_of(user),
            avatar_hue=avatar_hue_of(user.id),
        )
        for user in users
    ]


@router.post(
    "/login",
    response_model=UserOut,
    summary="Log in to a profile",
    dependencies=[Depends(require_client_header)],
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> UserOut:
    client = client_address(request)
    retry_after = login_throttle.retry_after(client, payload.user_id)
    if retry_after > 0:
        raise api_error(429, "login_throttled", seconds=retry_after)

    user = session.get(User, payload.user_id)
    if not verify_password(payload.password, user.password_hash if user else None):
        login_throttle.record_failure(client, payload.user_id)
        raise api_error(401, "login_failed")
    assert user is not None

    login_throttle.reset(client, payload.user_id)
    open_session(session, user, request, response)
    return user_out(user)


@router.post(
    "/logout",
    status_code=204,
    summary="Log out of this device",
    dependencies=[Depends(require_client_header)],
)
def logout(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> Response:
    response = Response(status_code=204)
    close_session(session, request, response)
    return response


@router.get("/me", response_model=UserOut, summary="My profile")
def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.patch("/me", response_model=UserOut, summary="Edit my profile")
def update_me(
    payload: MeUpdate, user: CurrentUser, session: Annotated[Session, Depends(get_session)]
) -> UserOut:
    accounts.update_profile(
        session,
        user,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    session.commit()
    return user_out(user)


@router.post("/me/password", status_code=204, summary="Change my password")
def change_password(
    payload: PasswordChange,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise api_error(400, "current_password_wrong")
    accounts.set_password(
        session, user, payload.new_password, keep_token=session_token(session, request)
    )
    session.commit()
    return Response(status_code=204)
