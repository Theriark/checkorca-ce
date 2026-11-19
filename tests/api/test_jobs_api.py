"""jobs: create with the plan's defaults, schedule checks, pause and resume,
archive, filters, changes and moves."""

import re
from typing import Any

import httpx
import pytest
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
    make_client,
    make_job,
    sign_in,
)

DENTAL, FREIGHT, LAW = CLIENT_NAMES


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
async def dental(client: httpx.AsyncClient, csrf: str) -> dict[str, Any]:
    return await make_client(client, csrf, DENTAL)


async def test_a_new_job_takes_the_plan_defaults(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    job = await make_job(client, csrf, dental["id"], "  Nightly   server backup ")
    assert job["name"] == "Nightly server backup"
    assert job["client_id"] == dental["id"]
    assert job["client_name"] == DENTAL
    assert job["kind"] == "backup"
    assert (job["schedule_kind"], job["schedule_expr"], job["timezone"]) == (
        "daily",
        "23:00",
        "Europe/Lisbon",
    )
    assert job["max_runtime_minutes"] == 360
    assert job["grace_minutes"] == 120
    assert job["escalate_minutes"] == 30
    assert job["attribution_basis"] == "finished"
    assert job["warning_policy"] == "warning_is_attention"
    assert job["consecutive_failures_to_alert"] == 1
    assert job["enabled"] is True
    assert job["paused_until"] is None
    assert job["archived"] is False
    assert job["state"] == "unknown"
    assert job["state_since"] is None
    assert job["last_success_at"] is None
    assert job["acknowledged_at"] is None
    assert re.fullmatch(
        r"http://localhost:8080/api/v1/ping/[A-Za-z0-9]{24}", job["ping_url"]
    )
    fetched = await client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.json() == job


async def test_ping_tokens_differ(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    urls = {
        (await make_job(client, csrf, dental["id"], f"Job {number}"))["ping_url"]
        for number in range(5)
    }
    assert len(urls) == 5


async def test_the_schedule_is_stored_in_its_normal_form(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    job = await make_job(
        client,
        csrf,
        dental["id"],
        "Log rotation script",
        kind="script",
        schedule_kind="cron",
        schedule_expr=" 15   2 * * 1-5 ",
        timezone="America/New_York",
        match_key="logrotate",
        parser_pack_id="generic-keywords",
    )
    assert job["schedule_expr"] == "15 2 * * 1-5"
    assert job["match_key"] == "logrotate"
    assert job["parser_pack_id"] == "generic-keywords"


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"schedule_kind": "cron", "schedule_expr": "61 * * * *"}, "schedule_expr"),
        ({"schedule_kind": "cron", "schedule_expr": "0 0 30 2 *"}, "schedule_expr"),
        ({"schedule_kind": "daily", "schedule_expr": "7pm"}, "schedule_expr"),
        ({"schedule_kind": "interval", "schedule_expr": "0m"}, "schedule_expr"),
        ({"timezone": "Mars/Olympus_Mons"}, "timezone"),
    ],
)
async def test_an_unusable_schedule_names_the_field(
    client: httpx.AsyncClient,
    csrf: str,
    dental: dict[str, Any],
    fields: dict[str, str],
    field: str,
) -> None:
    body = {
        "client_id": dental["id"],
        "name": "Broken schedule",
        "schedule_kind": "daily",
        "schedule_expr": "23:00",
        "timezone": "Europe/Lisbon",
        **fields,
    }
    response = await client.post("/api/v1/jobs", json=body, headers={CSRF_HEADER: csrf})
    assert response.status_code == 422
    problem = response.json()
    assert problem["title"] == "Invalid schedule"
    assert problem["errors"][0]["field"] == f"body.{field}"
    assert problem["errors"][0]["message"] == problem["detail"]


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "database"},
        {"max_runtime_minutes": 0},
        {"grace_minutes": -1},
        {"escalate_minutes": 10081},
        {"consecutive_failures_to_alert": 0},
        {"attribution_basis": "sent"},
        {"warning_policy": "ignore"},
        {"parser_pack_id": "Not A Pack"},
        {"schedule_kind": "weekly"},
    ],
)
async def test_invalid_settings_are_refused(
    client: httpx.AsyncClient,
    csrf: str,
    dental: dict[str, Any],
    fields: dict[str, object],
) -> None:
    body = {
        "client_id": dental["id"],
        "name": "Invalid",
        "schedule_kind": "daily",
        "schedule_expr": "23:00",
        "timezone": "UTC",
        **fields,
    }
    response = await client.post("/api/v1/jobs", json=body, headers={CSRF_HEADER: csrf})
    assert response.status_code == 422


