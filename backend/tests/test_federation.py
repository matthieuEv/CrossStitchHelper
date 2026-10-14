"""Sharing between two paired instances (Lot 11b, issue #78).

Two real instances: the host is a separate uvicorn process with its own
data directory, reached over real HTTP; the subscriber is the test client's
in-process instance. Nothing is mocked between them — what is tested is
exactly what two servers at two homes would exchange.
"""

from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import USER_PASSWORD
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db import get_session_factory
from app.federation import decode_invitation
from app.models import PeerInvitation

BACKEND = Path(__file__).resolve().parent.parent
MakeUser = Callable[..., TestClient]


# `TestClient` (the subscriber, in process) is an `httpx.Client` too: the
# same helpers drive both instances.
Api = httpx.Client


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _import(
    api: Api,
    name: str,
    *,
    code: str = "310",
    columns: int = 4,
    library: str = "personal",
    target: str | None = None,
) -> dict[str, Any]:
    job = api.post("/api/imports", files={"file": ("grille.png", _png(), "image/png")}).json()
    patched = api.patch(
        f"/api/imports/{job['id']}/config",
        json={
            "columns": columns,
            "rows": 3,
            "palette": [
                {"code": code, "name": f"DMC {code}", "rgb_hex": "#000000", "symbol_key": "X"}
            ],
            "fills": [{"x0": 0, "y0": 0, "x1": columns - 1, "y1": 2, "palette_index": 1}],
        },
    )
    assert patched.status_code == 200, patched.text
    body: dict[str, Any] = {"name": name, "library": library}
    if target is not None:
        body["shared_target_peer_id"] = target
    committed = api.post(f"/api/imports/{job['id']}/commit", json=body)
    assert committed.status_code in (200, 201), committed.text
    result: dict[str, Any] = committed.json()
    return result


def _shared(api: Api) -> dict[str, Any]:
    response = api.get("/api/shared")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _sync(api: Api) -> dict[str, Any]:
    # Opening the shared tab asks for a sync; tests do it explicitly.
    from app import federation

    federation._last_sync_by_peer.clear()
    response = api.post("/api/federation/sync")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _summary(api: Api, pattern_id: str) -> dict[str, Any]:
    [summary] = [p for p in api.get("/api/patterns").json() if p["id"] == pattern_id]
    return summary  # type: ignore[no-any-return]


class Host:
    def __init__(self, base_url: str, admin: httpx.Client, process: subprocess.Popen[bytes]):
        self.base_url = base_url
        self.admin = admin
        self.process = process

    def invite(self, *, trust_admins: bool = False) -> str:
        response = self.admin.post(
            "/api/federation/invitations",
            json={"public_url": self.base_url, "trust_admins": trust_admins},
        )
        assert response.status_code == 201, response.text
        code: str = response.json()["code"]
        return code


