"""Shared library routes (Lot 11a, issue #78) — the rules themselves live in
`app/shared.py`."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import federation
from app import shared as shared_library
from app.api.patterns import grid_out, pattern_detail
from app.auth import AdminUser, CurrentUser
from app.codec import decode_uint16_layer
from app.db import get_session
from app.http import api_error
from app.instance import instance_name
from app.labels import labels_from_json, labels_to_json
from app.models import Pattern, Peer, SharedRequest, User
from app.schemas import (
    GridOut,
    PatternDetail,
    PatternDuplicateOut,
    PatternUpdate,
    RequestStatus,
    SharedCopyRequest,
    SharedLibraryOut,
    SharedPatternOut,
    SharedPatternRef,
    SharedReplaceRequest,
    SharedRequestCreate,
    SharedRequestOut,
    SharedTarget,
)

router = APIRouter(prefix="/shared", tags=["shared"])


def _names(session: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    users = session.execute(select(User).where(User.id.in_(ids))).scalars()
    return {user.id: shared_library.display_name(user) or "" for user in users}


def _request_out(
    request: SharedRequest,
    names: dict[str, str],
    me: User,
    trusted_peers: set[str] | None = None,
) -> SharedRequestOut:
    can_decide = me.role == "admin" and (
        request.source_peer_id is None or request.source_peer_id in (trusted_peers or set())
    )
    return SharedRequestOut(
        id=request.id,
        kind="removal" if request.kind == "removal" else "replacement",
        status=cast(RequestStatus, request.status),
        shared_pattern_id=request.shared_pattern_id,
        pattern_name=request.pattern_name,
        requested_by_name=shared_library.requester_label(request, names),
        mine=request.requested_by == me.id,
        message=request.message,
        proposal_pattern_id=request.proposal_pattern_id,
        created_at=request.created_at,
        resolved_at=request.resolved_at,
        can_decide=can_decide,
    )


@router.get("", response_model=SharedLibraryOut, summary="The shared library and its requests")
def shared_library_view(
    session: Annotated[Session, Depends(get_session)], user: CurrentUser
) -> SharedLibraryOut:
    patterns = (
        session.execute(
            select(Pattern)
            .where(Pattern.library == "shared")
            .options(selectinload(Pattern.grid), selectinload(Pattern.palette_entries))
            .order_by(Pattern.created_at.desc())
        )
        .scalars()
        .all()
    )
    copies: dict[str, list[str]] = {}
    for copy_id, origin_id in session.execute(
        select(Pattern.id, Pattern.origin_pattern_id).where(
            Pattern.owner_id == user.id,
            Pattern.library == "personal",
            Pattern.origin_pattern_id.is_not(None),
        )
    ).tuples():
        copies.setdefault(origin_id or "", []).append(copy_id)

    # An admin sees every pending request (they decide on them) and their
    # own; anybody else, only their own, settled ones included so they learn
    # the outcome.
    visible = SharedRequest.requested_by == user.id
    if user.role == "admin":
        visible = or_(visible, SharedRequest.status == "pending")
    requests = (
        session.execute(
            select(SharedRequest).where(visible).order_by(SharedRequest.created_at.desc())
        )
        .scalars()
        .all()
    )

    names = _names(
        session,
        {p.contributed_by for p in patterns if p.contributed_by is not None}
        | {r.requested_by for r in requests if r.requested_by is not None},
    )
    # Lot 11b: patterns whose home is a paired instance (mirrors), and the
    # shared libraries one can add to — this one's, and each host's.
    peers = {peer.id: peer for peer in session.execute(select(Peer)).scalars()}
    is_admin = user.role == "admin"

    def can_moderate(pattern: Pattern) -> bool:
        if not is_admin:
            return False
        if pattern.source_peer_id is None:
            return True
        peer = peers.get(pattern.source_peer_id)
        return peer is not None and peer.trust_admins

    targets = [SharedTarget(peer_id=None, name=instance_name(session))] + [
        SharedTarget(peer_id=peer.id, name=peer.name)
        for peer in peers.values()
        if peer.role == "host"
    ]
    session.commit()  # `instance_name` may have created this instance's id
    return SharedLibraryOut(
        patterns=[
            SharedPatternOut(
                id=pattern.id,
                name=pattern.name,
                width=pattern.width,
                height=pattern.height,
                palette_count=len(pattern.palette_entries),
                cell_count=sum(1 for v in decode_uint16_layer(pattern.grid.layer_full) if v)
                if pattern.grid is not None
                else 0,
                labels=labels_from_json(pattern.labels_json),
                revision=pattern.revision,
                contributed_by_name=shared_library.contributor_label(pattern, names),
                created_at=pattern.created_at,
                updated_at=pattern.updated_at,
                my_copy_ids=copies.get(pattern.id, []),
                source_name=peers[pattern.source_peer_id].name
                if pattern.source_peer_id in peers
                else None,
                can_moderate=can_moderate(pattern),
            )
            for pattern in patterns
        ],
        requests=[
            _request_out(
                request,
                names,
                user,
                {peer.id for peer in peers.values() if peer.trust_admins},
            )
            for request in requests
        ],
        targets=targets,
    )


def _readable(session: Session, pattern_id: str, user: User) -> Pattern:
    """A shared pattern (anybody), or a proposal (admins, and whoever
    proposed it) — what the shared tab may display."""
    pattern = session.get(Pattern, pattern_id)
    if pattern is not None and pattern.library == "shared":
        return pattern
    if (
        pattern is not None
        and pattern.library == "proposal"
        and (user.role == "admin" or pattern.contributed_by == user.id)
    ):
        return pattern
    raise api_error(404, "shared_pattern_not_found")


@router.get("/patterns/{pattern_id}", response_model=PatternDetail, summary="Metadata and palette")
def get_shared_pattern(
    pattern_id: str, session: Annotated[Session, Depends(get_session)], user: CurrentUser
) -> PatternDetail:
    return pattern_detail(_readable(session, pattern_id, user))


@router.get("/patterns/{pattern_id}/grid", response_model=GridOut, summary="Grid layers")
def get_shared_grid(
    pattern_id: str, session: Annotated[Session, Depends(get_session)], user: CurrentUser
) -> GridOut:
    return grid_out(_readable(session, pattern_id, user))


@router.post(
    "/patterns/{pattern_id}/copy",
    response_model=PatternDuplicateOut,
    status_code=201,
    summary="Copy a shared pattern into my library",
)
def copy_shared_pattern(
    pattern_id: str,
    payload: SharedCopyRequest,
    session: Annotated[Session, Depends(get_session)],
    user: CurrentUser,
) -> PatternDuplicateOut:
    copy = shared_library.copy_to_library(
        session, user, shared_library.get_shared(session, pattern_id), payload.name
    )
    session.commit()
    return PatternDuplicateOut(id=copy.id)


@router.patch(
    "/patterns/{pattern_id}",
    response_model=PatternDetail,
    summary="Admins: rename a shared pattern, edit its labels",
)
def update_shared_pattern(
    pattern_id: str,
    payload: PatternUpdate,
    session: Annotated[Session, Depends(get_session)],
    admin: AdminUser,
) -> PatternDetail:
    """Name and labels only — like a personal pattern's "Edit" (issue #57),
    and without bumping the revision: copies have names and labels of their
    own, so this is not a change they need to hear about."""
    pattern = shared_library.get_shared(session, pattern_id)
    if pattern.source_peer_id is not None:
        federation.rename_on_host(session, admin, pattern, payload.name, payload.labels)
        return pattern_detail(shared_library.get_shared(session, pattern_id))
    if payload.name is not None:
        pattern.name = payload.name
    if payload.labels is not None:
        pattern.labels_json = labels_to_json(payload.labels)
    shared_library.touch(session, pattern)
    session.commit()
    return pattern_detail(pattern)


@router.post(
    "/patterns/{pattern_id}/replace",
    response_model=SharedPatternRef,
    summary="Admins: replace a shared pattern's content with one of mine",
)
def replace_shared_pattern(
    pattern_id: str,
    payload: SharedReplaceRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: AdminUser,
) -> SharedPatternRef:
    shared = shared_library.get_shared(session, pattern_id)
    source = shared_library.get_personal(session, payload.source_pattern_id, admin)
    if shared.source_peer_id is not None:
        federation.replace_on_host(session, admin, shared, source)
        return SharedPatternRef(id=shared.id)
    shared_library.replace_shared(session, shared, source)
    session.commit()
    return SharedPatternRef(id=shared.id)


@router.delete(
    "/patterns/{pattern_id}", status_code=204, summary="Admins: remove a shared pattern"
)
def delete_shared_pattern(
    pattern_id: str, session: Annotated[Session, Depends(get_session)], admin: AdminUser
) -> Response:
    shared = shared_library.get_shared(session, pattern_id)
    if shared.source_peer_id is not None:
        federation.delete_on_host(session, shared)
        return Response(status_code=204)
    shared_library.delete_shared(session, shared, admin)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/requests",
    response_model=SharedRequestOut,
    status_code=201,
    summary="Ask the admins to remove or replace a shared pattern",
)
def create_shared_request(
    payload: SharedRequestCreate,
    session: Annotated[Session, Depends(get_session)],
    user: CurrentUser,
) -> SharedRequestOut:
    shared = shared_library.get_shared(session, payload.shared_pattern_id)
    source = (
        shared_library.get_personal(session, payload.proposal_pattern_id, user)
        if payload.proposal_pattern_id is not None
        else None
    )
    if shared.source_peer_id is not None:
        request = federation.request_on_host(
            session,
            user,
            kind=payload.kind,
            mirror=shared,
            message=payload.message,
            proposal_source=source,
        )
        return _request_out(request, _names(session, {user.id}), user)
    request = shared_library.create_request(
        session,
        user,
        kind=payload.kind,
        shared=shared,
        message=payload.message,
        proposal_source=source,
    )
    session.commit()
    return _request_out(request, _names(session, {user.id}), user)


_OUTCOME: dict[str, RequestStatus] = {
    "accept": "accepted",
    "reject": "rejected",
    "cancel": "cancelled",
}


def _settled_on_host(
    session: Session, request: SharedRequest, user: User, action: str
) -> SharedRequestOut:
    """Forward a decision about a mirrored request to its home instance. The
    refreshed mirror may no longer list it (someone else's request, once
    settled, is none of this instance's business): answer from what was
    known before, with its new status."""
    before = _request_out(
        request, _names(session, {request.requested_by} if request.requested_by else set()), user
    )
    federation.settle_on_host(session, user, request, action)
    return before.model_copy(update={"status": _OUTCOME[action]})


def _settled(session: Session, request: SharedRequest, user: User) -> SharedRequestOut:
    session.commit()
    names = _names(session, {request.requested_by} if request.requested_by else set())
    return _request_out(request, names, user)


@router.post(
    "/requests/{request_id}/accept",
    response_model=SharedRequestOut,
    summary="Admins: grant a request",
)
def accept_shared_request(
    request_id: str, session: Annotated[Session, Depends(get_session)], admin: AdminUser
) -> SharedRequestOut:
    request = shared_library.get_request(session, request_id)
    if request.source_peer_id is not None:
        return _settled_on_host(session, request, admin, "accept")
    shared_library.accept_request(session, request, admin)
    return _settled(session, request, admin)


@router.post(
    "/requests/{request_id}/reject",
    response_model=SharedRequestOut,
    summary="Admins: turn a request down",
)
def reject_shared_request(
    request_id: str, session: Annotated[Session, Depends(get_session)], admin: AdminUser
) -> SharedRequestOut:
    request = shared_library.get_request(session, request_id)
    if request.source_peer_id is not None:
        return _settled_on_host(session, request, admin, "reject")
    shared_library.reject_request(session, request, admin)
    return _settled(session, request, admin)


@router.post(
    "/requests/{request_id}/cancel",
    response_model=SharedRequestOut,
    summary="Withdraw one of my requests",
)
def cancel_shared_request(
    request_id: str, session: Annotated[Session, Depends(get_session)], user: CurrentUser
) -> SharedRequestOut:
    request = shared_library.get_request(session, request_id)
    if request.source_peer_id is not None:
        return _settled_on_host(session, request, user, "cancel")
    shared_library.cancel_request(session, request, user)
    return _settled(session, request, user)
