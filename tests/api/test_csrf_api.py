"""CSRF: every state-changing route refuses a session request without the token.

The routes are read from the app, so a route added later is covered without a
change here. Only sign-in and first run are exempt: no session exists yet.
"""

import re
import uuid

import httpx
import pytest

from app.db.models import AppUser
from app.main import create_app
from app.security.sessions import UNSAFE_METHODS
from app.settings import load_settings
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    DATABASE_URL,
    TEST_FERNET_KEY,
    TEST_SECRET_KEY,
    sign_in,
)

CSRF_EXEMPT = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/first-run"),
}


def unsafe_routes() -> list[tuple[str, str]]:
    """Every (method, path) of /api/v1 that can change state.

    Read from the app's OpenAPI document: FastAPI keeps included routers nested,
    so app.routes does not list the full paths.
    """
    settings = load_settings(
        secret_key=TEST_SECRET_KEY,
        fernet_key=TEST_FERNET_KEY,
        database_url=DATABASE_URL,
    )
    paths = create_app(settings, static_dir=None).openapi()["paths"]
    return [
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/v1/")
        for method in sorted(operations)
        if method.upper() in UNSAFE_METHODS
    ]


UNSAFE_ROUTES = unsafe_routes()
STATE_CHANGING = [route for route in UNSAFE_ROUTES if route not in CSRF_EXEMPT]


def concrete(path: str) -> str:
    """The path with a fresh UUID for every path parameter."""
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


def test_the_route_list_is_complete() -> None:
    assert CSRF_EXEMPT <= set(UNSAFE_ROUTES)
    assert set(STATE_CHANGING) >= {
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/users"),
        ("PATCH", "/api/v1/users/{user_id}"),
        ("DELETE", "/api/v1/users/{user_id}"),
        ("POST", "/api/v1/tokens"),
        ("DELETE", "/api/v1/tokens/{token_id}"),
    }


@pytest.mark.parametrize(("method", "path"), STATE_CHANGING)
@pytest.mark.parametrize("token", [None, "", "not-the-session-token"])
async def test_a_state_change_without_the_session_token_is_403(
    client: httpx.AsyncClient,
    admin: AppUser,
    method: str,
    path: str,
    token: str | None,
) -> None:
    await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    headers = {} if token is None else {CSRF_HEADER: token}
    response = await client.request(method, concrete(path), headers=headers, json={})
    assert response.status_code == 403
    assert response.json()["title"] == "CSRF token missing or invalid"


@pytest.mark.parametrize(("method", "path"), STATE_CHANGING)
async def test_the_session_token_passes_the_csrf_check(
    client: httpx.AsyncClient, admin: AppUser, method: str, path: str
) -> None:
    csrf = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = await client.request(
        method, concrete(path), headers={CSRF_HEADER: csrf}, json={}
    )
    # Unknown ids or an empty body, but never the CSRF refusal.
    assert response.status_code in {204, 404, 422}


async def test_a_token_of_another_session_is_refused(
    client: httpx.AsyncClient, admin: AppUser
) -> None:
    other = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: other})
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path"), sorted(CSRF_EXEMPT))
async def test_the_exempt_routes_need_no_session(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(
        method, path, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code != 403
