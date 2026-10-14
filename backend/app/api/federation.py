"""Linking two instances (Lot 11b, issue #78).

Two routers:

- `protocol_router` (`/api/federation/v1/...`) is what a *subscribed*
  instance's server calls on this one, authenticated by the token it got at
  pairing (`Authorization: Bearer`) — never by a profile's session. It only
  ever exposes this instance's own shared patterns and the requests about
  them: personal libraries and progress never leave the instance.
- `router` (`/api/federation/...`) is this instance's admins managing the
  links (invite, join, revoke) and anybody asking for a fresh pull.

The subscribing side (pull, forwarding) is `app/federation.py`.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import federation
from app import shared as shared_library
from app.auth import AdminUser, CurrentUser
from app.db import get_session
from app.fed_payload import new_from_fed, replace_from_fed, to_fed
from app.http import api_error
from app.instance import current_seq, instance_id, instance_name, set_instance_name
from app.labels import labels_to_json
from app.models import Pattern, Peer, PeerInvitation, SharedRequest, SharedTombstone, User
from app.schemas import (
    FedActor,
    FedCancel,
    FedChanges,
    FedContribution,
    FedCreated,
    FederationOut,
    FedInfo,
    FedPairRequest,
    FedPairResponse,
    FedPattern,
    FedRename,
    FedReplace,
    FedRequest,
    FedRequestCreate,
    FedRequests,
    InstanceNameUpdate,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    JoinRequest,
    PeerOut,
    RequestStatus,
    SyncResult,
)

# --- Protocol (called by a subscribed instance) -------------------------------

protocol_router = APIRouter(prefix="/federation/v1", tags=["federation"])


def current_peer(request: Request, session: Annotated[Session, Depends(get_session)]) -> Peer:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise api_error(401, "peer_auth_required")
    peer = session.execute(
        select(Peer).where(
            Peer.inbound_token_hash == federation.token_hash(token), Peer.role == "subscriber"
        )
    ).scalar_one_or_none()
    if peer is None:
        raise api_error(401, "peer_auth_required")
    return peer


SubscribedPeer = Annotated[Peer, Depends(current_peer)]


def _trusted(peer: Peer) -> None:
    if not peer.trust_admins:
        raise api_error(403, "peer_not_trusted")


def _local_shared(session: Session, pattern_id: str) -> Pattern:
    pattern = session.get(Pattern, pattern_id)
    if pattern is None or pattern.library != "shared" or pattern.source_peer_id is not None:
        raise api_error(404, "shared_pattern_not_found")
    return pattern


def _names(session: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    users = session.execute(select(User).where(User.id.in_(ids))).scalars()
    return {user.id: shared_library.display_name(user) or "" for user in users}


def _fed(session: Session, pattern: Pattern) -> FedPattern:
    names = _names(session, {pattern.contributed_by} if pattern.contributed_by else set())
    return to_fed(pattern, shared_library.contributor_label(pattern, names))


@protocol_router.get("/info", response_model=FedInfo, summary="Protocol version and identity")
def info(session: Annotated[Session, Depends(get_session)]) -> FedInfo:
    result = FedInfo(
        protocol=federation.PROTOCOL_VERSION,
        instance_id=instance_id(session),
        name=instance_name(session),
    )
    session.commit()
    return result


@protocol_router.post("/pair", response_model=FedPairResponse, summary="Spend an invitation")
def pair(
    payload: FedPairRequest, session: Annotated[Session, Depends(get_session)]
) -> FedPairResponse:
    return federation.accept_pairing(session, payload.secret, payload.instance_id, payload.name)


@protocol_router.delete("/peer", status_code=204, summary="The subscriber leaves")
def unpair(peer: SubscribedPeer, session: Annotated[Session, Depends(get_session)]) -> Response:
    session.delete(peer)
    session.commit()
    return Response(status_code=204)


@protocol_router.get("/changes", response_model=FedChanges, summary="Changes since a cursor")
def changes(
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
    since: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FedChanges:
    """This instance's own shared patterns changed since `since` (never the
    mirrors it may itself keep of a third instance), and those removed, in
    the order they happened."""
    patterns = (
        session.execute(
            select(Pattern)
            .where(
                Pattern.library == "shared",
                Pattern.source_peer_id.is_(None),
                Pattern.shared_seq > since,
            )
            .options(selectinload(Pattern.palette_entries), selectinload(Pattern.grid))
            .order_by(Pattern.shared_seq)
            .limit(limit + 1)
        )
        .scalars()
        .all()
    )
    tombstones = (
        session.execute(
            select(SharedTombstone)
            .where(SharedTombstone.seq > since)
            .order_by(SharedTombstone.seq)
            .limit(limit + 1)
        )
        .scalars()
        .all()
    )
    events: list[tuple[int, Pattern | SharedTombstone]] = sorted(
        [(p.shared_seq or 0, p) for p in patterns] + [(t.seq, t) for t in tombstones],
        key=lambda event: event[0],
    )
    page, more = events[:limit], len(events) > limit
    cursor = page[-1][0] if more else max([since, current_seq(session)] + [e[0] for e in page])
    return FedChanges(
        cursor=cursor,
        more=more,
        upserts=[_fed(session, item) for _, item in page if isinstance(item, Pattern)],
        deletions=[item.pattern_id for _, item in page if isinstance(item, SharedTombstone)],
    )


@protocol_router.get("/patterns/{pattern_id}", response_model=FedPattern, summary="One pattern")
def get_pattern(
    pattern_id: str, peer: SubscribedPeer, session: Annotated[Session, Depends(get_session)]
) -> FedPattern:
    """A shared pattern, or a proposal a subscriber may see: its own users',
    or any pending one if its admins are trusted."""
    pattern = session.get(Pattern, pattern_id)
    if pattern is not None and pattern.source_peer_id is None:
        if pattern.library == "shared":
            return _fed(session, pattern)
        if pattern.library == "proposal":
            request = session.execute(
                select(SharedRequest).where(SharedRequest.proposal_pattern_id == pattern.id)
            ).scalar_one_or_none()
            if request is not None and (
                peer.trust_admins or request.requester_peer_id == peer.id
            ):
                return _fed(session, pattern)
    raise api_error(404, "shared_pattern_not_found")


@protocol_router.post("/shared", response_model=FedCreated, summary="Add to the shared library")
def contribute(
    payload: FedContribution,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> FedCreated:
    pattern = new_from_fed(
        session,
        payload.pattern,
        library="shared",
        contributed_by_name=f"{payload.contributor_name} · {peer.name}",
    )
    shared_library.touch(session, pattern)
    session.commit()
    return FedCreated(id=pattern.id, revision=pattern.revision)


@protocol_router.patch("/shared/{pattern_id}", status_code=204, summary="Trusted: rename")
def rename(
    pattern_id: str,
    payload: FedRename,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    _trusted(peer)
    pattern = _local_shared(session, pattern_id)
    if payload.name is not None:
        pattern.name = payload.name
    if payload.labels is not None:
        pattern.labels_json = labels_to_json(payload.labels)
    shared_library.touch(session, pattern)
    session.commit()
    return Response(status_code=204)


@protocol_router.post(
    "/shared/{pattern_id}/replace", status_code=204, summary="Trusted: replace content"
)
def replace(
    pattern_id: str,
    payload: FedReplace,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    _trusted(peer)
    pattern = _local_shared(session, pattern_id)
    replace_from_fed(session, pattern, payload.pattern)
    pattern.revision += 1
    shared_library.touch(session, pattern)
    session.commit()
    return Response(status_code=204)


@protocol_router.delete("/shared/{pattern_id}", status_code=204, summary="Trusted: remove")
def remove(
    pattern_id: str, peer: SubscribedPeer, session: Annotated[Session, Depends(get_session)]
) -> Response:
    _trusted(peer)
    shared_library.delete_shared(session, _local_shared(session, pattern_id), None)
    session.commit()
    return Response(status_code=204)


def _fed_request(request: SharedRequest, peer: Peer, names: dict[str, str]) -> FedRequest:
    return FedRequest(
        id=request.id,
        kind="removal" if request.kind == "removal" else "replacement",
        status=cast(RequestStatus, request.status),
        shared_pattern_id=request.shared_pattern_id,
        pattern_name=request.pattern_name,
        requested_by_name=shared_library.requester_label(request, names),
        requester_ref=request.requester_ref if request.requester_peer_id == peer.id else None,
        message=request.message,
        proposal_pattern_id=request.proposal_pattern_id,
        created_at=request.created_at,
        resolved_at=request.resolved_at,
    )


@protocol_router.get("/requests", response_model=FedRequests, summary="Requests it may see")
def requests(
    peer: SubscribedPeer, session: Annotated[Session, Depends(get_session)]
) -> FedRequests:
    """The subscriber's own users' requests, whatever their status; and,
    when its admins are trusted, every pending one (they decide on them)."""
    visible = SharedRequest.requester_peer_id == peer.id
    if peer.trust_admins:
        visible = or_(visible, SharedRequest.status == "pending")
    rows = (
        session.execute(
            select(SharedRequest)
            .where(visible, SharedRequest.source_peer_id.is_(None))
            .order_by(SharedRequest.created_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )
    names = _names(session, {r.requested_by for r in rows if r.requested_by is not None})
    return FedRequests(requests=[_fed_request(r, peer, names) for r in rows])


@protocol_router.post("/requests", response_model=FedRequest, status_code=201)
def create_request(
    payload: FedRequestCreate,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> FedRequest:
    """A profile of the subscriber asking to remove or replace one of this
    instance's shared patterns — the same rules as a local request
    (`app/shared.py::create_request`), credited to that profile."""
    shared = _local_shared(session, payload.shared_pattern_id)
    duplicate = session.execute(
        select(SharedRequest.id).where(
            SharedRequest.shared_pattern_id == shared.id,
            SharedRequest.requester_peer_id == peer.id,
            SharedRequest.requester_ref == payload.requester_ref,
            SharedRequest.kind == payload.kind,
            SharedRequest.status == "pending",
        )
    ).first()
    if duplicate is not None:
        raise api_error(409, "request_already_pending")
    proposal_id: str | None = None
    who = f"{payload.requester_name} · {peer.name}"
    if payload.kind == "replacement":
        if payload.proposal is None:
            raise api_error(400, "request_proposal_missing")
        proposal_id = new_from_fed(
            session, payload.proposal, library="proposal", contributed_by_name=who
        ).id
    request = SharedRequest(
        id=uuid.uuid4().hex,
        kind=payload.kind,
        status="pending",
        shared_pattern_id=shared.id,
        pattern_name=shared.name,
        requested_by=None,
        requested_by_name=who,
        requester_peer_id=peer.id,
        requester_ref=payload.requester_ref,
        message=(payload.message or "").strip() or None,
        proposal_pattern_id=proposal_id,
        created_at=datetime.now(UTC),
    )
    session.add(request)
    session.commit()
    return _fed_request(request, peer, {})


def _local_request(session: Session, request_id: str) -> SharedRequest:
    request = session.get(SharedRequest, request_id)
    if request is None or request.source_peer_id is not None:
        raise api_error(404, "request_not_found")
    return request


@protocol_router.post("/requests/{request_id}/cancel", status_code=204)
def cancel_request(
    request_id: str,
    payload: FedCancel,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Its author (a profile of this subscriber) withdraws a request."""
    shared_request = _local_request(session, request_id)
    if (
        shared_request.requester_peer_id != peer.id
        or shared_request.requester_ref != payload.requester_ref
    ):
        raise api_error(404, "request_not_found")
    if shared_request.status != "pending":
        raise api_error(409, "request_already_settled")
    shared_request.status = "cancelled"
    shared_request.resolved_at = datetime.now(UTC)
    if shared_request.proposal_pattern_id is not None:
        proposal = session.get(Pattern, shared_request.proposal_pattern_id)
        if proposal is not None:
            session.delete(proposal)
        shared_request.proposal_pattern_id = None
    session.commit()
    return Response(status_code=204)


