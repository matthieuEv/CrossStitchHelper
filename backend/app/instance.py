"""This instance's identity and the shared library's change counter
(Lot 11b, issue #78), kept in `AppMeta`.

- ``instance_id``: a random id made on first use, how a paired instance
  recognises this one (never derived from a host name or an address, which
  change).
- ``instance_name``: what a paired instance shows next to the shared
  patterns coming from here ("Shared by: Site B"), chosen by an admin.
- ``shared_seq``: incremented every time a shared pattern of this instance
  is added, renamed, replaced or removed. A subscribed instance remembers the
  last value it read and asks for what changed since (`app/federation.py`).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import AppMeta

_INSTANCE_ID = "instance_id"
_INSTANCE_NAME = "instance_name"
_SHARED_SEQ = "shared_seq"

DEFAULT_INSTANCE_NAME = "CrossStitchHelper"


def _get(session: Session, key: str) -> str | None:
    row = session.get(AppMeta, key)
    return row.value if row is not None else None


def _set(session: Session, key: str, value: str) -> None:
    row = session.get(AppMeta, key)
    if row is None:
        session.add(AppMeta(key=key, value=value))
    else:
        row.value = value


def instance_id(session: Session) -> str:
    value = _get(session, _INSTANCE_ID)
    if value is None:
        value = uuid.uuid4().hex
        _set(session, _INSTANCE_ID, value)
        session.flush()
    return value


def ensure_instance_id(session: Session) -> None:
    """Make this instance's id at startup, once and for good: the session
    cookie's name depends on it (`app/auth.py::cookie_name`), it must never
    change between two requests."""
    instance_id(session)
    session.commit()


def instance_name(session: Session) -> str:
    return _get(session, _INSTANCE_NAME) or DEFAULT_INSTANCE_NAME


def set_instance_name(session: Session, name: str) -> None:
    _set(session, _INSTANCE_NAME, name.strip() or DEFAULT_INSTANCE_NAME)


def current_seq(session: Session) -> int:
    return int(_get(session, _SHARED_SEQ) or "0")


def next_seq(session: Session) -> int:
    """The next value of the shared library's change counter. Writes stay in
    the caller's transaction: SQLite serialises them, so two changes never
    get the same value."""
    value = current_seq(session) + 1
    _set(session, _SHARED_SEQ, str(value))
    session.flush()
    return value
