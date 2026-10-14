"""The shared library and its rules (Lot 11a, issue #78).

Next to each profile's private library, the instance keeps one shared
library:

- everybody sees it and adds to it (sharing one of their patterns, or
  importing straight into it);
- only admins rename, replace or remove a shared pattern; anybody else asks
  them to (`SharedRequest`: a removal, or the replacement of its content by
  a version of their own);
- stitching a shared pattern means copying it into one's library first — a
  shared pattern has no progress of its own. The copy remembers its original
  and the revision it was copied at: when an admin replaces the original's
  content, the copy shows "update available", and is never overwritten
  without its owner asking (`update_copy`), nor ever loses its progress.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.http import api_error
from app.models import Pattern, SharedRequest, User
from app.pattern_copy import clone_pattern, replace_content, same_shape


def display_name(user: User | None) -> str | None:
    return None if user is None else f"{user.first_name} {user.last_name}"


def get_shared(session: Session, pattern_id: str) -> Pattern:
    pattern = session.get(Pattern, pattern_id)
    if pattern is None or pattern.library != "shared":
        raise api_error(404, "shared_pattern_not_found")
    return pattern


def get_personal(session: Session, pattern_id: str, user: User) -> Pattern:
    """One of `user`'s own patterns (404 otherwise, like `_get_pattern`)."""
    pattern = session.get(Pattern, pattern_id)
    if pattern is None or pattern.library != "personal" or pattern.owner_id != user.id:
        raise api_error(404, "pattern_not_found")
    return pattern


def share(session: Session, user: User, personal: Pattern) -> Pattern:
    """Put a copy of one's pattern in the shared library. The personal
    pattern — and its progress — stays where it is, now linked to the
    shared copy so its owner hears about later changes too."""
    if personal.origin_pattern_id is not None:
        # Already a copy of (or the source of) a shared pattern: sharing it
        # again would only duplicate that shared pattern.
        raise api_error(409, "pattern_already_shared")
    shared = clone_pattern(
        session,
        personal,
        name=personal.name,
        library="shared",
        owner_id=None,
        contributed_by=user.id,
    )
    personal.origin_pattern_id = shared.id
    personal.origin_revision = shared.revision
    return shared


def copy_to_library(session: Session, user: User, shared: Pattern, name: str) -> Pattern:
    return clone_pattern(
        session, shared, name=name, library="personal", owner_id=user.id, origin=shared
    )


def update_copy(session: Session, copy: Pattern, new_name: str) -> tuple[Pattern, bool]:
    """Bring a personal copy up to its original's current content.

    In place when the progress already recorded keeps its meaning (same
    cells, same backstitches and knots — `same_shape`): only the palette and
    grid change, the progress stays. Otherwise a new copy is made next to
    it: a change of shape must never cost the stitching already done
    (`CLAUDE.md`), so the old copy keeps its progress, unlinked."""
    if copy.origin_pattern_id is None:
        raise api_error(409, "pattern_has_no_origin")
    origin = session.get(Pattern, copy.origin_pattern_id)
    if origin is None:
        raise api_error(409, "pattern_has_no_origin")
    if copy.origin_revision == origin.revision:
        return copy, True
    if same_shape(copy, origin):
        replace_content(session, copy, origin)
        copy.origin_revision = origin.revision
        return copy, True
    fresh = clone_pattern(
        session, origin, name=new_name, library="personal", owner_id=copy.owner_id, origin=origin
    )
    fresh.labels_json = copy.labels_json
    copy.origin_pattern_id = None
    copy.origin_revision = None
    return fresh, False


def replace_shared(session: Session, shared: Pattern, source: Pattern) -> None:
    """New content for a shared pattern (an admin's decision): its copies
    now see "update available"."""
    replace_content(session, shared, source)
    shared.revision += 1


def _settle(request: SharedRequest, status: str, by: User | None) -> None:
    request.status = status
    request.resolved_by = by.id if by is not None else None
    request.resolved_at = datetime.now(UTC)


def _drop_proposal(session: Session, request: SharedRequest) -> None:
    if request.proposal_pattern_id is not None:
        proposal = session.get(Pattern, request.proposal_pattern_id)
        if proposal is not None:
            session.delete(proposal)
        request.proposal_pattern_id = None


def delete_shared(session: Session, shared: Pattern, admin: User) -> None:
    """Remove a shared pattern. Copies keep their content and progress, no
    longer linked. Pending requests about it are settled: a removal was
    granted, a replacement no longer has anything to replace."""
    pending = session.execute(
        select(SharedRequest).where(
            SharedRequest.shared_pattern_id == shared.id, SharedRequest.status == "pending"
        )
    ).scalars().all()
    for request in pending:
        _settle(request, "accepted" if request.kind == "removal" else "rejected", admin)
        _drop_proposal(session, request)
    session.delete(shared)


def create_request(
    session: Session,
    user: User,
    *,
    kind: str,
    shared: Pattern,
    message: str | None,
    proposal_source: Pattern | None,
) -> SharedRequest:
    duplicate = session.execute(
        select(SharedRequest.id).where(
            SharedRequest.shared_pattern_id == shared.id,
            SharedRequest.requested_by == user.id,
            SharedRequest.kind == kind,
            SharedRequest.status == "pending",
        )
    ).first()
    if duplicate is not None:
        raise api_error(409, "request_already_pending")

    proposal_id: str | None = None
    if kind == "replacement":
        if proposal_source is None:
            raise api_error(400, "request_proposal_missing")
        # Frozen at the time of asking: the admin decides on what was
        # proposed, whatever the profile does with its pattern meanwhile.
        proposal = clone_pattern(
            session,
            proposal_source,
            name=proposal_source.name,
            library="proposal",
            owner_id=None,
            contributed_by=user.id,
        )
        proposal_id = proposal.id

    request = SharedRequest(
        id=uuid.uuid4().hex,
        kind=kind,
        status="pending",
        shared_pattern_id=shared.id,
        pattern_name=shared.name,
        requested_by=user.id,
        message=(message or "").strip() or None,
        proposal_pattern_id=proposal_id,
        created_at=datetime.now(UTC),
    )
    session.add(request)
    return request


def get_request(session: Session, request_id: str) -> SharedRequest:
    request = session.get(SharedRequest, request_id)
    if request is None:
        raise api_error(404, "request_not_found")
    return request


def _require_pending(request: SharedRequest) -> None:
    if request.status != "pending":
        raise api_error(409, "request_already_settled")


def accept_request(session: Session, request: SharedRequest, admin: User) -> None:
    _require_pending(request)
    shared = (
        session.get(Pattern, request.shared_pattern_id)
        if request.shared_pattern_id is not None
        else None
    )
    if shared is None:
        raise api_error(409, "request_already_settled")
    if request.kind == "removal":
        _settle(request, "accepted", admin)
        delete_shared(session, shared, admin)
        return
    proposal = (
        session.get(Pattern, request.proposal_pattern_id)
        if request.proposal_pattern_id is not None
        else None
    )
    if proposal is None:
        raise api_error(409, "request_already_settled")
    replace_shared(session, shared, proposal)
    _settle(request, "accepted", admin)
    _drop_proposal(session, request)


def reject_request(session: Session, request: SharedRequest, admin: User) -> None:
    _require_pending(request)
    _settle(request, "rejected", admin)
    _drop_proposal(session, request)


def cancel_request(session: Session, request: SharedRequest, user: User) -> None:
    if request.requested_by != user.id:
        raise api_error(404, "request_not_found")
    _require_pending(request)
    _settle(request, "cancelled", user)
    _drop_proposal(session, request)
