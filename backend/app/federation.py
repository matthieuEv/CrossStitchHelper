"""Sharing between two paired instances — the subscribing side (Lot 11b,
issue #78).

Model: every shared pattern has one home instance, the only one that
changes it. An instance that subscribes to another one's shared library
keeps a read-only **mirror** of it, refreshed by **pull** — it calls its
host, never the other way round, so only the host needs to be reachable
(reverse proxy, Tailscale, tunnel: a documentation matter, `README.md`).
Its users' writes (adding a pattern, asking for a removal, proposing a
version, and the admin actions when the host trusts this instance's admins)
are **forwarded** to the host, then the mirror is refreshed. No change is
ever made to a mirror locally, so the two sides can never disagree on whose
version wins.

What is delegated, and what is not (`docs/specification.md` §13): no
replication or federation library fits a single-container SQLite app (the
2026-10-14 research: cr-sqlite has no Python package, Marmot/rqlite need a
separate service, ActivityPub is overkill for two trusted peers). Transport
security is delegated to HTTPS or the tunnel already used to reach the
instance from outside, HTTP to `httpx`; the protocol itself is a small
changes feed in the spirit of CouchDB's replication (cursor, revision,
tombstones).

The host side of the protocol is `app/api/federation.py`.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import shared as shared_library
from app.fed_payload import new_from_fed, replace_from_fed, to_fed
from app.http import api_error
from app.instance import instance_id, instance_name
from app.labels import labels_to_json
from app.models import Pattern, Peer, PeerInvitation, SharedRequest, User
from app.schemas import (
    FedChanges,
    FedCreated,
    FedPairResponse,
    FedPattern,
    FedRequests,
)

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
CODE_PREFIX = "csh1."
INVITATION_LIFETIME = timedelta(hours=24)
# A request made on behalf of a user waits for the other instance; a home
# server on a slow uplink still answers well within this.
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_PAGE = 50


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Invitations (host side, made by an admin here) -------------------------


def create_invitation(
    session: Session, admin: User, public_url: str, trust_admins: bool
) -> tuple[str, PeerInvitation]:
    """A one-time code for the admin of another instance: this instance's
    address as that instance's server will reach it, and a secret."""
    secret = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    invitation = PeerInvitation(
        id=uuid.uuid4().hex,
        secret_hash=token_hash(secret),
        trust_admins=trust_admins,
        created_by=admin.id,
        created_at=now,
        expires_at=now + INVITATION_LIFETIME,
    )
    session.add(invitation)
    body = json.dumps({"u": public_url.rstrip("/"), "s": secret}, separators=(",", ":"))
    code = CODE_PREFIX + base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return code, invitation


def decode_invitation(code: str) -> tuple[str, str]:
    code = code.strip()
    if not code.startswith(CODE_PREFIX):
        raise api_error(400, "invitation_invalid")
    raw = code[len(CODE_PREFIX) :]
    try:
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        url, secret = str(body["u"]), str(body["s"])
    except (binascii.Error, ValueError, KeyError, TypeError) as error:
        raise api_error(400, "invitation_invalid") from error
    if not url.startswith(("http://", "https://")):
        raise api_error(400, "invitation_invalid")
    return url.rstrip("/"), secret


def accept_pairing(
    session: Session, secret: str, peer_instance_id: str, peer_name: str
) -> FedPairResponse:
    """Host side of `join`: spend the invitation, remember the subscriber."""
    invitation = session.execute(
        select(PeerInvitation).where(PeerInvitation.secret_hash == token_hash(secret))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if invitation is None or invitation.used_at is not None:
        raise api_error(403, "invitation_invalid")
    expires_at = invitation.expires_at
    if (expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)) <= now:
        raise api_error(403, "invitation_expired")
    if peer_instance_id == instance_id(session):
        raise api_error(400, "invitation_same_instance")
    invitation.used_at = now

    # Pairing again (after a revocation, a lost token) replaces the old link.
    for previous in session.execute(
        select(Peer).where(Peer.instance_id == peer_instance_id, Peer.role == "subscriber")
    ).scalars():
        session.delete(previous)
    token = secrets.token_urlsafe(32)
    session.add(
        Peer(
            id=uuid.uuid4().hex,
            instance_id=peer_instance_id,
            name=peer_name,
            role="subscriber",
            inbound_token_hash=token_hash(token),
            trust_admins=invitation.trust_admins,
            created_at=now,
        )
    )
    session.commit()
    return FedPairResponse(
        token=token,
        instance_id=instance_id(session),
        name=instance_name(session),
        trust_admins=invitation.trust_admins,
    )


# --- Talking to a host --------------------------------------------------------


