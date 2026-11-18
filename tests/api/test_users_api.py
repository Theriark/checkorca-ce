"""users: admin-only account management, the last-admin rule, pagination."""

import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AppSession, AppUser
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    add_user,
    another_browser,
    sign_in,
)

NEW_PASSWORD = "Synthetic-" + "n" * 12


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    """The admin is signed in; the CSRF token of the session."""
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def session_count(engine: AsyncEngine, user: AppUser) -> int:
    query = select(func.count()).where(AppSession.user_id == user.id)
    async with engine.connect() as connection:
        return int((await connection.execute(query)).scalar_one())


async def test_create_get_and_list_users(client: httpx.AsyncClient, csrf: str) -> None:
    created = await client.post(
        "/api/v1/users",
        json={
            "email": "Technician.Two@Example.com",
            "password": TECHNICIAN_PASSWORD,
            "role": "technician",
        },
        headers={CSRF_HEADER: csrf},
    )
    assert created.status_code == 201
    user = created.json()
    assert user["email"] == "technician.two@example.com"
    assert user["role"] == "technician"
    assert "password" not in created.text
    assert "argon2" not in created.text

    fetched = await client.get(f"/api/v1/users/{user['id']}")
    assert fetched.json() == user
    listed = await client.get("/api/v1/users")
    assert [item["email"] for item in listed.json()["items"]] == [
        ADMIN_EMAIL,
        "technician.two@example.com",
    ]
    assert listed.json()["next_cursor"] is None


async def test_a_taken_address_answers_409(
    client: httpx.AsyncClient, csrf: str
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={"email": ADMIN_EMAIL, "password": NEW_PASSWORD, "role": "admin"},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-address", "password": NEW_PASSWORD, "role": "admin"},
        {"email": "new@example.com", "password": "too-short", "role": "admin"},
        {"email": "new@example.com", "password": NEW_PASSWORD, "role": "owner"},
        {"email": "new@example.com", "password": NEW_PASSWORD},
        {
            "email": "new@example.com",
            "password": NEW_PASSWORD,
            "role": "admin",
            "disabled": True,
        },
    ],
)
async def test_invalid_users_answer_422(
    client: httpx.AsyncClient, csrf: str, body: dict[str, object]
) -> None:
    response = await client.post(
        "/api/v1/users", json=body, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 422
    assert response.json()["errors"]


async def test_users_page_with_a_cursor(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    for index in range(4):
        await add_user(
            db_engine, f"user{index}@example.com", NEW_PASSWORD, "technician"
        )
    emails: list[str] = []
    cursor = None
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = (await client.get("/api/v1/users", params=params)).json()
        emails += [item["email"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert emails == [ADMIN_EMAIL] + [f"user{index}@example.com" for index in range(4)]


@pytest.mark.parametrize("cursor", ["%%%", "e30", "eyJlbWFpbCI6IDF9"])
async def test_an_invalid_cursor_answers_400(
    client: httpx.AsyncClient, csrf: str, cursor: str
) -> None:
    response = await client.get("/api/v1/users", params={"cursor": cursor})
    assert response.status_code == 400
    assert response.json()["title"] == "Invalid cursor"


@pytest.mark.parametrize("limit", [0, 201])
async def test_the_limit_is_bounded(
    client: httpx.AsyncClient, csrf: str, limit: int
) -> None:
    response = await client.get("/api/v1/users", params={"limit": limit})
    assert response.status_code == 422


async def test_change_role_and_disable(
    app: FastAPI,
    client: httpx.AsyncClient,
    csrf: str,
    technician: AppUser,
    db_engine: AsyncEngine,
) -> None:
    url = f"/api/v1/users/{technician.id}"
    promoted = await client.patch(
        url, json={"role": "admin"}, headers={CSRF_HEADER: csrf}
    )
    assert promoted.json()["role"] == "admin"

    async with another_browser(app) as other:
        await sign_in(other, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
        disabled = await client.patch(
            url, json={"disabled": True}, headers={CSRF_HEADER: csrf}
        )
        assert disabled.json()["disabled"] is True
        # Disabling ends the user's sessions at once.
        assert (await other.get("/api/v1/auth/me")).status_code == 401
    assert await session_count(db_engine, technician) == 0


async def test_a_new_password_replaces_the_old_and_clears_a_lock(
    client: httpx.AsyncClient, csrf: str, technician: AppUser, db_engine: AsyncEngine
) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE app_user SET failed_logins = 3, "
                "locked_until = '2099-01-01T00:00:00Z' WHERE role = 'technician'"
            )
        )
    response = await client.patch(
        f"/api/v1/users/{technician.id}",
        json={"password": NEW_PASSWORD},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 200
    assert response.json()["locked_until"] is None
    old = await client.post(
        "/api/v1/auth/login",
        json={"email": TECHNICIAN_EMAIL, "password": TECHNICIAN_PASSWORD},
    )
    assert old.status_code == 401
    await sign_in(client, TECHNICIAN_EMAIL, NEW_PASSWORD)


async def test_the_own_password_change_keeps_the_own_session(
    client: httpx.AsyncClient, csrf: str, admin: AppUser
) -> None:
    response = await client.patch(
        f"/api/v1/users/{admin.id}",
        json={"password": NEW_PASSWORD},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


@pytest.mark.parametrize("change", [{"role": "technician"}, {"disabled": True}])
async def test_the_last_admin_cannot_be_demoted_or_disabled(
    client: httpx.AsyncClient, csrf: str, admin: AppUser, change: dict[str, object]
) -> None:
    response = await client.patch(
        f"/api/v1/users/{admin.id}", json=change, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 409
    assert response.json()["title"] == "Last admin"


async def test_an_admin_can_step_down_while_another_admin_remains(
    client: httpx.AsyncClient, csrf: str, admin: AppUser, db_engine: AsyncEngine
) -> None:
    await add_user(db_engine, "admin.two@example.com", NEW_PASSWORD, "admin")
    response = await client.patch(
        f"/api/v1/users/{admin.id}",
        json={"role": "technician"},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 200
    # Now a technician: the admin routes close for this session.
    assert (await client.get("/api/v1/users")).status_code == 403


async def test_delete_a_user(
    client: httpx.AsyncClient, csrf: str, technician: AppUser
) -> None:
    url = f"/api/v1/users/{technician.id}"
    deleted = await client.delete(url, headers={CSRF_HEADER: csrf})
    assert deleted.status_code == 204
    assert (await client.get(url)).status_code == 404
    assert (await client.delete(url, headers={CSRF_HEADER: csrf})).status_code == 404


async def test_an_admin_cannot_delete_themselves(
    client: httpx.AsyncClient, csrf: str, admin: AppUser, db_engine: AsyncEngine
) -> None:
    await add_user(db_engine, "admin.two@example.com", NEW_PASSWORD, "admin")
    response = await client.delete(
        f"/api/v1/users/{admin.id}", headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 409
    assert response.json()["title"] == "Own account"


async def test_unknown_users_answer_404(client: httpx.AsyncClient, csrf: str) -> None:
    url = f"/api/v1/users/{uuid.uuid4()}"
    assert (await client.get(url)).status_code == 404
    patched = await client.patch(url, json={}, headers={CSRF_HEADER: csrf})
    assert patched.status_code == 404
    assert (await client.get("/api/v1/users/not-a-uuid")).status_code == 422
