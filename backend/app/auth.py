"""Authentication: password hashing, sessions, request guards (Lot 10, issue #77).

What is delegated, and what is not:

- **Password hashing is delegated to `pwdlib`** (Argon2id, its recommended
  parameters), the maintained replacement for `passlib`. Never hand-rolled.
- **Sessions are a small server-side table** (`app/models.py::UserSession`):
  no maintained library offers cookie sessions on top of *synchronous*
  SQLAlchemy (`fastapi-users`, the only full-featured candidate, requires an
  async database layer and is in maintenance mode — see
  `docs/specification.md` §13). The browser holds an opaque random token in
  an HttpOnly cookie, never a JWT and never anything script-readable: on an
  iPhone home-screen PWA, script-writable storage is purged after a week of
  inactivity, while a server-set HttpOnly cookie is kept.
- **OpenID Connect (later)** will go through Authlib's client and end in the
  same `open_session` call as the password login — nothing here assumes a
  password exists.

Cross-site request forgery: the cookie is ``SameSite=Lax`` (no cross-site
POST carries it), and every state-changing request authenticated by that
cookie must also carry the ``X-CSH-Client`` header (`require_client_header`),
which a page from another origin cannot add without a CORS preflight this API
never grants. That second check also covers *same-site* origins (another app
on a sibling subdomain), which ``SameSite`` does not. A header rather than an
``Origin``/``Host`` comparison, because reverse proxies rewrite ``Host``
(nginx's default does) and would break every write behind them.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.http import api_error
from app.models import User, UserSession

COOKIE_NAME = "csh_session"

# A household logs in once per device and expects to stay logged in: a short
# idle timeout (OWASP's 15-30 minutes, meant for online services) would ask
# for a password at every stitching session. Sliding expiry, refreshed on
# use, with an absolute cap so that a stolen cookie does not live forever.
SESSION_IDLE_LIFETIME = timedelta(days=90)
SESSION_ABSOLUTE_LIFETIME = timedelta(days=365)
# Refreshing `last_seen_at`/`expires_at` on every request would turn every
# read into a write; once an hour is precise enough for a 90-day window.
_SESSION_TOUCH_INTERVAL = timedelta(hours=1)

_password_hash = PasswordHash.recommended()

# A pre-computed hash to verify against when the profile does not exist, so
# that a login attempt takes the same time whether or not the profile id is
# valid.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _as_aware(value: datetime) -> datetime:
    # SQLite does not keep the time zone (same caveat as `get_activity`,
    # `app/api/patterns.py`): every timestamp is written in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def open_session(session: Session, user: User, request: Request, response: Response) -> None:
    """Create a session for `user` and set its cookie on `response`."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        UserSession(
            id=uuid.uuid4().hex,
            user_id=user.id,
            token_hash=_token_hash(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_IDLE_LIFETIME,
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        )
    )
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_IDLE_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        # Plain HTTP on the home network (`http://nas:8765`) must keep
        # working: `Secure` only when the request really arrived over HTTPS
        # (uvicorn trusts the reverse proxy's `X-Forwarded-Proto`, see the
        # `Dockerfile`).
        secure=request.url.scheme == "https",
        path="/",
    )


def close_session(session: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token is not None:
        session.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
        session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


def end_sessions(session: Session, user_id: str, *, keep_token: str | None = None) -> None:
    """End every session of `user_id`, except the one holding `keep_token`
    (the device that just changed its own password stays logged in)."""
    statement = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_token is not None:
        statement = statement.where(UserSession.token_hash != _token_hash(keep_token))
    session.execute(statement)


def user_for_request(session: Session, request: Request) -> User | None:
    """The user whose valid session cookie came with `request`, if any."""
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return None
    row = session.execute(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    ).scalar_one_or_none()
    if row is None:
        return None

    now = datetime.now(UTC)
    created_at = _as_aware(row.created_at)
    if _as_aware(row.expires_at) <= now or created_at + SESSION_ABSOLUTE_LIFETIME <= now:
        session.delete(row)
        session.commit()
        return None

    if now - _as_aware(row.last_seen_at) >= _SESSION_TOUCH_INTERVAL:
        row.last_seen_at = now
        row.expires_at = min(now + SESSION_IDLE_LIFETIME, created_at + SESSION_ABSOLUTE_LIFETIME)
        session.commit()
    return row.user


def current_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> User:
    """FastAPI dependency: the logged-in user, or 401."""
    require_client_header(request)
    user = user_for_request(session, request)
    if user is None:
        raise api_error(401, "auth_required")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    """FastAPI dependency: the logged-in user if they are an admin, or 403."""
    if user.role != "admin":
        raise api_error(403, "admin_required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]


_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CLIENT_HEADER = "x-csh-client"


def require_client_header(request: Request) -> None:
    """FastAPI dependency: refuse a state-changing request that does not
    come from the application's own frontend (see the module docstring).
    `frontend/src/lib/api.ts` adds the header to every request."""
    if request.method in _UNSAFE_METHODS and CLIENT_HEADER not in request.headers:
        raise api_error(403, "client_header_missing")


class LoginThrottle:
    """Slows down password guessing, in memory (no Redis — single process).

    The login screen lists the profiles, so the profile id is no secret: only
    the password protects an account. Two limits over a sliding `window`:
    `per_client` failures for one (client address, profile) pair — what a
    family member mistyping hits — and `per_profile` failures for a profile
    from all addresses together, because the client address comes from a
    reverse proxy header that a guesser could vary (`Dockerfile`).
    """

    def __init__(
        self, per_client: int = 5, per_profile: int = 20, window: float = 300.0
    ) -> None:
        self.per_client = per_client
        self.per_profile = per_profile
        self.window = window
        self._failures: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: tuple[str, str], now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def _wait(self, recent: list[float], limit: int, now: float) -> int:
        if len(recent) < limit:
            return 0
        return max(1, int(self.window - (now - recent[-limit])) + 1)

    def retry_after(self, client: str, user_id: str) -> int:
        """Seconds to wait before a new attempt is accepted (0 if allowed)."""
        now = time.monotonic()
        with self._lock:
            return max(
                self._wait(self._recent((client, user_id), now), self.per_client, now),
                self._wait(self._recent(("*", user_id), now), self.per_profile, now),
            )

    def record_failure(self, client: str, user_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._failures.setdefault((client, user_id), []).append(now)
            self._failures.setdefault(("*", user_id), []).append(now)

    def reset(self, client: str, user_id: str) -> None:
        """A successful login clears this client's failures — not the
        profile-wide count, which someone else may be accumulating."""
        with self._lock:
            self._failures.pop((client, user_id), None)


login_throttle = LoginThrottle()


def client_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"