class PeerError(Exception):
    """The other instance could not be reached, or refused. `code` is an
    API error code (`frontend/src/i18n`), kept in `Peer.last_error`."""

    def __init__(self, code: str, status: int = 502) -> None:
        super().__init__(code)
        self.code = code
        self.status = status

    def as_http(self) -> Exception:
        return api_error(self.status, self.code)


class PeerClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token is not None else {}

    @classmethod
    def for_host(cls, peer: Peer) -> PeerClient:
        if peer.role != "host" or peer.base_url is None or peer.outbound_token is None:
            raise PeerError("peer_not_found", 404)
        return cls(peer.base_url, peer.outbound_token)

    def call(self, method: str, path: str, json_body: Any = None) -> Any:
        url = f"{self.base_url}/api/federation/v1{path}"
        try:
            with httpx.Client(timeout=_TIMEOUT, headers=self.headers) as client:
                response = client.request(method, url, json=json_body)
        except httpx.HTTPError as error:
            logger.warning("Paired instance %s unreachable: %s", self.base_url, error)
            raise PeerError("peer_unreachable") from error
        if response.status_code == 401:
            raise PeerError("peer_auth_failed")
        if response.status_code >= 400:
            code = "peer_refused"
            try:
                detail = response.json().get("detail")
                if isinstance(detail, dict) and isinstance(detail.get("code"), str):
                    code = detail["code"]
            except ValueError:
                pass
            raise PeerError(code, 409 if response.status_code < 500 else 502)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


# --- Joining a host (subscriber side, made by an admin here) -----------------


def join(session: Session, code: str) -> Peer:
    url, secret = decode_invitation(code)
    client = PeerClient(url)
    try:
        info = client.call("GET", "/info")
        if not isinstance(info, dict) or info.get("protocol") != PROTOCOL_VERSION:
            raise PeerError("peer_incompatible", 409)
        paired = FedPairResponse.model_validate(
            client.call(
                "POST",
                "/pair",
                {
                    "secret": secret,
                    "instance_id": instance_id(session),
                    "name": instance_name(session),
                },
            )
        )
    except PeerError as error:
        raise error.as_http() from error

    for previous in session.execute(
        select(Peer).where(Peer.instance_id == paired.instance_id, Peer.role == "host")
    ).scalars():
        session.delete(previous)
    session.flush()
    peer = Peer(
        id=uuid.uuid4().hex,
        instance_id=paired.instance_id,
        name=paired.name,
        role="host",
        base_url=url,
        outbound_token=paired.token,
        trust_admins=paired.trust_admins,
        cursor=0,
        created_at=datetime.now(UTC),
    )
    session.add(peer)
    session.commit()
    return peer


def leave(session: Session, peer: Peer) -> None:
    """Undo a pairing from either side. Leaving a host tells it (best
    effort: an unreachable host just keeps a token nobody uses any more);
    its mirrors go with the pairing, copies stay, unlinked."""
    if peer.role == "host":
        try:
            PeerClient.for_host(peer).call("DELETE", "/peer")
        except PeerError:
            logger.info("Could not tell %s about leaving; removing the link anyway", peer.name)
    session.delete(peer)
    session.commit()


# --- Pull (subscriber side) ---------------------------------------------------


def _mirror(session: Session, peer: Peer, remote_id: str) -> Pattern | None:
    return session.execute(
        select(Pattern).where(Pattern.source_peer_id == peer.id, Pattern.remote_id == remote_id)
    ).scalar_one_or_none()


def _apply_upsert(session: Session, peer: Peer, fed: FedPattern) -> None:
    mirror = _mirror(session, peer, fed.id)
    if mirror is None:
        new_from_fed(
            session,
            fed,
            library="shared",
            revision=fed.revision,
            contributed_by_name=fed.contributed_by_name,
            source_peer_id=peer.id,
            remote_id=fed.id,
        )
        return
    if mirror.revision != fed.revision:
        replace_from_fed(session, mirror, fed)
        mirror.revision = fed.revision
    mirror.name = fed.name
    mirror.labels_json = labels_to_json(fed.labels)
    mirror.contributed_by_name = fed.contributed_by_name


def _apply_deletion(session: Session, peer: Peer, remote_id: str) -> None:
    mirror = _mirror(session, peer, remote_id)
    if mirror is not None:
        # Copies keep their content and progress, no longer linked
        # (`ON DELETE SET NULL`), exactly as for a local removal.
        session.delete(mirror)


