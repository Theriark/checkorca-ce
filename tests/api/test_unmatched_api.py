"""unmatched: the queue, assign, create-job and suggest-schedule.

Results are written straight to the table, as the parse hook writes them.
Clients, jobs and names are synthetic (legal R-11: fictional companies).
"""

import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models import AppUser, JobResult
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    another_browser,
    make_client,
    make_job,
    sign_in,
)

DENTAL = "Fictional Dental Clinic"
ARCHIVE = "Weekly archive copy"


async def add_result(
    engine: AsyncEngine,
    clock: FakeClock,
    job_name: str | None = ARCHIVE,
    client_hint: str | None = DENTAL,
    **times: datetime,
) -> str:
    result = JobResult(
        id=uuid.uuid4(),
        job_id=None,
        job_name=job_name,
        client_hint=client_hint,
        status="failed",
        received_at=clock.now(),
        details={},
        **times,
    )
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        db.add(result)
        await db.commit()
    clock.advance(seconds=1)
    return str(result.id)


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def post(
    client: httpx.AsyncClient, csrf: str, path: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/unmatched/{path}", json=body, headers={CSRF_HEADER: csrf}
    )


async def test_the_queue_lists_unbound_results_newest_first(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    ids = [await add_result(db_engine, clock, f"Job {number}") for number in range(3)]
    first = (await client.get("/api/v1/unmatched", params={"limit": 2})).json()
    assert [item["result_id"] for item in first["items"]] == ids[:0:-1]
    item = first["items"][0]
    assert (item["job_name"], item["client_hint"], item["status"]) == (
        "Job 2",
        DENTAL,
        "failed",
    )
    assert item["raw_message_id"] is None
    rest = await client.get(
        "/api/v1/unmatched", params={"limit": 2, "cursor": first["next_cursor"]}
    )
    assert [item["result_id"] for item in rest.json()["items"]] == ids[:1]
    assert rest.json()["next_cursor"] is None


async def test_a_read_token_lists_the_queue(
    app: FastAPI, client: httpx.AsyncClient, csrf: str
) -> None:
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "dashboard", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    token = created.json()["token"]
    async with another_browser(app) as anonymous:
        listed = await anonymous.get(
            "/api/v1/unmatched", headers={"Authorization": f"Bearer {token}"}
        )
        assert listed.status_code == 200
        assert (await anonymous.get("/api/v1/unmatched")).status_code == 401


def finished(text: str) -> dict[str, datetime]:
    return {"finished_at": datetime.fromisoformat(text)}


async def test_suggest_schedule_takes_the_median_of_the_same_names(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    # 23:00 in Lisbon on both sides of the spring change (28 March 2027).
    for at in ("2027-03-26T23:00:00Z", "2027-03-28T22:04:00Z"):
        await add_result(db_engine, clock, **finished(at))
    # Other names are not counted.
    early = finished("2027-03-27T05:00:00Z")
    await add_result(db_engine, clock, "Other job", **early)
    await add_result(db_engine, clock, ARCHIVE, None, **early)
    last = await add_result(
        db_engine,
        clock,
        ARCHIVE.upper(),
        DENTAL.lower(),
        **finished("2027-03-29T22:02:00Z"),
    )
    response = await client.get(f"/api/v1/unmatched/{last}/suggest-schedule")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "daily",
        "expr": "23:00",
        "timezone": "Europe/Lisbon",
        "basis": "finished",
        "results": 3,
    }
    utc = await client.get(
        f"/api/v1/unmatched/{last}/suggest-schedule", params={"timezone": "UTC"}
    )
    assert utc.json()["expr"] == "22:00" and utc.json()["timezone"] == "UTC"


async def test_suggest_schedule_needs_three_runs_and_a_known_zone(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    await add_result(db_engine, clock)
    alone = await add_result(db_engine, clock)
    few = await client.get(f"/api/v1/unmatched/{alone}/suggest-schedule")
    assert few.status_code == 422
    assert few.json()["title"] == "Too few results"
    assert "2 found" in few.json()["detail"]
    zone = await client.get(
        f"/api/v1/unmatched/{alone}/suggest-schedule",
        params={"timezone": "Mars/Olympus"},
    )
    assert zone.status_code == 422 and zone.json()["title"] == "Invalid time zone"
    unknown = await client.get(f"/api/v1/unmatched/{uuid.uuid4()}/suggest-schedule")
    assert unknown.status_code == 404


async def test_create_job_with_a_schedule_for_an_existing_client(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    result_id = await add_result(db_engine, clock)
    body = {
        "client_id": dental["id"],
        "name": "Archive copy",
        "kind": "other",
        "schedule_kind": "cron",
        "schedule_expr": "30 4 * * 1",
        "timezone": "Europe/London",
        "grace_minutes": 30,
    }
    made = await post(client, csrf, f"{result_id}/create-job", body)
    assert made.status_code == 201, made.text
    created = made.json()
    job = created["job"]
    assert (job["name"], job["kind"], job["client_id"]) == (
        "Archive copy",
        "other",
        dental["id"],
    )
    assert (job["schedule_kind"], job["schedule_expr"], job["timezone"]) == (
        "cron",
        "30 4 * * 1",
        "Europe/London",
    )
    assert job["grace_minutes"] == 30 and job["match_key"] == ARCHIVE
    assert created["client_created"] is False
    binding = created["binding"]
    assert binding["result_id"] == result_id and binding["job_id"] == job["id"]
    # The job was made with the key, and the hint is the client's name.
    assert binding["match_key_set"] is False and binding["alias_added"] is False
    assert (await client.get("/api/v1/unmatched")).json()["items"] == []
    again = await post(client, csrf, f"{result_id}/create-job", body)
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "body"),
        ({"client_id": str(uuid.uuid4()), "client_name": DENTAL}, "body"),
        ({"client_name": DENTAL, "schedule_kind": "daily"}, "body"),
        ({"client_name": DENTAL, "unknown": 1}, "body.unknown"),
    ],
)
async def test_create_job_checks_its_body(
    client: httpx.AsyncClient,
    csrf: str,
    db_engine: AsyncEngine,
    clock: FakeClock,
    body: dict[str, Any],
    field: str,
) -> None:
    result_id = await add_result(db_engine, clock)
    response = await post(client, csrf, f"{result_id}/create-job", body)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