@pytest.fixture
def host(tmp_path: Path) -> Iterator[Host]:
    """A second, real instance, in its own process and data directory."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {
        **os.environ,
        "CSH_DATA_DIR": str(tmp_path / "host-data"),
        "CSH_RUN_AUTO_BACKUP_LOOP": "false",
        "CSH_RUN_FEDERATION_LOOP": "false",
    }
    env.pop("CSH_FRONTEND_DIST", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    admin = httpx.Client(base_url=base_url, headers={"X-CSH-Client": "test"}, timeout=30)
    try:
        for _ in range(150):
            try:
                if admin.get("/api/health").json().get("status") == "ok":
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("the host instance did not start")
        setup = admin.post(
            "/api/auth/setup",
            json={
                "email": "hana@example.com",
                "first_name": "Hana",
                "last_name": "Host",
                "password": "host-password",
            },
        )
        assert setup.status_code == 201, setup.text
        admin.put("/api/federation/instance", json={"name": "Site A"})
        yield Host(base_url, admin, process)
    finally:
        admin.close()
        process.terminate()
        process.wait(timeout=10)


def _join(client: TestClient, host: Host, *, trust_admins: bool = False) -> dict[str, Any]:
    client.put("/api/federation/instance", json={"name": "Site B"})
    joined = client.post(
        "/api/federation/join", json={"code": host.invite(trust_admins=trust_admins)}
    )
    assert joined.status_code == 201, joined.text
    peer: dict[str, Any] = joined.json()
    return peer


# --- Pairing and mirroring -----------------------------------------------------


def test_join_mirrors_the_hosts_shared_library(client: TestClient, host: Host) -> None:
    host_shared = _import(host.admin, "Citrus", library="shared")["shared_pattern_id"]
    _import(host.admin, "Hana's own")  # personal: never leaves the host

    peer = _join(client, host)
    assert (peer["role"], peer["name"], peer["trust_admins"]) == ("host", "Site A", False)
    assert peer["last_error"] is None

    library = _shared(client)
    [mirror] = library["patterns"]
    assert mirror["name"] == "Citrus"
    assert mirror["source_name"] == "Site A"
    assert mirror["contributed_by_name"] == "Hana Host"
    assert mirror["can_moderate"] is False  # untrusted: this admin only asks
    assert mirror["id"] != host_shared  # a mirror has an id of its own here
    assert client.get(f"/api/shared/patterns/{mirror['id']}/grid").status_code == 200
    assert {t["name"] for t in library["targets"]} == {"Site B", "Site A"}

    # The host knows its subscriber.
    [subscriber] = host.admin.get("/api/federation").json()["peers"]
    assert (subscriber["role"], subscriber["name"]) == ("subscriber", "Site B")


def test_an_invitation_works_once(client: TestClient, host: Host) -> None:
    code = host.invite()
    assert client.post("/api/federation/join", json={"code": code}).status_code == 201
    again = client.post("/api/federation/join", json={"code": code})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "invitation_invalid"
    garbled = client.post("/api/federation/join", json={"code": "csh1.not-base64!"})
    assert garbled.json()["detail"]["code"] == "invitation_invalid"


def test_an_expired_invitation_is_hidden_and_refused(client: TestClient) -> None:
    created = client.post(
        "/api/federation/invitations",
        json={"public_url": "http://site-a.test", "trust_admins": False},
    )
    assert created.status_code == 201
    [listed] = client.get("/api/federation").json()["invitations"]
    # Sent in UTC with its offset, or Settings shows it expiring hours early.
    expires_at = datetime.fromisoformat(listed["expires_at"])
    assert expires_at.utcoffset() == timedelta(0)
    assert timedelta(hours=23) < expires_at - datetime.now(UTC) <= timedelta(hours=24)

    with get_session_factory()() as session:
        for invitation in session.execute(select(PeerInvitation)).scalars():
            invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    assert client.get("/api/federation").json()["invitations"] == []
    _, secret = decode_invitation(created.json()["code"])
    refused = client.post(
        "/api/federation/v1/pair",
        json={"secret": secret, "instance_id": "another-instance", "name": "Site B"},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "invitation_expired"


def test_regular_profiles_cannot_manage_links(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    assert bea.get("/api/federation").status_code == 403
    assert bea.post("/api/federation/join", json={"code": host.invite()}).status_code == 403
    # Asking for a fresh pull is for everybody.
    assert bea.post("/api/federation/sync").status_code == 200


def test_the_protocol_needs_the_peer_token(client: TestClient, host: Host) -> None:
    anonymous = httpx.Client(base_url=host.base_url)
    assert anonymous.get("/api/federation/v1/changes").status_code == 401
    assert (
        anonymous.get(
            "/api/federation/v1/changes", headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )
    # A profile's session is not a peer token either.
    assert host.admin.get("/api/federation/v1/requests").status_code == 401
    assert anonymous.get("/api/federation/v1/info").json()["protocol"] == 1


# --- Copies and updates --------------------------------------------------------


def test_a_copy_hears_about_the_hosts_replacement(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    host_shared = _import(host.admin, "Citrus", library="shared")["shared_pattern_id"]
    _join(client, host)
    bea = make_user("bea@example.com")
    mirror_id = _shared(bea)["patterns"][0]["id"]
    copy_id = bea.post(f"/api/shared/patterns/{mirror_id}/copy", json={"name": "C"}).json()["id"]
    bea.post(
        f"/api/patterns/{copy_id}/progress",
        json={"base_version": 0, "ops": [{"index": 0, "stitched": True}]},
    )

    fixed = _import(host.admin, "Citrus v2", code="742")["pattern_id"]
    host.admin.post(
        f"/api/shared/patterns/{host_shared}/replace", json={"source_pattern_id": fixed}
    )

    assert _summary(bea, copy_id)["update_available"] is False  # not pulled yet
    assert _sync(bea)["synced"] == 1
    assert _summary(bea, copy_id)["update_available"] is True
    updated = bea.post(f"/api/patterns/{copy_id}/update-from-origin", json={"name": "C2"})
    assert updated.json() == {"pattern_id": copy_id, "in_place": True}
    assert _summary(bea, copy_id)["stitched_count"] == 1
    assert [e["code"] for e in bea.get(f"/api/patterns/{copy_id}").json()["palette"]] == ["742"]


def test_a_removal_on_the_host_unlinks_copies(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    host_shared = _import(host.admin, "Citrus", library="shared")["shared_pattern_id"]
    _join(client, host)
    bea = make_user("bea@example.com")
    mirror_id = _shared(bea)["patterns"][0]["id"]
    copy_id = bea.post(f"/api/shared/patterns/{mirror_id}/copy", json={"name": "C"}).json()["id"]

    host.admin.delete(f"/api/shared/patterns/{host_shared}")
    _sync(bea)
    assert _shared(bea)["patterns"] == []
    assert _summary(bea, copy_id)["origin_pattern_id"] is None


# --- Writes forwarded to the host ------------------------------------------------


def test_sharing_into_the_hosts_library(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    peer = _join(client, host)
    bea = make_user("bea@example.com")
    mine = _import(bea, "Lavande")["pattern_id"]

    shared = bea.post(f"/api/patterns/{mine}/share", json={"target_peer_id": peer["id"]})
    assert shared.status_code == 201, shared.text

    [on_host] = _shared(host.admin)["patterns"]
    assert on_host["contributed_by_name"] == "Bea Tester · Site B"
    [mirror] = _shared(bea)["patterns"]
    assert mirror["source_name"] == "Site A"
    assert _summary(bea, mine)["origin_pattern_id"] == mirror["id"]

    # Imported straight into the host's library: nothing left here.
    straight = _import(bea, "Direct", library="shared", target=peer["id"])
    assert straight["pattern_id"] is None
    assert {p["name"] for p in _shared(host.admin)["patterns"]} == {"Lavande", "Direct"}
    assert "Direct" not in {p["name"] for p in bea.get("/api/patterns").json()}


def test_requests_go_to_the_host_and_their_outcome_comes_back(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    host_shared = _import(host.admin, "Citrus", library="shared")["shared_pattern_id"]
    _join(client, host)
    bea = make_user("bea@example.com")
    mirror_id = _shared(bea)["patterns"][0]["id"]

    asked = bea.post(
        "/api/shared/requests",
        json={"kind": "removal", "shared_pattern_id": mirror_id, "message": "Doublon"},
    )
    assert asked.status_code == 201, asked.text
    assert (asked.json()["mine"], asked.json()["status"]) == (True, "pending")

    [pending] = _shared(host.admin)["requests"]
    assert pending["requested_by_name"] == "Bea Tester · Site B"
    assert pending["message"] == "Doublon"
    host.admin.post(f"/api/shared/requests/{pending['id']}/accept")

    _sync(bea)
    [outcome] = _shared(bea)["requests"]
    assert (outcome["status"], outcome["pattern_name"], outcome["mine"]) == (
        "accepted",
        "Citrus",
        True,
    )
    assert _shared(host.admin)["patterns"] == []
    assert host_shared not in [p["id"] for p in _shared(host.admin)["patterns"]]


def test_a_proposal_reaches_the_host_frozen(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host)
    bea = make_user("bea@example.com")
    mirror_id = _shared(bea)["patterns"][0]["id"]
    version = _import(bea, "Citrus corrigé", code="742")["pattern_id"]

    bea.post(
        "/api/shared/requests",
        json={
            "kind": "replacement",
            "shared_pattern_id": mirror_id,
            "proposal_pattern_id": version,
        },
    )
    bea.delete(f"/api/patterns/{version}")  # frozen when sent

    [pending] = _shared(host.admin)["requests"]
    assert (
        host.admin.get(f"/api/shared/patterns/{pending['proposal_pattern_id']}/grid").status_code
        == 200
    )
    host.admin.post(f"/api/shared/requests/{pending['id']}/accept")
    _sync(bea)
    [mirror] = _shared(bea)["patterns"]
    assert mirror["revision"] == 2
    palette = bea.get(f"/api/shared/patterns/{mirror['id']}").json()["palette"]
    assert [entry["code"] for entry in palette] == ["742"]

    # Withdrawing works across instances too.
    bea.post("/api/shared/requests", json={"kind": "removal", "shared_pattern_id": mirror["id"]})
    mine = next(r for r in _shared(bea)["requests"] if r["status"] == "pending")
    cancelled = bea.post(f"/api/shared/requests/{mine['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert all(r["status"] != "pending" for r in _shared(host.admin)["requests"])


# --- Moderation by the subscriber's admins ------------------------------------------


def test_untrusted_admins_only_ask(client: TestClient, host: Host) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host, trust_admins=False)
    mirror_id = _shared(client)["patterns"][0]["id"]
    renamed = client.patch(f"/api/shared/patterns/{mirror_id}", json={"name": "Agrumes"})
    assert renamed.status_code == 403
    assert renamed.json()["detail"]["code"] == "peer_not_trusted"
    assert client.delete(f"/api/shared/patterns/{mirror_id}").status_code == 403


def test_trusted_admins_moderate_the_hosts_library(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host, trust_admins=True)
    [mirror] = _shared(client)["patterns"]
    assert mirror["can_moderate"] is True

    renamed = client.patch(f"/api/shared/patterns/{mirror['id']}", json={"name": "Agrumes"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Agrumes"
    assert _shared(host.admin)["patterns"][0]["name"] == "Agrumes"

    # A request made on the host is decided from here.
    host_user = httpx.Client(base_url=host.base_url, headers={"X-CSH-Client": "test"})
    created = host.admin.post(
        "/api/users",
        json={
            "email": "ivy@example.com",
            "first_name": "Ivy",
            "last_name": "Host",
            "password": USER_PASSWORD,
        },
    ).json()
    host_user.post("/api/auth/login", json={"user_id": created["id"], "password": USER_PASSWORD})
    host_shared_id = _shared(host_user)["patterns"][0]["id"]
    host_user.post(
        "/api/shared/requests", json={"kind": "removal", "shared_pattern_id": host_shared_id}
    )

    _sync(client)
    [pending] = [r for r in _shared(client)["requests"] if r["status"] == "pending"]
    assert pending["requested_by_name"] == "Ivy Host"
    rejected = client.post(f"/api/shared/requests/{pending['id']}/reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert [r["status"] for r in _shared(host_user)["requests"]] == ["rejected"]
    host_user.close()


# --- Leaving, revoking, outages --------------------------------------------------


def test_leaving_drops_mirrors_but_keeps_copies(
    client: TestClient, host: Host, make_user: MakeUser
) -> None:
    _import(host.admin, "Citrus", library="shared")
    peer = _join(client, host)
    bea = make_user("bea@example.com")
    mirror_id = _shared(bea)["patterns"][0]["id"]
    copy_id = bea.post(f"/api/shared/patterns/{mirror_id}/copy", json={"name": "C"}).json()["id"]

    assert client.delete(f"/api/federation/peers/{peer['id']}").status_code == 204
    assert _shared(bea)["patterns"] == []
    assert _summary(bea, copy_id)["origin_pattern_id"] is None
    assert host.admin.get("/api/federation").json()["peers"] == []  # told the host


def test_a_revoked_subscriber_is_refused(client: TestClient, host: Host) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host)
    [subscriber] = host.admin.get("/api/federation").json()["peers"]
    host.admin.delete(f"/api/federation/peers/{subscriber['id']}")

    result = _sync(client)
    assert result == {"synced": 0, "errors": ["peer_auth_failed"]}
    [peer] = client.get("/api/federation").json()["peers"]
    assert peer["last_error"] == "peer_auth_failed"
    # What was mirrored stays readable.
    assert len(_shared(client)["patterns"]) == 1


def test_an_unreachable_host_leaves_the_mirror_readable(client: TestClient, host: Host) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host)
    host.process.terminate()
    host.process.wait(timeout=10)

    assert _sync(client)["errors"] == ["peer_unreachable"]
    [mirror] = _shared(client)["patterns"]
    copied = client.post(f"/api/shared/patterns/{mirror['id']}/copy", json={"name": "Offline"})
    assert copied.status_code == 201
    asked = client.post(
        "/api/shared/requests", json={"kind": "removal", "shared_pattern_id": mirror["id"]}
    )
    assert asked.status_code == 502
    assert asked.json()["detail"]["code"] == "peer_unreachable"


def test_mirrors_are_not_in_backups_and_come_back_after_a_restore(
    client: TestClient, host: Host
) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host)
    snapshot = client.get("/api/backup").json()
    assert snapshot["patterns"] == []

    assert client.post("/api/backup/restore", json=snapshot).status_code == 200
    assert _shared(client)["patterns"] == []  # mirrors went with the restore
    _sync(client)
    assert [p["name"] for p in _shared(client)["patterns"]] == ["Citrus"]


def test_a_restore_on_the_host_reaches_its_subscribers(client: TestClient, host: Host) -> None:
    _import(host.admin, "Citrus", library="shared")
    _join(client, host)
    empty = host.admin.get("/api/backup").json()
    _import(host.admin, "Added later", library="shared")
    _sync(client)
    assert len(_shared(client)["patterns"]) == 2

    host.admin.post("/api/backup/restore", json=empty)
    _sync(client)
    assert [p["name"] for p in _shared(client)["patterns"]] == ["Citrus"]


def test_personal_libraries_never_cross(client: TestClient, host: Host) -> None:
    mine = _import(host.admin, "Hana's own")["pattern_id"]
    _join(client, host)
    assert all(p["name"] != "Hana's own" for p in _shared(client)["patterns"])
    # Not even a guess through the protocol.
    from app.db import get_session_factory
    from app.models import Peer

    with get_session_factory()() as session:
        token = session.query(Peer).one().outbound_token
    peer = httpx.Client(base_url=host.base_url, headers={"Authorization": f"Bearer {token}"})
    assert peer.get(f"/api/federation/v1/patterns/{mine}").status_code == 404
    peer.close()