def _sync_requests(session: Session, peer: Peer, client: PeerClient) -> None:
    fed = FedRequests.model_validate(client.call("GET", "/requests"))
    local_users = {
        user_id for (user_id,) in session.execute(select(User.id))
    }
    seen: set[str] = set()
    wanted_proposals: set[str] = set()
    for remote in fed.requests:
        seen.add(remote.id)
        mirror = (
            _mirror(session, peer, remote.shared_pattern_id)
            if remote.shared_pattern_id is not None
            else None
        )
        mine = remote.requester_ref if remote.requester_ref in local_users else None
        proposal_id: str | None = None
        if remote.status == "pending" and remote.proposal_pattern_id is not None:
            wanted_proposals.add(remote.proposal_pattern_id)
            proposal = session.execute(
                select(Pattern).where(
                    Pattern.source_peer_id == peer.id,
                    Pattern.remote_id == remote.proposal_pattern_id,
                    Pattern.library == "proposal",
                )
            ).scalar_one_or_none()
            if proposal is None:
                fetched = FedPattern.model_validate(
                    client.call("GET", f"/patterns/{remote.proposal_pattern_id}")
                )
                proposal = new_from_fed(
                    session,
                    fetched,
                    library="proposal",
                    contributed_by=mine,
                    contributed_by_name=fetched.contributed_by_name,
                    source_peer_id=peer.id,
                    remote_id=remote.proposal_pattern_id,
                )
            proposal_id = proposal.id

        # Only now that every field is known: fetching a proposal above
        # flushes the session, which must never see a half-filled row.
        request = session.execute(
            select(SharedRequest).where(
                SharedRequest.source_peer_id == peer.id, SharedRequest.remote_id == remote.id
            )
        ).scalar_one_or_none()
        if request is None:
            request = SharedRequest(
                id=uuid.uuid4().hex,
                source_peer_id=peer.id,
                remote_id=remote.id,
                created_at=remote.created_at,
            )
            session.add(request)
        request.kind = remote.kind
        request.status = remote.status
        request.shared_pattern_id = mirror.id if mirror is not None else None
        request.pattern_name = remote.pattern_name
        request.requested_by = mine
        request.requested_by_name = remote.requested_by_name
        request.message = remote.message
        request.proposal_pattern_id = proposal_id
        request.resolved_at = remote.resolved_at

    for stale in session.execute(
        select(SharedRequest).where(SharedRequest.source_peer_id == peer.id)
    ).scalars():
        if stale.remote_id not in seen:
            session.delete(stale)
    for proposal in session.execute(
        select(Pattern).where(Pattern.source_peer_id == peer.id, Pattern.library == "proposal")
    ).scalars():
        if proposal.remote_id not in wanted_proposals:
            session.delete(proposal)


def sync_peer(session: Session, peer: Peer) -> None:
    """Bring this instance's mirror of `peer`'s shared library, and of the
    requests it may see, up to date. Raises `PeerError` (recorded on the
    peer) if the host cannot be reached or refuses."""
    client = PeerClient.for_host(peer)
    try:
        while True:
            changes = FedChanges.model_validate(
                client.call("GET", f"/changes?since={peer.cursor}&limit={_PAGE}")
            )
            for fed in changes.upserts:
                _apply_upsert(session, peer, fed)
            for remote_id in changes.deletions:
                _apply_deletion(session, peer, remote_id)
            peer.cursor = changes.cursor
            session.flush()
            if not changes.more:
                break
        _sync_requests(session, peer, client)
    except PeerError as error:
        session.rollback()
        peer = session.get(Peer, peer.id) or peer
        peer.last_error = error.code
        session.commit()
        raise
    peer.last_sync_at = datetime.now(UTC)
    peer.last_error = None
    session.commit()


def hosts(session: Session) -> list[Peer]:
    return list(session.execute(select(Peer).where(Peer.role == "host")).scalars())


_last_sync_by_peer: dict[str, float] = {}


def sync_hosts(session: Session, *, min_interval: float = 0.0) -> tuple[int, list[str]]:
    """Sync every host, skipping those synced less than `min_interval`
    seconds ago (opening the shared tab asks for a sync; reopening it a few
    seconds later must not hit the host again)."""
    synced, errors = 0, []
    now = time.monotonic()
    for peer in hosts(session):
        last = _last_sync_by_peer.get(peer.id)
        if last is not None and now - last < min_interval:
            continue
        _last_sync_by_peer[peer.id] = now
        try:
            sync_peer(session, peer)
            synced += 1
        except PeerError as error:
            errors.append(error.code)
    return synced, errors


async def run_federation_loop(
    session_factory: sessionmaker[Session],
    interval: float,
    *,
    sync: Callable[[Session], object] = sync_hosts,
) -> None:
    """Pull every host now and then, in the application's own process — no
    extra service (`CLAUDE.md`), same principle as `app/auto_backup.py`.
    Copies are told about a replaced original within `interval`, or at once
    when someone opens the shared tab."""
    while True:
        try:
            await asyncio.to_thread(_sync_once, session_factory, sync)
        except Exception:  # never let one bad round stop the loop
            logger.exception("Shared library sync failed")
        await asyncio.sleep(interval)