async def test_a_job_needs_an_existing_client_and_a_free_name(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    body = {
        "client_id": "00000000-0000-4000-8000-000000000000",
        "name": "Orphan",
        "schedule_kind": "daily",
        "schedule_expr": "23:00",
        "timezone": "UTC",
    }
    orphan = await client.post("/api/v1/jobs", json=body, headers={CSRF_HEADER: csrf})
    assert orphan.status_code == 422
    assert orphan.json()["errors"][0]["field"] == "body.client_id"
    await make_job(client, csrf, dental["id"], "Nightly server backup")
    twice = await client.post(
        "/api/v1/jobs",
        json={**body, "client_id": dental["id"], "name": "NIGHTLY server backup"},
        headers={CSRF_HEADER: csrf},
    )
    assert twice.status_code == 409


async def test_pause_and_resume(
    client: httpx.AsyncClient,
    csrf: str,
    dental: dict[str, Any],
    clock: FakeClock,
    db_engine: AsyncEngine,
) -> None:
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    url = f"/api/v1/jobs/{job['id']}"
    headers = {CSRF_HEADER: csrf}
    paused = (await client.post(f"{url}/pause", headers=headers)).json()
    assert (paused["state"], paused["enabled"], paused["paused_until"]) == (
        "paused",
        False,
        None,
    )
    resumed = (await client.post(f"{url}/resume", headers=headers)).json()
    assert (resumed["state"], resumed["enabled"]) == ("unknown", True)

    until = await client.post(
        f"{url}/pause", json={"until": "2027-01-04T12:00:00+01:00"}, headers=headers
    )
    assert until.json()["paused_until"] == "2027-01-04T11:00:00Z"
    assert until.json()["enabled"] is True
    assert until.json()["state"] == "paused"
    clock.advance(hours=2, minutes=1)
    assert (await client.get(url)).json()["state"] == "unknown"

    past = await client.post(
        f"{url}/pause", json={"until": "2027-01-04T08:00:00Z"}, headers=headers
    )
    assert past.status_code == 422
    assert past.json()["errors"][0]["field"] == "body.until"
    naive = await client.post(
        f"{url}/pause", json={"until": "2027-01-05T08:00:00"}, headers=headers
    )
    assert naive.status_code == 422

    async with db_engine.connect() as connection:
        actions = (await connection.execute(select(AuditEvent.action))).scalars()
        assert sorted(actions) == ["job.create", "job.pause", "job.pause", "job.resume"]


async def test_archive_and_filters(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    freight = await make_client(client, csrf, FREIGHT)
    nightly = await make_job(client, csrf, dental["id"], "Nightly server backup")
    script = await make_job(
        client, csrf, freight["id"], "Disk check script", kind="script"
    )
    paused = await make_job(
        client, csrf, freight["id"], "Weekly NAS backup", parser_pack_id="veeam-br"
    )
    old = await make_job(client, csrf, dental["id"], "Old tape backup")
    headers = {CSRF_HEADER: csrf}
    await client.post(f"/api/v1/jobs/{paused['id']}/pause", headers=headers)
    archived = await client.post(f"/api/v1/jobs/{old['id']}/archive", headers=headers)
    assert archived.json()["archived"] is True

    async def names(**params: object) -> list[str]:
        response = await client.get("/api/v1/jobs", params=params)
        assert response.status_code == 200, response.text
        return [item["name"] for item in response.json()["items"]]

    assert await names() == [script["name"], nightly["name"], paused["name"]]
    assert await names(client_id=freight["id"]) == [script["name"], paused["name"]]
    assert await names(kind="script") == [script["name"]]
    assert await names(pack="veeam-br") == [paused["name"]]
    assert await names(state="paused") == [paused["name"]]
    assert await names(state="unknown") == [script["name"], nightly["name"]]
    assert await names(state="missed") == []
    assert await names(q="BACKUP") == [nightly["name"], paused["name"]]
    assert await names(archived=True) == [old["name"]]
    first = (await client.get("/api/v1/jobs", params={"limit": 1})).json()
    rest = await client.get(
        "/api/v1/jobs", params={"limit": 5, "cursor": first["next_cursor"]}
    )
    assert [item["name"] for item in rest.json()["items"]] == [
        nightly["name"],
        paused["name"],
    ]
    restored = await client.patch(
        f"/api/v1/jobs/{old['id']}", json={"archived": False}, headers=headers
    )
    assert restored.json()["archived"] is False


async def test_change_a_job(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    job = await make_job(
        client, csrf, dental["id"], "Nightly server backup", match_key="srv01"
    )
    url = f"/api/v1/jobs/{job['id']}"
    headers = {CSRF_HEADER: csrf}
    changed = await client.patch(
        url,
        json={
            "schedule_kind": "cron",
            "schedule_expr": "30   1 * * *",
            "grace_minutes": 60,
            "match_key": None,
            "name": None,
        },
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["schedule_kind"], body["schedule_expr"]) == ("cron", "30 1 * * *")
    assert body["timezone"] == "Europe/Lisbon"
    assert body["grace_minutes"] == 60
    assert body["match_key"] is None
    assert body["name"] == job["name"]
    assert body["ping_url"] == job["ping_url"]

    bad = await client.patch(url, json={"timezone": "Nowhere/City"}, headers=headers)
    assert bad.status_code == 422
    assert bad.json()["errors"][0]["field"] == "body.timezone"
    interval = await client.patch(
        url,
        json={"schedule_kind": "interval", "schedule_expr": "6H"},
        headers=headers,
    )
    assert interval.json()["schedule_expr"] == "6h"


async def test_move_a_job_to_another_client(
    client: httpx.AsyncClient, csrf: str, dental: dict[str, Any]
) -> None:
    freight = await make_client(client, csrf, FREIGHT)
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    await make_job(client, csrf, freight["id"], "Nightly server backup")
    headers = {CSRF_HEADER: csrf}
    url = f"/api/v1/jobs/{job['id']}"
    clash = await client.patch(url, json={"client_id": freight["id"]}, headers=headers)
    assert clash.status_code == 409
    moved = await client.patch(
        url,
        json={"client_id": freight["id"], "name": "Nightly server backup 2"},
        headers=headers,
    )
    assert moved.status_code == 200
    assert moved.json()["client_name"] == FREIGHT
    missing = await client.patch(
        url,
        json={"client_id": "00000000-0000-4000-8000-000000000000"},
        headers=headers,
    )
    assert missing.status_code == 422


async def test_a_technician_runs_jobs_end_to_end(
    client: httpx.AsyncClient, technician: AppUser
) -> None:
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    created = await make_client(client, csrf, LAW)
    job = await make_job(client, csrf, created["id"], "Document server backup")
    headers = {CSRF_HEADER: csrf}
    for action in ("pause", "resume", "archive"):
        response = await client.post(
            f"/api/v1/jobs/{job['id']}/{action}", headers=headers
        )
        assert response.status_code == 200


async def test_unknown_jobs_answer_404(client: httpx.AsyncClient, csrf: str) -> None:
    missing = "/api/v1/jobs/00000000-0000-4000-8000-000000000000"
    assert (await client.get(missing)).status_code == 404
    headers = {CSRF_HEADER: csrf}
    assert (await client.post(f"{missing}/pause", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/jobs/not-a-uuid")).status_code == 422
