"""Profile management rules (Lot 10, issue #77).

Kept out of the routes so that the API (`app/api/auth.py`,
`app/api/users.py`), the restore (`app/backup.py`) and the command line
(`app/cli.py`) apply exactly the same rules — above all the one no library
provides: **there is always at least one admin**, otherwise nobody could
manage profiles any more.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import end_sessions, hash_password
from app.http import api_error
from app.models import ImportJob, Pattern, User

ROLES = ("admin", "user")


def normalise_email(email: str) -> str:
    return email.strip().lower()


def admin_count(session: Session) -> int:
    return session.execute(
        select(func.count()).select_from(User).where(User.role == "admin")
    ).scalar_one()


def has_users(session: Session) -> bool:
    return session.execute(select(User.id).limit(1)).first() is not None


def _check_email_free(session: Session, email: str, *, except_id: str | None = None) -> None:
    statement = select(User.id).where(User.email == email)
    if except_id is not None:
        statement = statement.where(User.id != except_id)
    if session.execute(statement).first() is not None:
        raise api_error(409, "email_taken")


def create_user(
    session: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    role: str,
    password: str,
) -> User:
    email = normalise_email(email)
    _check_email_free(session, email)
    user = User(
        id=uuid.uuid4().hex,
        email=email,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        role=role,
        password_hash=hash_password(password),
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as error:  # two concurrent creations with one email
        session.rollback()
        raise api_error(409, "email_taken") from error
    return user


def create_first_admin(
    session: Session, *, email: str, first_name: str, last_name: str, password: str
) -> User:
    """First-launch setup: only while the instance has no profile at all.

    The new admin receives every pattern and import job that has no owner —
    the data of an instance upgraded from the single-user version, or the
    demo pattern seeded before setup — so nothing that existed before
    profiles is lost or left invisible."""
    if has_users(session):
        raise api_error(409, "setup_already_done")
    admin = create_user(
        session,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role="admin",
        password=password,
    )
    session.execute(update(Pattern).where(Pattern.owner_id.is_(None)).values(owner_id=admin.id))
    session.execute(
        update(ImportJob).where(ImportJob.owner_id.is_(None)).values(owner_id=admin.id)
    )
    session.commit()
    return admin


def first_admin_id(session: Session) -> str | None:
    """The oldest admin, owner of data created outside any request (the seed
    script run on an instance that already has profiles)."""
    return session.execute(
        select(User.id).where(User.role == "admin").order_by(User.created_at).limit(1)
    ).scalar_one_or_none()


def update_profile(
    session: Session,
    user: User,
    *,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    if email is not None:
        email = normalise_email(email)
        _check_email_free(session, email, except_id=user.id)
        user.email = email
    if first_name is not None:
        user.first_name = first_name.strip()
    if last_name is not None:
        user.last_name = last_name.strip()


def set_role(session: Session, user: User, role: str) -> None:
    if user.role == "admin" and role != "admin":
        user.role = role
        session.flush()
        ensure_an_admin_remains(session)
    else:
        user.role = role


def set_password(
    session: Session, user: User, password: str, *, keep_token: str | None = None
) -> None:
    """Replace a password and end the profile's sessions — every one of
    them after an admin reset, every one but the current device's after a
    change made by the profile itself (`keep_token`)."""
    user.password_hash = hash_password(password)
    end_sessions(session, user.id, keep_token=keep_token)


def delete_user(session: Session, user: User) -> int:
    """Delete a profile together with its personal library (private: no
    admin inherits it). Returns the number of patterns deleted with it."""
    patterns = session.execute(select(Pattern).where(Pattern.owner_id == user.id)).scalars().all()
    for pattern in patterns:
        session.delete(pattern)
    session.delete(user)
    session.flush()
    ensure_an_admin_remains(session)
    return len(patterns)


def ensure_an_admin_remains(session: Session) -> None:
    """Called after a demotion or a deletion has been flushed, inside the
    same transaction: if it left no admin, undo everything and refuse."""
    if admin_count(session) == 0:
        session.rollback()
        raise api_error(409, "last_admin")