async def test_create_job_refusals(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    await make_job(client, csrf, dental["id"], ARCHIVE)
    named = await add_result(db_engine, clock)
    nameless = await add_result(db_engine, clock, job_name=None)
    by_name = {"client_name": DENTAL}
    taken = await post(client, csrf, f"{named}/create-job", by_name)
    assert taken.status_code == 409 and taken.json()["title"] == "Job name taken"
    no_name = await post(client, csrf, f"{nameless}/create-job", by_name)
    assert no_name.status_code == 422
    assert no_name.json()["errors"][0]["field"] == "body.name"
    unknown_client = await post(
        client, csrf, f"{named}/create-job", {"client_id": str(uuid.uuid4())}
    )
    assert unknown_client.status_code == 422
    bad_schedule = await post(
        client,
        csrf,
        f"{named}/create-job",
        {
            "client_name": DENTAL,
            "name": "Other",
            "schedule_kind": "cron",
            "schedule_expr": "not a cron",
        },
    )
    assert bad_schedule.status_code == 422
    unknown_result = await post(client, csrf, f"{uuid.uuid4()}/create-job", by_name)
    assert unknown_result.status_code == 404
    # Nothing was created along the way.
    jobs = (await client.get("/api/v1/jobs")).json()["items"]
    assert [job["name"] for job in jobs] == [ARCHIVE]


async def test_assign_refusals(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    result_id = await add_result(db_engine, clock)
    unknown_job = await post(
        client, csrf, f"{result_id}/assign", {"job_id": str(uuid.uuid4())}
    )
    assert unknown_job.status_code == 422
    assert unknown_job.json()["errors"][0]["field"] == "body.job_id"
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    unknown_result = await post(
        client, csrf, f"{uuid.uuid4()}/assign", {"job_id": job["id"]}
    )
    assert unknown_result.status_code == 404


async def test_a_technician_works_the_queue(
    client: httpx.AsyncClient,
    admin: AppUser,
    technician: AppUser,
    db_engine: AsyncEngine,
    clock: FakeClock,
) -> None:
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "Archive copy")
    first = await add_result(db_engine, clock, client_hint=None)
    second = await add_result(db_engine, clock, client_hint=None)
    # Results without a hint stay clear of the client's aliases.
    assigned = await post(client, csrf, f"{first}/assign", {"job_id": job["id"]})
    assert assigned.status_code == 200, assigned.text
    binding = assigned.json()
    assert binding["match_key_set"] is True and binding["alias_added"] is False
    assert binding["also_bound"] == 1
    stored = (await client.get(f"/api/v1/jobs/{job['id']}/results")).json()["items"]
    assert [item["id"] for item in stored] == [second, first]
    aliases = (await client.get(f"/api/v1/clients/{dental['id']}")).json()["aliases"]
    assert aliases == []
    assert (await client.get("/api/v1/unmatched")).json()["items"] == []