def _sync_once(session_factory: sessionmaker[Session], sync: Callable[[Session], object]) -> None:
    with session_factory() as session:
        sync(session)


# --- Forwarding writes to a host (subscriber side) ----------------------------


def _forward(peer: Peer, method: str, path: str, body: Any = None) -> Any:
    try:
        return PeerClient.for_host(peer).call(method, path, body)
    except PeerError as error:
        raise error.as_http() from error


def _refresh(session: Session, peer: Peer) -> None:
    try:
        sync_peer(session, peer)
    except PeerError as error:
        raise error.as_http() from error


def peer_of(session: Session, peer_id: str) -> Peer:
    peer = session.get(Peer, peer_id)
    if peer is None or peer.role != "host":
        raise api_error(404, "peer_not_found")
    return peer


def _who(user: User) -> str:
    return shared_library.display_name(user) or user.first_name


def share_to_host(session: Session, user: User, personal: Pattern, peer: Peer) -> Pattern:
    """Add one's pattern to the host's shared library, then link it to its
    mirror here, like a local share (`app/shared.py::share`)."""
    if personal.origin_pattern_id is not None:
        raise api_error(409, "pattern_already_shared")
    created = FedCreated.model_validate(
        _forward(
            peer,
            "POST",
            "/shared",
            {
                "pattern": to_fed(personal, None).model_dump(mode="json"),
                "contributor_name": _who(user),
            },
        )
    )
    _refresh(session, peer)
    mirror = _mirror(session, peer, created.id)
    if mirror is None:  # pragma: no cover - the host just listed it
        raise api_error(502, "peer_refused")
    personal = session.get(Pattern, personal.id) or personal
    personal.origin_pattern_id = mirror.id
    personal.origin_revision = mirror.revision
    session.commit()
    return mirror


def rename_on_host(
    session: Session, admin: User, mirror: Pattern, name: str | None, labels: list[str] | None
) -> None:
    peer = _trusting(session, mirror)
    body: dict[str, Any] = {"actor_name": _who(admin)}
    if name is not None:
        body["name"] = name
    if labels is not None:
        body["labels"] = labels
    _forward(peer, "PATCH", f"/shared/{mirror.remote_id}", body)
    _refresh(session, peer)


def replace_on_host(session: Session, admin: User, mirror: Pattern, source: Pattern) -> None:
    peer = _trusting(session, mirror)
    _forward(
        peer,
        "POST",
        f"/shared/{mirror.remote_id}/replace",
        {"actor_name": _who(admin), "pattern": to_fed(source, None).model_dump(mode="json")},
    )
    _refresh(session, peer)


def delete_on_host(session: Session, mirror: Pattern) -> None:
    peer = _trusting(session, mirror)
    _forward(peer, "DELETE", f"/shared/{mirror.remote_id}")
    _refresh(session, peer)


def _trusting(session: Session, mirror: Pattern) -> Peer:
    """A mirror's host, provided it lets this instance's admins moderate."""
    peer = peer_of(session, mirror.source_peer_id or "")
    if not peer.trust_admins:
        raise api_error(403, "peer_not_trusted")
    return peer


def request_on_host(
    session: Session,
    user: User,
    *,
    kind: str,
    mirror: Pattern,
    message: str | None,
    proposal_source: Pattern | None,
) -> SharedRequest:
    peer = peer_of(session, mirror.source_peer_id or "")
    if kind == "replacement" and proposal_source is None:
        raise api_error(400, "request_proposal_missing")
    created = _forward(
        peer,
        "POST",
        "/requests",
        {
            "kind": kind,
            "shared_pattern_id": mirror.remote_id,
            "message": message,
            "requester_name": _who(user),
            "requester_ref": user.id,
            "proposal": to_fed(proposal_source, None).model_dump(mode="json")
            if proposal_source is not None
            else None,
        },
    )
    _refresh(session, peer)
    request = session.execute(
        select(SharedRequest).where(
            SharedRequest.source_peer_id == peer.id, SharedRequest.remote_id == created["id"]
        )
    ).scalar_one()
    return request


def settle_on_host(session: Session, user: User, request: SharedRequest, action: str) -> None:
    peer = peer_of(session, request.source_peer_id or "")
    if action == "cancel":
        if request.requested_by != user.id:
            raise api_error(404, "request_not_found")
        _forward(peer, "POST", f"/requests/{request.remote_id}/cancel", {"requester_ref": user.id})
    else:
        if not peer.trust_admins:
            raise api_error(403, "peer_not_trusted")
        _forward(
            peer, "POST", f"/requests/{request.remote_id}/{action}", {"actor_name": _who(user)}
        )
    _refresh(session, peer)