@protocol_router.post("/requests/{request_id}/accept", status_code=204)
def accept_request(
    request_id: str,
    payload: FedActor,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    _trusted(peer)
    shared_library.accept_request(session, _local_request(session, request_id), None)
    session.commit()
    return Response(status_code=204)


@protocol_router.post("/requests/{request_id}/reject", status_code=204)
def reject_request(
    request_id: str,
    payload: FedActor,
    peer: SubscribedPeer,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    _trusted(peer)
    shared_library.reject_request(session, _local_request(session, request_id), None)
    session.commit()
    return Response(status_code=204)


# --- Admin side (this instance's profiles) ------------------------------------

router = APIRouter(prefix="/federation", tags=["federation"])


def _peer_out(peer: Peer) -> PeerOut:
    return PeerOut(
        id=peer.id,
        name=peer.name,
        role="host" if peer.role == "host" else "subscriber",
        base_url=peer.base_url,
        trust_admins=peer.trust_admins,
        last_sync_at=peer.last_sync_at,
        last_error=peer.last_error,
        created_at=peer.created_at,
    )


@router.get("", response_model=FederationOut, summary="Admins: this instance and its links")
def overview(
    admin: AdminUser, session: Annotated[Session, Depends(get_session)]
) -> FederationOut:
    now = datetime.now(UTC)
    invitations = (
        session.execute(
            select(PeerInvitation)
            .where(PeerInvitation.used_at.is_(None), PeerInvitation.expires_at > now)
            .order_by(PeerInvitation.created_at.desc())
        )
        .scalars()
        .all()
    )
    result = FederationOut(
        instance_id=instance_id(session),
        instance_name=instance_name(session),
        peers=[
            _peer_out(peer)
            for peer in session.execute(select(Peer).order_by(Peer.created_at)).scalars()
        ],
        invitations=[
            InvitationOut(
                id=i.id,
                trust_admins=i.trust_admins,
                created_at=i.created_at,
                expires_at=i.expires_at,
            )
            for i in invitations
        ],
    )
    session.commit()
    return result


@router.put("/instance", status_code=204, summary="Admins: this instance's name")
def rename_instance(
    payload: InstanceNameUpdate,
    admin: AdminUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    set_instance_name(session, payload.name)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/invitations",
    response_model=InvitationCreated,
    status_code=201,
    summary="Admins: invite another instance to mirror this shared library",
)
def invite(
    payload: InvitationCreate,
    admin: AdminUser,
    session: Annotated[Session, Depends(get_session)],
) -> InvitationCreated:
    code, invitation = federation.create_invitation(
        session, admin, payload.public_url, payload.trust_admins
    )
    session.commit()
    return InvitationCreated(code=code, expires_at=invitation.expires_at)


@router.delete("/invitations/{invitation_id}", status_code=204, summary="Admins: withdraw")
def withdraw_invitation(
    invitation_id: str, admin: AdminUser, session: Annotated[Session, Depends(get_session)]
) -> Response:
    invitation = session.get(PeerInvitation, invitation_id)
    if invitation is not None:
        session.delete(invitation)
        session.commit()
    return Response(status_code=204)


@router.post("/join", response_model=PeerOut, status_code=201, summary="Admins: join a host")
def join(
    payload: JoinRequest, admin: AdminUser, session: Annotated[Session, Depends(get_session)]
) -> PeerOut:
    peer = federation.join(session, payload.code)
    # Joined all the same if this first pull fails: the error is shown on the
    # link, and the next sync tries again.
    with contextlib.suppress(federation.PeerError):
        federation.sync_peer(session, peer)
    session.refresh(peer)
    return _peer_out(peer)


@router.delete("/peers/{peer_id}", status_code=204, summary="Admins: undo a link")
def leave(
    peer_id: str, admin: AdminUser, session: Annotated[Session, Depends(get_session)]
) -> Response:
    peer = session.get(Peer, peer_id)
    if peer is None:
        raise api_error(404, "peer_not_found")
    federation.leave(session, peer)
    return Response(status_code=204)


@router.post("/sync", response_model=SyncResult, summary="Pull the paired hosts now")
def sync(user: CurrentUser, session: Annotated[Session, Depends(get_session)]) -> SyncResult:
    """Any profile opening the shared tab asks for this; hosts pulled a few
    seconds ago are skipped (switching tabs back and forth)."""
    synced, errors = federation.sync_hosts(session, min_interval=10.0)
    return SyncResult(synced=synced, errors=errors)
