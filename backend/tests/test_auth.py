"""Profiles, sessions and access rules (Lot 10, issue #77)."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from conftest import ADMIN_PASSWORD, USER_PASSWORD, as_app_client
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update

from app import cli
from app.auth import LoginThrottle
from app.db import get_session_factory
from app.models import Pattern, User, UserSession
from app.seed import DEMO_PATTERN_ID, seed_demo_pattern

MakeUser = Callable[..., TestClient]

_SETUP = {
    "email": "Admin@Example.com",
    "first_name": "Ada",
    "last_name": "Admin",
    "password": ADMIN_PASSWORD,
}


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _admin_id(client: TestClient) -> str:
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    user_id: str = response.json()["id"]
    return user_id


# --- First launch ------------------------------------------------------------


def test_status_before_setup_requires_setup_and_protects_the_api(
    anonymous_client: TestClient,
) -> None:
    assert anonymous_client.get("/api/auth/status").json() == {
        "setup_required": True,
        "user": None,
    }
    response = anonymous_client.get("/api/patterns")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "auth_required"
    # Health stays public: `docker compose`'s healthcheck has no session.
    assert anonymous_client.get("/api/health").status_code == 200


def test_setup_creates_the_first_admin_and_hands_over_existing_patterns(
    anonymous_client: TestClient,
) -> None:
    # A pattern that predates profiles (the seed, or an upgraded instance).
    with get_session_factory()() as session:
        seed_demo_pattern(session)
        assert session.get(Pattern, DEMO_PATTERN_ID).owner_id is None  # type: ignore[union-attr]

    response = anonymous_client.post("/api/auth/setup", json=_SETUP)
    assert response.status_code == 201
    admin = response.json()
    assert admin["role"] == "admin"
    assert admin["email"] == "admin@example.com"  # stored lowercased
    assert admin["initials"] == "AA"

    # Logged in straight away, and the pattern is now theirs.
    status = anonymous_client.get("/api/auth/status").json()
    assert status["setup_required"] is False
    assert status["user"]["id"] == admin["id"]
    [summary] = anonymous_client.get("/api/patterns").json()
    assert summary["id"] == DEMO_PATTERN_ID


def test_setup_is_refused_once_a_profile_exists(client: TestClient) -> None:
    response = client.post("/api/auth/setup", json={**_SETUP, "email": "other@example.com"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "setup_already_done"


def test_seed_after_setup_goes_to_the_first_admin(client: TestClient) -> None:
    with get_session_factory()() as session:
        seed_demo_pattern(session)
    assert [p["id"] for p in client.get("/api/patterns").json()] == [DEMO_PATTERN_ID]


# --- Login screen ------------------------------------------------------------


def test_profiles_list_is_public_but_minimal(client: TestClient, make_user: MakeUser) -> None:
    make_user("bea@example.com")
    anonymous = as_app_client(TestClient(client.app))
    cards = anonymous.get("/api/auth/profiles").json()
    assert [card["first_name"] for card in cards] == ["Ada", "Bea"]
    for card in cards:
        assert set(card) == {"id", "first_name", "initials", "avatar_hue"}
        assert 0 <= card["avatar_hue"] < 360


def test_login_logout_round_trip(client: TestClient) -> None:
    admin_id = _admin_id(client)
    other = as_app_client(TestClient(client.app))

    wrong = other.post("/api/auth/login", json={"user_id": admin_id, "password": "nope-nope"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"]["code"] == "login_failed"
    unknown = other.post("/api/auth/login", json={"user_id": "x" * 32, "password": "whatever"})
    assert unknown.status_code == 401

    ok = other.post("/api/auth/login", json={"user_id": admin_id, "password": ADMIN_PASSWORD})
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"]
    assert "csh_session=" in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert "secure" not in cookie.lower()  # plain HTTP on the home network
    assert other.get("/api/auth/me").json()["id"] == admin_id

    assert other.post("/api/auth/logout").status_code == 204
    assert other.get("/api/auth/me").status_code == 401
    # Logging out one device leaves the others logged in.
    assert client.get("/api/auth/me").status_code == 200


def test_state_changing_requests_need_the_app_header(client: TestClient) -> None:
    bare = TestClient(client.app, cookies=client.cookies)
    response = bare.patch("/api/auth/me", json={"first_name": "Mallory"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "client_header_missing"
    # Reads are not affected.
    assert bare.get("/api/auth/me").status_code == 200


def test_login_throttle_after_repeated_failures(client: TestClient) -> None:
    admin_id = _admin_id(client)
    other = as_app_client(TestClient(client.app))
    for _ in range(5):
        other.post("/api/auth/login", json={"user_id": admin_id, "password": "wrong-pass"})
    blocked = other.post("/api/auth/login", json={"user_id": admin_id, "password": ADMIN_PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "login_throttled"


def test_login_throttle_also_counts_per_profile_across_addresses() -> None:
    throttle = LoginThrottle(per_client=5, per_profile=3, window=60)
    for address in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        assert throttle.retry_after(address, "u1") == 0
        throttle.record_failure(address, "u1")
    # A guesser varying its (proxy-supplied) address still hits the limit.
    assert throttle.retry_after("10.0.0.4", "u1") > 0
    assert throttle.retry_after("10.0.0.4", "u2") == 0


def test_expired_session_is_refused(client: TestClient) -> None:
    with get_session_factory()() as session:
        session.execute(
            update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        session.commit()
    assert client.get("/api/auth/me").status_code == 401


# --- My account --------------------------------------------------------------


def test_profile_edits_its_own_information_but_not_its_role(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    response = bea.patch(
        "/api/auth/me",
        json={"first_name": "Béatrice", "email": "BEA2@example.com", "role": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Béatrice"
    assert body["email"] == "bea2@example.com"
    assert body["role"] == "user"  # `role` is not part of `/me`

    taken = bea.patch("/api/auth/me", json={"email": "admin@example.com"})
    assert taken.status_code == 409
    assert taken.json()["detail"]["code"] == "email_taken"


def test_password_change_keeps_this_device_and_ends_the_others(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    bea_id = bea.get("/api/auth/me").json()["id"]
    bea_phone = as_app_client(TestClient(client.app))
    bea_phone.post("/api/auth/login", json={"user_id": bea_id, "password": USER_PASSWORD})

    wrong = bea.post(
        "/api/auth/me/password",
        json={"current_password": "not-mine!", "new_password": "brand-new-pass"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["detail"]["code"] == "current_password_wrong"

    ok = bea.post(
        "/api/auth/me/password",
        json={"current_password": USER_PASSWORD, "new_password": "brand-new-pass"},
    )
    assert ok.status_code == 204
    assert bea.get("/api/auth/me").status_code == 200
    assert bea_phone.get("/api/auth/me").status_code == 401

    relog = as_app_client(TestClient(client.app)).post(
        "/api/auth/login", json={"user_id": bea_id, "password": "brand-new-pass"}
    )
    assert relog.status_code == 200


def test_password_must_be_long_enough(client: TestClient) -> None:
    response = client.post(
        "/api/auth/me/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


# --- Profile management (admins) ---------------------------------------------


def test_regular_profile_cannot_manage_profiles(client: TestClient, make_user: MakeUser) -> None:
    bea = make_user("bea@example.com")
    for response in (
        bea.get("/api/users"),
        bea.post(
            "/api/users",
            json={
                "email": "x@example.com",
                "first_name": "X",
                "last_name": "Y",
                "password": "12345678",
            },
        ),
        bea.delete(f"/api/users/{_admin_id(client)}"),
    ):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "admin_required"


def test_admin_creates_edits_and_lists_profiles(client: TestClient) -> None:
    created = client.post(
        "/api/users",
        json={
            "email": "Bea@Example.com",
            "first_name": "Bea",
            "last_name": "Brodeuse",
            "password": "initial-pass",
        },
    )
    assert created.status_code == 201
    bea = created.json()
    assert bea["role"] == "user"
    assert bea["pattern_count"] == 0

    duplicate = client.post(
        "/api/users",
        json={
            "email": "bea@example.com",
            "first_name": "Bea",
            "last_name": "Again",
            "password": "initial-pass",
        },
    )
    assert duplicate.status_code == 409

    promoted = client.patch(f"/api/users/{bea['id']}", json={"role": "admin", "last_name": "B."})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert promoted.json()["last_name"] == "B."

    assert [u["first_name"] for u in client.get("/api/users").json()] == ["Ada", "Bea"]
    assert client.patch(f"/api/users/{'0' * 32}", json={"role": "user"}).status_code == 404


def test_admin_password_reset_ends_the_profiles_sessions(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    bea_id = bea.get("/api/auth/me").json()["id"]
    reset = client.patch(f"/api/users/{bea_id}", json={"password": "reset-by-admin"})
    assert reset.status_code == 200
    assert bea.get("/api/auth/me").status_code == 401
    # The admin resetting someone else's password stays logged in.
    assert client.get("/api/auth/me").status_code == 200


def test_admin_resetting_their_own_password_stays_logged_in(client: TestClient) -> None:
    admin_id = _admin_id(client)
    response = client.patch(f"/api/users/{admin_id}", json={"password": "new-admin-pass"})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_the_last_admin_can_be_neither_demoted_nor_deleted(
    client: TestClient, make_user: MakeUser
) -> None:
    admin_id = _admin_id(client)
    demote = client.patch(f"/api/users/{admin_id}", json={"role": "user"})
    assert demote.status_code == 409
    assert demote.json()["detail"]["code"] == "last_admin"
    delete = client.delete(f"/api/users/{admin_id}")
    assert delete.status_code == 409
    assert client.get("/api/auth/me").json()["role"] == "admin"

    # With a second admin, either can step down.
    make_user("cleo@example.com", role="admin")
    assert client.patch(f"/api/users/{admin_id}", json={"role": "user"}).status_code == 200


def test_deleting_a_profile_deletes_its_personal_library(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    bea_id = bea.get("/api/auth/me").json()["id"]
    with get_session_factory()() as session:
        seed_demo_pattern(session)
        session.execute(update(Pattern).values(owner_id=bea_id))
        session.commit()

    [listed] = [u for u in client.get("/api/users").json() if u["id"] == bea_id]
    assert listed["pattern_count"] == 1

    assert client.delete(f"/api/users/{bea_id}").status_code == 204
    with get_session_factory()() as session:
        assert session.get(Pattern, DEMO_PATTERN_ID) is None
        sessions = select(UserSession).where(UserSession.user_id == bea_id)
        assert session.execute(sessions).first() is None
    assert bea.get("/api/auth/me").status_code == 401


# --- Private libraries -------------------------------------------------------


def test_someone_elses_pattern_is_invisible(client: TestClient, make_user: MakeUser) -> None:
    with get_session_factory()() as session:
        seed_demo_pattern(session)
    bea = make_user("bea@example.com")

    assert bea.get("/api/patterns").json() == []
    for path in ("", "/grid", "/progress", "/activity", "/export"):
        response = bea.get(f"/api/patterns/{DEMO_PATTERN_ID}{path}")
        assert response.status_code == 404, path
    assert bea.patch(f"/api/patterns/{DEMO_PATTERN_ID}", json={"name": "Mine"}).status_code == 404
    assert (
        bea.post(
            f"/api/patterns/{DEMO_PATTERN_ID}/progress",
            json={"base_version": 0, "ops": [{"index": 0, "stitched": True}]},
        ).status_code
        == 404
    )
    assert (
        bea.post(f"/api/patterns/{DEMO_PATTERN_ID}/duplicate", json={"name": "Copy"}).status_code
        == 404
    )
    assert bea.delete(f"/api/patterns/{DEMO_PATTERN_ID}").status_code == 404
    # Still there, untouched, for its owner.
    assert client.get(f"/api/patterns/{DEMO_PATTERN_ID}").json()["name"] != "Mine"


def test_imports_belong_to_whoever_started_them(client: TestClient, make_user: MakeUser) -> None:
    bea = make_user("bea@example.com")
    job = bea.post("/api/imports", files={"file": ("grille.png", _png(), "image/png")}).json()

    assert client.get(f"/api/imports/{job['id']}").status_code == 404
    assert client.get(f"/api/imports/{job['id']}/pages/1/preview").status_code == 404
    assert bea.get(f"/api/imports/{job['id']}").status_code == 200

    bea.patch(
        f"/api/imports/{job['id']}/config",
        json={
            "columns": 4,
            "rows": 3,
            "palette": [
                {"code": "310", "name": "Black", "rgb_hex": "#000000", "symbol_key": "X"}
            ],
        },
    )
    committed = bea.post(f"/api/imports/{job['id']}/commit", json={"name": "Bea's"})
    assert committed.status_code in (200, 201), committed.text
    pattern_id = committed.json()["pattern_id"]
    assert [p["id"] for p in bea.get("/api/patterns").json()] == [pattern_id]
    assert client.get(f"/api/patterns/{pattern_id}").status_code == 404


def test_recipes_are_shared_but_only_admins_delete_them(
    client: TestClient, make_user: MakeUser
) -> None:
    from app.models import Recipe

    with get_session_factory()() as session:
        session.add(
            Recipe(
                id="r" * 32,
                fingerprint="a" * 16,
                label="DMC",
                grid_type="C",
                config_json='{"crop_by_page": {}}',
            )
        )
        session.commit()
    bea = make_user("bea@example.com")
    assert len(bea.get("/api/recipes").json()) == 1
    assert bea.delete(f"/api/recipes/{'r' * 32}").status_code == 403
    assert client.delete(f"/api/recipes/{'r' * 32}").status_code == 204


# --- Backups -----------------------------------------------------------------


def test_backup_is_admin_only(client: TestClient, make_user: MakeUser) -> None:
    bea = make_user("bea@example.com")
    assert bea.get("/api/backup").status_code == 403
    assert bea.get("/api/backup/auto").status_code == 403
    restore = bea.post("/api/backup/restore", json={"generated_at": "2026-01-01T00:00:00Z"})
    assert restore.status_code == 403


def test_backup_round_trip_keeps_profiles_and_owners(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    bea_id = bea.get("/api/auth/me").json()["id"]
    with get_session_factory()() as session:
        seed_demo_pattern(session)
        session.execute(update(Pattern).values(owner_id=bea_id))
        session.commit()
    snapshot = client.get("/api/backup").json()

    summary = client.post("/api/backup/restore", json=snapshot)
    assert summary.status_code == 200
    assert summary.json()["users_count"] == 2
    # Profiles present in the backup keep their sessions...
    assert client.get("/api/auth/me").status_code == 200
    assert bea.get("/api/auth/me").status_code == 200
    # ...and their library.
    assert [p["id"] for p in bea.get("/api/patterns").json()] == [DEMO_PATTERN_ID]


def test_restoring_a_v1_backup_gives_everything_to_the_restoring_admin(
    client: TestClient, make_user: MakeUser
) -> None:
    bea = make_user("bea@example.com")
    with get_session_factory()() as session:
        seed_demo_pattern(session)
    snapshot = client.get("/api/backup").json()
    v1 = {key: value for key, value in snapshot.items() if key != "users"}
    v1["format_version"] = 1
    for pattern in v1["patterns"]:
        pattern["owner_id"] = None

    response = client.post("/api/backup/restore", json=v1)
    assert response.status_code == 200
    assert response.json()["users_count"] == 0
    # Profiles untouched, pattern handed to the admin who restored.
    assert bea.get("/api/auth/me").status_code == 200
    assert [p["id"] for p in client.get("/api/patterns").json()] == [DEMO_PATTERN_ID]


def test_restore_without_any_admin_is_refused(client: TestClient) -> None:
    snapshot = client.get("/api/backup").json()
    for user in snapshot["users"]:
        user["role"] = "user"
    response = client.post("/api/backup/restore", json=snapshot)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "backup_without_admin"
    assert client.get("/api/auth/me").json()["role"] == "admin"


# --- Command line ------------------------------------------------------------


def test_cli_reset_password(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    admin_id = _admin_id(client)
    assert cli.main(["reset-password", "ADMIN@example.com"]) == 0
    new_password = capsys.readouterr().out.strip().rsplit(" ", 1)[-1]

    # Every session of that profile ended, the printed password works.
    assert client.get("/api/auth/me").status_code == 401
    other = as_app_client(TestClient(client.app))
    response = other.post("/api/auth/login", json={"user_id": admin_id, "password": new_password})
    assert response.status_code == 200

    assert cli.main(["reset-password", "nobody@example.com"]) == 1


def test_cli_list_profiles(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list-profiles"]) == 0
    assert "admin@example.com\tAda Admin\tadmin" in capsys.readouterr().out


def test_users_table_never_stores_clear_passwords(client: TestClient) -> None:
    with get_session_factory()() as session:
        [user] = session.execute(select(User)).scalars().all()
        assert ADMIN_PASSWORD not in user.password_hash
        assert user.password_hash.startswith("$argon2id$")
