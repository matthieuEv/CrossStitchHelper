"""Shared library on one instance (Lot 11a, issue #78)."""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image

MakeUser = Callable[..., TestClient]


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _import(
    client: TestClient,
    name: str,
    *,
    columns: int = 4,
    rows: int = 3,
    code: str = "310",
    library: str = "personal",
) -> dict[str, Any]:
    """A small pattern made through the real import wizard API."""
    job = client.post("/api/imports", files={"file": ("grille.png", _png(), "image/png")}).json()
    patched = client.patch(
        f"/api/imports/{job['id']}/config",
        json={
            "columns": columns,
            "rows": rows,
            "palette": [
                {"code": code, "name": f"DMC {code}", "rgb_hex": "#000000", "symbol_key": "X"}
            ],
            "fills": [
                {"x0": 0, "y0": 0, "x1": columns - 1, "y1": rows - 1, "palette_index": 1}
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    response = client.post(
        f"/api/imports/{job['id']}/commit", json={"name": name, "library": library}
    )
    assert response.status_code in (200, 201), response.text
    body: dict[str, Any] = response.json()
    return body


def _shared(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/shared")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _summary(client: TestClient, pattern_id: str) -> dict[str, Any]:
    [summary] = [p for p in client.get("/api/patterns").json() if p["id"] == pattern_id]
    return summary  # type: ignore[no-any-return]


def _stitch(client: TestClient, pattern_id: str, indices: list[int]) -> None:
    response = client.post(
        f"/api/patterns/{pattern_id}/progress",
        json={"base_version": 0, "ops": [{"index": i, "stitched": True} for i in indices]},
    )
    assert response.status_code == 200, response.text


# --- Sharing and copying -----------------------------------------------------


def test_sharing_puts_a_copy_in_the_shared_library_for_everyone(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    mine = _import(bea, "Lavande")["pattern_id"]
    _stitch(bea, mine, [0, 1])

    shared_id = bea.post(f"/api/patterns/{mine}/share").json()["id"]

    # The personal pattern stays, with its progress, now linked.
    summary = _summary(bea, mine)
    assert summary["stitched_count"] == 2
    assert summary["origin_pattern_id"] == shared_id
    assert summary["update_available"] is False

    # Everybody sees the shared copy, credited to Bea, without progress.
    [listed] = _shared(client)["patterns"]
    assert listed["id"] == shared_id
    assert listed["name"] == "Lavande"
    assert listed["contributed_by_name"] == "Bea Tester"
    assert listed["revision"] == 1
    assert client.get(f"/api/shared/patterns/{shared_id}/grid").status_code == 200
    # It is not anybody's personal pattern.
    assert shared_id not in [p["id"] for p in client.get("/api/patterns").json()]
    assert client.get(f"/api/patterns/{shared_id}").status_code == 404
    assert client.get(f"/api/patterns/{shared_id}/progress").status_code == 404

    again = bea.post(f"/api/patterns/{mine}/share")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "pattern_already_shared"


def test_copying_a_shared_pattern_into_ones_library(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")

    copied = bea.post(f"/api/shared/patterns/{shared_id}/copy", json={"name": "Mes citrons"})
    assert copied.status_code == 201
    copy_id = copied.json()["id"]

    summary = _summary(bea, copy_id)
    assert summary["name"] == "Mes citrons"
    assert summary["stitched_count"] == 0
    assert summary["origin_pattern_id"] == shared_id
    [listed] = _shared(bea)["patterns"]
    assert listed["my_copy_ids"] == [copy_id]
    # Somebody else's copies are not "mine".
    assert _shared(client)["patterns"][0]["my_copy_ids"] == []


def test_import_straight_into_the_shared_library_or_both(client: TestClient) -> None:
    only_shared = _import(client, "Partagé seulement", library="shared")
    assert only_shared["pattern_id"] is None
    assert only_shared["shared_pattern_id"] is not None
    assert client.get("/api/patterns").json() == []

    both = _import(client, "Les deux", library="both")
    assert both["pattern_id"] is not None
    assert _summary(client, both["pattern_id"])["origin_pattern_id"] == both["shared_pattern_id"]
    assert {p["name"] for p in _shared(client)["patterns"]} == {"Partagé seulement", "Les deux"}


# --- What only admins do -----------------------------------------------------


def test_regular_profiles_cannot_edit_replace_or_remove(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    own = _import(bea, "Mine")["pattern_id"]
    for response in (
        bea.patch(f"/api/shared/patterns/{shared_id}", json={"name": "Renamed"}),
        bea.post(f"/api/shared/patterns/{shared_id}/replace", json={"source_pattern_id": own}),
        bea.delete(f"/api/shared/patterns/{shared_id}"),
    ):
        assert response.status_code == 403
    assert _shared(client)["patterns"][0]["name"] == "Citrus"


def test_renaming_does_not_notify_copies(client: TestClient, make_user: MakeUser) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    copy_id = bea.post(f"/api/shared/patterns/{shared_id}/copy", json={"name": "C"}).json()["id"]

    renamed = client.patch(
        f"/api/shared/patterns/{shared_id}", json={"name": "Agrumes", "labels": ["Fruits"]}
    )
    assert renamed.status_code == 200
    listed = _shared(client)["patterns"][0]
    assert (listed["name"], listed["labels"], listed["revision"]) == ("Agrumes", ["Fruits"], 1)
    assert _summary(bea, copy_id)["update_available"] is False


def test_replacing_content_notifies_copies_and_updating_keeps_progress(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    copy_id = bea.post(f"/api/shared/patterns/{shared_id}/copy", json={"name": "C"}).json()["id"]
    _stitch(bea, copy_id, [0, 5])

    # Same shape, another colour: the admin's corrected version.
    fixed = _import(client, "Citrus v2", code="742")["pattern_id"]
    replaced = client.post(
        f"/api/shared/patterns/{shared_id}/replace", json={"source_pattern_id": fixed}
    )
    assert replaced.status_code == 200
    assert _shared(client)["patterns"][0]["revision"] == 2
    assert _shared(client)["patterns"][0]["name"] == "Citrus"  # name kept

    assert _summary(bea, copy_id)["update_available"] is True
    updated = bea.post(f"/api/patterns/{copy_id}/update-from-origin", json={"name": "C (new)"})
    assert updated.json() == {"pattern_id": copy_id, "in_place": True}

    after = _summary(bea, copy_id)
    assert after["update_available"] is False
    assert after["stitched_count"] == 2  # progress untouched
    palette = bea.get(f"/api/patterns/{copy_id}").json()["palette"]
    assert [entry["code"] for entry in palette] == ["742"]


def test_an_update_that_would_lose_progress_makes_a_new_copy(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    copy_id = bea.post(f"/api/shared/patterns/{shared_id}/copy", json={"name": "C"}).json()["id"]
    _stitch(bea, copy_id, [0])

    bigger = _import(client, "Citrus XL", columns=6, rows=5)["pattern_id"]
    client.post(f"/api/shared/patterns/{shared_id}/replace", json={"source_pattern_id": bigger})

    updated = bea.post(f"/api/patterns/{copy_id}/update-from-origin", json={"name": "C (6×5)"})
    body = updated.json()
    assert body["in_place"] is False
    assert body["pattern_id"] != copy_id

    old, new = _summary(bea, copy_id), _summary(bea, body["pattern_id"])
    assert (old["width"], old["stitched_count"], old["origin_pattern_id"]) == (4, 1, None)
    assert (new["width"], new["stitched_count"], new["origin_pattern_id"]) == (6, 0, shared_id)
    assert new["name"] == "C (6×5)"


# --- Requests ----------------------------------------------------------------


def test_removal_request_granted_by_an_admin(client: TestClient, make_user: MakeUser) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    copy_id = bea.post(f"/api/shared/patterns/{shared_id}/copy", json={"name": "C"}).json()["id"]

    asked = bea.post(
        "/api/shared/requests",
        json={"kind": "removal", "shared_pattern_id": shared_id, "message": "Doublon"},
    )
    assert asked.status_code == 201
    request = asked.json()
    assert (request["status"], request["mine"], request["message"]) == ("pending", True, "Doublon")
    duplicate = bea.post(
        "/api/shared/requests", json={"kind": "removal", "shared_pattern_id": shared_id}
    )
    assert duplicate.status_code == 409

    # Admins see it pending, and only they decide.
    [pending] = _shared(client)["requests"]
    assert pending["requested_by_name"] == "Bea Tester"
    assert pending["mine"] is False
    assert bea.post(f"/api/shared/requests/{request['id']}/accept").status_code == 403
    granted = client.post(f"/api/shared/requests/{request['id']}/accept")
    assert granted.status_code == 200
    assert granted.json()["status"] == "accepted"

    assert _shared(client)["patterns"] == []
    # The copy keeps its content, no longer linked; Bea sees the outcome.
    assert _summary(bea, copy_id)["origin_pattern_id"] is None
    [mine] = _shared(bea)["requests"]
    assert (mine["status"], mine["pattern_name"], mine["shared_pattern_id"]) == (
        "accepted",
        "Citrus",
        None,
    )
    # Settled requests no longer show up for admins.
    assert _shared(client)["requests"] == []


def test_replacement_proposal_is_frozen_then_accepted(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    proposal_source = _import(bea, "Citrus corrigé", code="742")["pattern_id"]

    asked = bea.post(
        "/api/shared/requests",
        json={
            "kind": "replacement",
            "shared_pattern_id": shared_id,
            "proposal_pattern_id": proposal_source,
        },
    )
    assert asked.status_code == 201
    request = asked.json()
    proposal_id = request["proposal_pattern_id"]
    assert proposal_id not in (None, proposal_source)

    # Frozen: Bea deleting her pattern does not take the proposal away.
    assert bea.delete(f"/api/patterns/{proposal_source}").status_code == 204
    # Admins (and Bea) can look at it; somebody else cannot.
    assert client.get(f"/api/shared/patterns/{proposal_id}/grid").status_code == 200
    assert bea.get(f"/api/shared/patterns/{proposal_id}").status_code == 200
    cleo = make_user("cleo@example.com")
    assert cleo.get(f"/api/shared/patterns/{proposal_id}").status_code == 404
    # It is not part of the shared library.
    assert [p["id"] for p in _shared(cleo)["patterns"]] == [shared_id]

    accepted = client.post(f"/api/shared/requests/{request['id']}/accept")
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["proposal_pattern_id"] is None
    listed = _shared(client)["patterns"][0]
    assert listed["revision"] == 2
    palette = client.get(f"/api/shared/patterns/{shared_id}").json()["palette"]
    assert [entry["code"] for entry in palette] == ["742"]
    assert client.get(f"/api/shared/patterns/{proposal_id}").status_code == 404


def test_replacement_needs_one_of_ones_own_patterns(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    admins_own = _import(client, "Admin's")["pattern_id"]
    bea = make_user("bea@example.com")
    missing = bea.post(
        "/api/shared/requests", json={"kind": "replacement", "shared_pattern_id": shared_id}
    )
    assert missing.status_code == 400
    not_hers = bea.post(
        "/api/shared/requests",
        json={
            "kind": "replacement",
            "shared_pattern_id": shared_id,
            "proposal_pattern_id": admins_own,
        },
    )
    assert not_hers.status_code == 404


def test_reject_and_cancel(client: TestClient, make_user: MakeUser) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    cleo = make_user("cleo@example.com")
    first = bea.post(
        "/api/shared/requests", json={"kind": "removal", "shared_pattern_id": shared_id}
    ).json()
    rejected = client.post(f"/api/shared/requests/{first['id']}/reject")
    assert rejected.json()["status"] == "rejected"
    assert client.post(f"/api/shared/requests/{first['id']}/accept").status_code == 409

    second = bea.post(
        "/api/shared/requests", json={"kind": "removal", "shared_pattern_id": shared_id}
    ).json()
    assert cleo.post(f"/api/shared/requests/{second['id']}/cancel").status_code == 404
    cancelled = bea.post(f"/api/shared/requests/{second['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert len(_shared(client)["patterns"]) == 1


def test_direct_removal_settles_pending_requests(
    client: TestClient, make_user: MakeUser
) -> None:
    shared_id = _import(client, "Citrus", library="shared")["shared_pattern_id"]
    bea = make_user("bea@example.com")
    own = _import(bea, "Mine")["pattern_id"]
    bea.post("/api/shared/requests", json={"kind": "removal", "shared_pattern_id": shared_id})
    bea.post(
        "/api/shared/requests",
        json={"kind": "replacement", "shared_pattern_id": shared_id, "proposal_pattern_id": own},
    )
    assert client.delete(f"/api/shared/patterns/{shared_id}").status_code == 204
    statuses = {r["kind"]: r["status"] for r in _shared(bea)["requests"]}
    assert statuses == {"removal": "accepted", "replacement": "rejected"}


# --- Profiles and backups ----------------------------------------------------


def test_shared_patterns_outlive_their_contributor(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    _import(bea, "Lavande", library="shared")
    bea_id = bea.get("/api/auth/me").json()["id"]
    assert client.delete(f"/api/users/{bea_id}").status_code == 204
    [listed] = _shared(client)["patterns"]
    assert listed["name"] == "Lavande"
    assert listed["contributed_by_name"] is None


def test_backup_round_trip_keeps_the_shared_library(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    both = _import(bea, "Lavande", library="both")
    bea.post(
        "/api/shared/requests",
        json={"kind": "removal", "shared_pattern_id": both["shared_pattern_id"]},
    )
    before = _shared(bea)
    snapshot = client.get("/api/backup").json()
    assert snapshot["format_version"] == 4

    assert client.post("/api/backup/restore", json=snapshot).status_code == 200
    after = _shared(bea)
    assert after["patterns"] == before["patterns"]
    assert [r["id"] for r in after["requests"]] == [r["id"] for r in before["requests"]]
    assert _summary(bea, both["pattern_id"])["origin_pattern_id"] == both["shared_pattern_id"]
