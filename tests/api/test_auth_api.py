"""auth: setup-state, first run, sign-in, lockout, sessions, logout, me."""

from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AppSession, AppUser, AuditEvent
from app.security.sessions import SESSION_COOKIE
from app.security.tokens import sha256_hex
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    sign_in,
)

LOGIN = "/api/v1/auth/login"
FIRST_RUN = "/api/v1/auth/first-run"
WRONG_PASSWORD = "Synthetic-" + "w" * 12


async def rows(engine: AsyncEngine, model: type[Any]) -> list[Any]:
    async with engine.connect() as connection:
        return list((await connection.execute(select(model))).all())


async def test_first_run_creates_the_admin_once_then_answers_404(
    client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    state = await client.get("/api/v1/auth/setup-state")
    assert state.json() == {"needs_first_run": True}
    assert (await client.get(FIRST_RUN)).status_code == 200

    created = await client.post(
        FIRST_RUN, json={"email": " Admin.One@Example.com ", "password": ADMIN_PASSWORD}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "admin"
    assert body["csrf_token"]
    # The first admin is signed in at once.
    me = await client.get("/api/v1/auth/me")
    assert me.json()["csrf_token"] == body["csrf_token"]

    state = await client.get("/api/v1/auth/setup-state")
    assert state.json() == {"needs_first_run": False}
    again = await client.post(
        FIRST_RUN, json={"email": "other@example.com", "password": ADMIN_PASSWORD}
    )
    assert again.status_code == 404
    assert again.headers["content-type"] == "application/problem+json"
    assert (await client.get(FIRST_RUN)).status_code == 404
    assert len(await rows(db_engine, AppUser)) == 1


async def test_first_run_is_closed_when_any_user_exists(
    client: httpx.AsyncClient, technician: AppUser
) -> None:
    response = await client.post(
        FIRST_RUN, json={"email": "other@example.com", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 404
    assert (await client.get("/api/v1/auth/setup-state")).json() == {
        "needs_first_run": False
    }


async def test_first_run_rejects_a_short_password_without_echoing_it(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        FIRST_RUN, json={"email": ADMIN_EMAIL, "password": "short-pw"}
    )
    assert response.status_code == 422
    problem = response.json()
    assert problem["status"] == 422
    assert problem["errors"][0]["field"] == "body.password"
    assert "short-pw" not in response.text
    assert problem["request_id"] == response.headers["x-request-id"]


async def test_login_sets_a_strict_session_cookie(
    client: httpx.AsyncClient, admin: AppUser, db_engine: AsyncEngine
) -> None:
    response = await client.post(
        LOGIN, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": str(admin.id),
        "email": ADMIN_EMAIL,
        "role": "admin",
        "disabled": False,
        "locked_until": None,
        "created_at": "2027-01-01T00:00:00Z",
    }
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=43200"):
        assert attribute.lower() in cookie.lower()
    # The database keeps the hash of the cookie secret, never the secret.
    secret = client.cookies[SESSION_COOKIE]
    sessions = await rows(db_engine, AppSession)
    assert [row.id_hash for row in sessions] == [sha256_hex(secret)]
    assert secret not in str(sessions)


@pytest.mark.parametrize(
    ("email", "password"),
    [(ADMIN_EMAIL, WRONG_PASSWORD), ("nobody@example.com", ADMIN_PASSWORD)],
)
async def test_wrong_password_and_unknown_address_answer_alike(
    client: httpx.AsyncClient, admin: AppUser, email: str, password: str
) -> None:
    response = await client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 401
    problem = response.json()
    assert problem["title"] == "Sign-in failed"
    assert problem["detail"] == "The e-mail address or the password is wrong."
    assert SESSION_COOKIE not in client.cookies


async def test_five_failures_lock_the_account_for_five_minutes(
    client: httpx.AsyncClient, admin: AppUser, clock: FakeClock
) -> None:
    wrong = {"email": ADMIN_EMAIL, "password": WRONG_PASSWORD}
    right = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    for _ in range(4):
        assert (await client.post(LOGIN, json=wrong)).status_code == 401
        clock.advance(seconds=10)
    fifth = await client.post(LOGIN, json=wrong)
    assert fifth.status_code == 423
    assert fifth.headers["retry-after"] == "300"

    # Locked: even the right password is refused until the five minutes pass.
    clock.advance(minutes=4, seconds=59)
    locked = await client.post(LOGIN, json=right)
    assert locked.status_code == 423
    assert locked.headers["retry-after"] == "1"
    clock.advance(seconds=1)
    response = await client.post(LOGIN, json=right)
    assert response.status_code == 200
    assert response.json()["user"]["locked_until"] is None


async def test_a_success_resets_the_failure_count(
    client: httpx.AsyncClient, admin: AppUser, db_engine: AsyncEngine
) -> None:
    wrong = {"email": ADMIN_EMAIL, "password": WRONG_PASSWORD}
    for _ in range(4):
        assert (await client.post(LOGIN, json=wrong)).status_code == 401
    await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    for _ in range(4):
        assert (await client.post(LOGIN, json=wrong)).status_code == 401
    (user,) = await rows(db_engine, AppUser)
    assert user.failed_logins == 4
    assert user.locked_until is None


async def test_a_disabled_account_cannot_sign_in(
    client: httpx.AsyncClient, db_engine: AsyncEngine, admin: AppUser
) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(text("UPDATE app_user SET disabled = true"))
    response = await client.post(
        LOGIN, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["title"] == "Sign-in failed"


async def test_sign_in_is_rate_limited_per_address(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    attempt = {"email": "nobody@example.com", "password": WRONG_PASSWORD}
    for _ in range(10):
        assert (await client.post(LOGIN, json=attempt)).status_code == 401
    limited = await client.post(LOGIN, json=attempt)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "6"
    clock.advance(seconds=6)
    assert (await client.post(LOGIN, json=attempt)).status_code == 401


async def test_the_session_slides_and_expires_after_twelve_idle_hours(
    client: httpx.AsyncClient, admin: AppUser, clock: FakeClock
) -> None:
    await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    clock.advance(hours=11)
    used = await client.get("/api/v1/auth/me")
    assert used.status_code == 200
    # Use moves the expiry and renews the cookie.
    assert used.headers["set-cookie"].startswith(f"{SESSION_COOKIE}=")
    clock.advance(hours=11)
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    clock.advance(hours=12, seconds=1)
    expired = await client.get("/api/v1/auth/me")
    assert expired.status_code == 401
    assert expired.json()["title"] == "Not signed in"


async def test_me_and_logout(
    client: httpx.AsyncClient, technician: AppUser, db_engine: AsyncEngine
) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    me = await client.get("/api/v1/auth/me")
    assert me.json() == {
        "id": str(technician.id),
        "email": TECHNICIAN_EMAIL,
        "role": "technician",
        "csrf_token": csrf,
    }
    response = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: csrf})
    assert response.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert await rows(db_engine, AppSession) == []


async def test_sign_in_events_are_audited_by_id(
    client: httpx.AsyncClient, admin: AppUser, db_engine: AsyncEngine
) -> None:
    await client.post(LOGIN, json={"email": ADMIN_EMAIL, "password": WRONG_PASSWORD})
    await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": WRONG_PASSWORD}
    )
    await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    events = [
        (row.action, row.actor, row.target_id, row.details.get("reason"))
        for row in await rows(db_engine, AuditEvent)
    ]
    assert len(events) == 3
    assert set(events) == {
        ("auth.login", f"user:{admin.id}", str(admin.id), None),
        ("auth.login_failed", "anonymous", None, "unknown"),
        ("auth.login_failed", "anonymous", str(admin.id), "password"),
    }
    # Ids, never the address that was typed (legal D-7).
    for row in await rows(db_engine, AuditEvent):
        assert "example.com" not in str(row.details)


async def test_a_technician_cannot_use_the_admin_routes(
    client: httpx.AsyncClient, technician: AppUser
) -> None:
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    assert (await client.get("/api/v1/users")).status_code == 403
    assert (await client.get("/api/v1/tokens")).status_code == 403
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "nightly script", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    assert created.status_code == 403
    assert created.json()["title"] == "Admin role required"
