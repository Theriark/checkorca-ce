"""clients: create, list, search, change, archive; both roles; read tokens."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AppUser, AuditEvent
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    another_browser,
    make_client,
    make_job,
    sign_in,
)

DENTAL, FREIGHT, LAW = CLIENT_NAMES


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def audit_actions(engine: AsyncEngine) -> list[tuple[str, str | None]]:
    query = select(AuditEvent.action, AuditEvent.target_id)
    async with engine.connect() as connection:
        return [tuple(row) for row in (await connection.execute(query)).all()]


async def test_create_and_get_a_client(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock, db_engine: AsyncEngine
) -> None:
    created = await make_client(
        client,
        csrf,
        "  Fictional   Dental Clinic ",
        notes="Synthetic test client.",
        aliases=["FDC", "fdc", "Dental"],
    )
    assert created["name"] == DENTAL
    assert created["aliases"] == ["FDC", "Dental"]
    assert created["archived"] is False
    assert created["job_count"] == 0
    assert created["status_counts"] == {}
    assert created["worst_state"] is None
    assert created["created_at"] == "2027-01-04T09:00:00Z"
    fetched = await client.get(f"/api/v1/clients/{created['id']}")
    assert fetched.json() == created
    assert await audit_actions(db_engine) == [("client.create", created["id"])]


async def test_names_are_unique_ignoring_case_and_spaces(
    client: httpx.AsyncClient, csrf: str
) -> None:
    await make_client(client, csrf, DENTAL)
    again = await client.post(
        "/api/v1/clients",
        json={"name": "fictional  DENTAL clinic"},
        headers={CSRF_HEADER: csrf},
    )
    assert again.status_code == 409
    assert again.headers["content-type"] == "application/problem+json"
    other = await make_client(client, csrf, FREIGHT)
    renamed = await client.patch(
        f"/api/v1/clients/{other['id']}",
        json={"name": DENTAL.upper()},
        headers={CSRF_HEADER: csrf},
    )
    assert renamed.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 201},
        {"name": "Bell\x07 Company"},
        {"name": DENTAL, "unknown": 1},
        {"name": DENTAL, "aliases": ["a"] * 51},
        {"name": DENTAL, "notes": "n" * 4001},
    ],
)
async def test_invalid_clients_are_refused(
    client: httpx.AsyncClient, csrf: str, body: dict[str, object]
) -> None:
    response = await client.post(
        "/api/v1/clients", json=body, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 422


async def test_list_search_and_pages(client: httpx.AsyncClient, csrf: str) -> None:
    for name in (LAW, DENTAL, FREIGHT):
        await make_client(client, csrf, name, aliases=[f"{name[:3]} alias"])
    listed = (await client.get("/api/v1/clients")).json()
    assert [item["name"] for item in listed["items"]] == [FREIGHT, DENTAL, LAW]
    assert listed["next_cursor"] is None

    first = (await client.get("/api/v1/clients", params={"limit": 2})).json()
    assert [item["name"] for item in first["items"]] == [FREIGHT, DENTAL]
    second = await client.get(
        "/api/v1/clients", params={"limit": 2, "cursor": first["next_cursor"]}
    )
    assert [item["name"] for item in second.json()["items"]] == [LAW]
    assert second.json()["next_cursor"] is None

    by_name = await client.get("/api/v1/clients", params={"q": "freight"})
    assert [item["name"] for item in by_name.json()["items"]] == [FREIGHT]
    by_alias = await client.get("/api/v1/clients", params={"q": "SAM ALIAS"})
    assert [item["name"] for item in by_alias.json()["items"]] == [LAW]
    # LIKE wildcards are plain characters.
    wildcard = await client.get("/api/v1/clients", params={"q": "%"})
    assert wildcard.json()["items"] == []
    bad = await client.get("/api/v1/clients", params={"cursor": "not-a-cursor"})
    assert bad.status_code == 400


async def test_archive_hides_and_patch_restores(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    created = await make_client(client, csrf, DENTAL)
    url = f"/api/v1/clients/{created['id']}"
    archived = await client.post(f"{url}/archive", headers={CSRF_HEADER: csrf})
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert (await client.get("/api/v1/clients")).json()["items"] == []
    only_archived = await client.get("/api/v1/clients", params={"archived": True})
    assert [item["id"] for item in only_archived.json()["items"]] == [created["id"]]

    restored = await client.patch(
        url, json={"archived": False, "notes": "Back."}, headers={CSRF_HEADER: csrf}
    )
    assert restored.json()["archived"] is False
    assert restored.json()["notes"] == "Back."
    # Sending the stored values again changes and audits nothing.
    same = await client.patch(url, json={"notes": "Back."}, headers={CSRF_HEADER: csrf})
    assert same.status_code == 200
    actions = sorted(action for action, _ in await audit_actions(db_engine))
    assert actions == ["client.archive", "client.create", "client.update"]


async def test_job_counts_by_state(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    created = await make_client(client, csrf, DENTAL)
    await make_job(client, csrf, created["id"], "Nightly server backup")
    paused = await make_job(client, csrf, created["id"], "Weekly image backup")
    archived = await make_job(client, csrf, created["id"], "Old NAS backup")
    headers = {CSRF_HEADER: csrf}
    await client.post(f"/api/v1/jobs/{paused['id']}/pause", headers=headers)
    await client.post(f"/api/v1/jobs/{archived['id']}/archive", headers=headers)
    described = (await client.get(f"/api/v1/clients/{created['id']}")).json()
    assert described["job_count"] == 2
    assert described["status_counts"] == {"unknown": 1, "paused": 1}
    assert described["worst_state"] == "unknown"


async def test_a_technician_manages_clients_too(
    client: httpx.AsyncClient, technician: AppUser
) -> None:
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    created = await make_client(client, csrf, FREIGHT)
    changed = await client.patch(
        f"/api/v1/clients/{created['id']}",
        json={"notes": "Changed by the technician."},
        headers={CSRF_HEADER: csrf},
    )
    assert changed.status_code == 200
    deleted = await client.delete(
        f"/api/v1/clients/{created['id']}",
        params={"confirm_name": FREIGHT},
        headers={CSRF_HEADER: csrf},
    )
    assert deleted.status_code == 204


async def test_anonymous_requests_are_refused(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/clients")).status_code == 401
    created = await client.post("/api/v1/clients", json={"name": DENTAL})
    assert created.status_code == 401


async def test_a_read_token_lists_but_cannot_change(
    app: FastAPI, client: httpx.AsyncClient, csrf: str
) -> None:
    created = await make_client(client, csrf, DENTAL)
    token = await client.post(
        "/api/v1/tokens",
        json={"label": "synthetic reader", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    ingest = await client.post(
        "/api/v1/tokens",
        json={"label": "synthetic ingest", "scope": "ingest"},
        headers={CSRF_HEADER: csrf},
    )
    async with another_browser(app) as script:
        reader = {"Authorization": f"Bearer {token.json()['token']}"}
        listed = await script.get("/api/v1/clients", headers=reader)
        assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
        one = await script.get(f"/api/v1/clients/{created['id']}", headers=reader)
        assert one.status_code == 200
        wrong = {"Authorization": f"Bearer {ingest.json()['token']}"}
        assert (await script.get("/api/v1/clients", headers=wrong)).status_code == 403
        change = await script.post(
            "/api/v1/clients", json={"name": FREIGHT}, headers=reader
        )
        assert change.status_code == 401


async def test_unknown_clients_answer_404(client: httpx.AsyncClient, csrf: str) -> None:
    missing = "/api/v1/clients/00000000-0000-4000-8000-000000000000"
    assert (await client.get(missing)).status_code == 404
    patched = await client.patch(missing, json={}, headers={CSRF_HEADER: csrf})
    assert patched.status_code == 404
