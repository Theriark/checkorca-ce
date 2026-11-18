"""API tokens: shown once, stored as SHA-256, revoked for good; Bearer access."""

import base64
import uuid
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.access import Principal
from app.api.deps import require_token
from app.db.models import ApiToken, AppUser
from app.security.tokens import API_TOKEN_PREFIX, sha256_hex
from helpers import ADMIN_EMAIL, ADMIN_PASSWORD, CSRF_HEADER, FakeClock, sign_in


@pytest.fixture
def token_app(app: FastAPI) -> FastAPI:
    """The app with one test-only route per scope behind require_token."""

    @app.get("/test-only/read")
    async def read_route(
        principal: Annotated[Principal, Depends(require_token("read"))],
    ) -> dict[str, str]:
        return {"kind": principal.kind, "id": str(principal.id)}

    @app.get("/test-only/ingest")
    async def ingest_route(
        principal: Annotated[Principal, Depends(require_token("ingest"))],
    ) -> dict[str, str]:
        return {"kind": principal.kind, "id": str(principal.id)}

    return app


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser, token_app: FastAPI) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def create(client: httpx.AsyncClient, csrf: str, scope: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/tokens",
        json={"label": f"  {scope} script  ", "scope": scope},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 201, response.text
    body: dict[str, str] = response.json()
    return body


async def stored(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        return list((await connection.execute(select(ApiToken))).all())


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


async def test_the_token_is_shown_once_and_stored_as_sha256(
    client: httpx.AsyncClient, csrf: str, admin: AppUser, db_engine: AsyncEngine
) -> None:
    created = await create(client, csrf, "read")
    value = created["token"]
    assert value.startswith(API_TOKEN_PREFIX)
    raw = base64.urlsafe_b64decode(value.removeprefix(API_TOKEN_PREFIX) + "==")
    assert len(raw) == 24
    assert created["label"] == "read script"
    assert created["created_by"] == str(admin.id)

    (row,) = await stored(db_engine)
    assert row.token_sha256 == sha256_hex(value)
    assert value not in str(tuple(row))

    listed = await client.get("/api/v1/tokens")
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
    assert value not in listed.text
    assert row.token_sha256 not in listed.text


async def test_a_token_authenticates_its_scope_until_revoked(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock, db_engine: AsyncEngine
) -> None:
    created = await create(client, csrf, "read")
    value = created["token"]
    answer = await client.get("/test-only/read", headers=bearer(value))
    assert answer.status_code == 200
    assert answer.json() == {"kind": "token", "id": created["id"]}
    (row,) = await stored(db_engine)
    assert row.last_used_at == clock.now()

    wrong_scope = await client.get("/test-only/ingest", headers=bearer(value))
    assert wrong_scope.status_code == 403

    revoked = await client.delete(
        f"/api/v1/tokens/{created['id']}", headers={CSRF_HEADER: csrf}
    )
    assert revoked.status_code == 204
    refused = await client.get("/test-only/read", headers=bearer(value))
    assert refused.status_code == 401
    assert refused.headers["www-authenticate"] == "Bearer"
    (row,) = await stored(db_engine)
    assert row.revoked_at == clock.now()


async def test_revoking_twice_keeps_the_first_time(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock, db_engine: AsyncEngine
) -> None:
    created = await create(client, csrf, "ingest")
    url = f"/api/v1/tokens/{created['id']}"
    first = clock.now()
    assert (await client.delete(url, headers={CSRF_HEADER: csrf})).status_code == 204
    clock.advance(minutes=5)
    assert (await client.delete(url, headers={CSRF_HEADER: csrf})).status_code == 204
    (row,) = await stored(db_engine)
    assert row.revoked_at == first
    listed = (await client.get("/api/v1/tokens")).json()["items"]
    assert listed[0]["revoked_at"] is not None


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Basic synthetic"},
        bearer(API_TOKEN_PREFIX + "unknown"),
    ],
)
async def test_missing_or_unknown_tokens_answer_401(
    client: httpx.AsyncClient, csrf: str, headers: dict[str, str]
) -> None:
    response = await client.get("/test-only/read", headers=headers)
    assert response.status_code == 401


async def test_a_session_cookie_is_not_a_token(
    client: httpx.AsyncClient, csrf: str
) -> None:
    assert (await client.get("/test-only/read")).status_code == 401


async def test_tokens_are_rate_limited(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    value = (await create(client, csrf, "read"))["token"]
    for _ in range(120):
        response = await client.get("/test-only/read", headers=bearer(value))
        assert response.status_code == 200
    limited = await client.get("/test-only/read", headers=bearer(value))
    assert limited.status_code == 429
    clock.advance(seconds=1)
    assert (await client.get("/test-only/read", headers=bearer(value))).is_success


async def test_tokens_page_with_a_cursor(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    ids = []
    for scope in ("read", "ingest", "read"):
        ids.append((await create(client, csrf, scope))["id"])
        clock.advance(seconds=1)
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = (await client.get("/api/v1/tokens", params=params)).json()
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == ids


async def test_unknown_tokens_and_bad_bodies(
    client: httpx.AsyncClient, csrf: str
) -> None:
    missing = await client.delete(
        f"/api/v1/tokens/{uuid.uuid4()}", headers={CSRF_HEADER: csrf}
    )
    assert missing.status_code == 404
    for body in ({"label": " ", "scope": "read"}, {"label": "x", "scope": "admin"}):
        response = await client.post(
            "/api/v1/tokens", json=body, headers={CSRF_HEADER: csrf}
        )
        assert response.status_code == 422
