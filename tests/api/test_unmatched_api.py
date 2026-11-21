"""unmatched: the queue, assign, create-job and suggest-schedule.

Results are written straight to the table, as the parse hook writes them.
Clients, jobs and names are synthetic (legal R-11: fictional companies).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.models import AppUser, AuditEvent, Client, JobResult, name_key
from app.matcher import Bound
from app.repos.clients import ClientRepository
from app.repos.jobs import JobRepository
from app.repos.results import JobResultRepository
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
FREIGHT = "Example Freight Ltd"
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
    # The job was made with the result's job name as its key, and the hint is
    # the client's name.
    assert binding["match_key_set"] is True
    assert binding["current_match_key"] == ARCHIVE
    assert binding["replaced_match_key"] is None
    assert binding["client_alias_added"] is False
    assert binding["reason"] == "already_known"
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
    assert binding["match_key_set"] is True and binding["client_alias_added"] is False
    assert binding["reason"] == "no_client_hint"
    assert binding["also_bound"] == 1
    stored = (await client.get(f"/api/v1/jobs/{job['id']}/results")).json()["items"]
    assert [item["id"] for item in stored] == [second, first]
    aliases = (await client.get(f"/api/v1/clients/{dental['id']}")).json()["aliases"]
    assert aliases == []
    assert (await client.get("/api/v1/unmatched")).json()["items"] == []


async def matched_job(engine: AsyncEngine, job_name: str, hint: str) -> str | None:
    """The job the matcher binds the next mail with these names to."""
    async with async_sessionmaker(engine)() as db:
        matcher = await JobRepository(db, AllowAllPolicy()).matcher(SYSTEM)
    found = matcher.match(job_name, hint)
    return str(found.job_id) if isinstance(found, Bound) else None


async def test_assign_keeps_another_match_key_unless_told_to_replace_it(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(
        client, csrf, dental["id"], "File backup", match_key="Old tool name"
    )
    first = await add_result(db_engine, clock)
    second = await add_result(db_engine, clock)
    third = await add_result(db_engine, clock)

    kept = await post(client, csrf, f"{first}/assign", {"job_id": job["id"]})
    assert kept.status_code == 200, kept.text
    binding = kept.json()
    assert binding["match_key_set"] is False
    assert binding["current_match_key"] == "Old tool name"
    assert binding["replaced_match_key"] is None
    assert binding["also_bound"] == 0
    stored = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert stored["match_key"] == "Old tool name"
    # The next identical mail would wait in Unmatched again.
    assert await matched_job(db_engine, ARCHIVE, DENTAL) is None

    replace = {"job_id": job["id"], "replace_match_key": True}
    replaced = await post(client, csrf, f"{second}/assign", replace)
    assert replaced.status_code == 200, replaced.text
    binding = replaced.json()
    assert binding["match_key_set"] is True
    assert binding["current_match_key"] == ARCHIVE
    assert binding["replaced_match_key"] == "Old tool name"
    # The third result has the same names and binds with it.
    assert binding["also_bound"] == 1
    bound = (await client.get(f"/api/v1/jobs/{job['id']}/results")).json()
    assert [item["id"] for item in bound["items"]] == [third, second, first]
    assert await matched_job(db_engine, ARCHIVE, DENTAL) == job["id"]
    is_replace = AuditEvent.action == "job.match_key_replaced"
    async with async_sessionmaker(db_engine)() as db:
        (event,) = (await db.scalars(select(AuditEvent).where(is_replace))).all()
    assert (event.target_kind, event.target_id) == ("job", job["id"])
    # Ids only (D-7): job names come from mail and audit outlives a client delete.
    assert event.details == {"result_id": second}


async def test_assign_with_replace_keeps_a_key_of_the_same_words(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(
        client, csrf, dental["id"], "File backup", match_key="weekly-archive copy"
    )
    result_id = await add_result(db_engine, clock)
    replace = {"job_id": job["id"], "replace_match_key": True}
    binding = (await post(client, csrf, f"{result_id}/assign", replace)).json()
    assert binding["match_key_set"] is False
    assert binding["current_match_key"] == "weekly-archive copy"
    assert binding["replaced_match_key"] is None
    assert await matched_job(db_engine, ARCHIVE, DENTAL) == job["id"]


async def test_assign_at_the_alias_limit_says_so(
    client: httpx.AsyncClient,
    csrf: str,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.v1.unmatched.MAX_ALIASES", 1)
    dental = await make_client(client, csrf, DENTAL, aliases=["FDC"])
    job = await make_job(client, csrf, dental["id"], ARCHIVE)
    result_id = await add_result(db_engine, clock, client_hint="FDC Main Office")
    assigned = await post(client, csrf, f"{result_id}/assign", {"job_id": job["id"]})
    assert assigned.status_code == 200, assigned.text
    binding = assigned.json()
    assert binding["client_alias_added"] is False
    assert binding["reason"] == "alias_limit"
    aliases = (await client.get(f"/api/v1/clients/{dental['id']}")).json()["aliases"]
    assert aliases == ["FDC"]


async def test_assign_never_takes_an_alias_or_name_of_another_client(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    freight = await make_client(client, csrf, FREIGHT, aliases=["Shared Office"])
    # Archived or not, the hint must not name two clients.
    archived = await client.post(
        f"/api/v1/clients/{freight['id']}/archive", headers={CSRF_HEADER: csrf}
    )
    assert archived.is_success, archived.text
    job = await make_job(client, csrf, dental["id"], ARCHIVE)
    body = {"job_id": job["id"]}
    for hint in ("shared-office", FREIGHT.upper()):
        result_id = await add_result(db_engine, clock, client_hint=hint)
        assigned = await post(client, csrf, f"{result_id}/assign", body)
        assert assigned.status_code == 200, assigned.text
        binding = assigned.json()
        assert binding["client_alias_added"] is False
        assert binding["reason"] == "alias_of_other_client"
    aliases = (await client.get(f"/api/v1/clients/{dental['id']}")).json()["aliases"]
    assert aliases == []


async def test_assign_keeps_a_binding_made_meanwhile(
    client: httpx.AsyncClient,
    csrf: str,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    archive = await make_job(client, csrf, dental["id"], ARCHIVE)
    other = await make_job(client, csrf, dental["id"], "Other copy")
    first = await add_result(db_engine, clock)
    second = await add_result(db_engine, clock)
    named = JobResultRepository.named

    async def then_bound_elsewhere(*args: Any, **kwargs: Any) -> list[JobResult]:
        # Another user assigns the second result while this request has
        # already read it as unbound.
        found = await named(*args, **kwargs)
        async with async_sessionmaker(db_engine)() as db:
            await db.execute(
                update(JobResult)
                .where(JobResult.id == uuid.UUID(second))
                .values(job_id=uuid.UUID(other["id"]))
            )
            await db.commit()
        return found

    monkeypatch.setattr(JobResultRepository, "named", then_bound_elsewhere)
    assigned = await post(client, csrf, f"{first}/assign", {"job_id": archive["id"]})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["also_bound"] == 0
    kept = (await client.get(f"/api/v1/jobs/{other['id']}/results")).json()["items"]
    assert [item["id"] for item in kept] == [second]
    bound = (await client.get(f"/api/v1/jobs/{archive['id']}/results")).json()
    assert [item["id"] for item in bound["items"]] == [first]


async def job_of(engine: AsyncEngine, result_id: str) -> str | None:
    async with async_sessionmaker(engine)() as db:
        result = await db.get(JobResult, uuid.UUID(result_id))
    assert result is not None
    return None if result.job_id is None else str(result.job_id)


def meet_before_binding_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hold both requests until each holds its own result and is about to bind
    the other's: the order in which two transactions deadlock."""
    both = asyncio.Barrier(2)
    bind_unbound = JobResultRepository.bind_unbound

    async def together(*args: Any, **kwargs: Any) -> list[uuid.UUID | None]:
        async with asyncio.timeout(10):
            await both.wait()
        return await bind_unbound(*args, **kwargs)

    monkeypatch.setattr(JobResultRepository, "bind_unbound", together)


@pytest.fixture
async def second_browser(
    app: FastAPI, client: httpx.AsyncClient, technician: AppUser
) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    """A technician in another browser, for a request beside the admin's."""
    async with another_browser(app) as other:
        yield other, await sign_in(other, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)


async def test_two_concurrent_assigns_never_deadlock(
    client: httpx.AsyncClient,
    csrf: str,
    second_browser: tuple[httpx.AsyncClient, str],
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other, other_csrf = second_browser
    dental = await make_client(client, csrf, DENTAL)
    freight = await make_client(client, csrf, FREIGHT)
    dental_job = await make_job(client, csrf, dental["id"], "Dental copy")
    freight_job = await make_job(client, csrf, freight["id"], "Freight copy")
    # Without a client hint each request is sure the other's result belongs
    # to its own job: the other's new match key is not committed yet.
    first = await add_result(db_engine, clock, client_hint=None)
    second = await add_result(db_engine, clock, client_hint=None)
    meet_before_binding_the_others(monkeypatch)
    answers = await asyncio.gather(
        post(client, csrf, f"{first}/assign", {"job_id": dental_job["id"]}),
        post(other, other_csrf, f"{second}/assign", {"job_id": freight_job["id"]}),
    )
    assert [answer.status_code for answer in answers] == [200, 200]
    assert [answer.json()["also_bound"] for answer in answers] == [0, 0]
    # Each result is bound once, to the job of the request that held it.
    assert await job_of(db_engine, first) == dental_job["id"]
    assert await job_of(db_engine, second) == freight_job["id"]


async def test_a_concurrent_assign_and_create_job_never_deadlock(
    client: httpx.AsyncClient,
    csrf: str,
    second_browser: tuple[httpx.AsyncClient, str],
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other, other_csrf = second_browser
    dental = await make_client(client, csrf, DENTAL)
    freight = await make_client(client, csrf, FREIGHT)
    dental_job = await make_job(client, csrf, dental["id"], "Dental copy")
    first = await add_result(db_engine, clock, client_hint=None)
    second = await add_result(db_engine, clock, client_hint=None)
    meet_before_binding_the_others(monkeypatch)
    create = {"client_id": freight["id"], "name": "Freight copy"}
    assigned, made = await asyncio.gather(
        post(client, csrf, f"{first}/assign", {"job_id": dental_job["id"]}),
        post(other, other_csrf, f"{second}/create-job", create),
    )
    assert assigned.status_code == 200, assigned.text
    assert made.status_code == 201, made.text
    assert await job_of(db_engine, first) == dental_job["id"]
    assert await job_of(db_engine, second) == made.json()["job"]["id"]


async def test_create_job_takes_a_client_created_meanwhile(
    client: httpx.AsyncClient,
    csrf: str,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = await add_result(db_engine, clock)
    find_by_name = ClientRepository.find_by_name
    calls = 0

    async def created_meanwhile(*args: Any, **kwargs: Any) -> Client | None:
        # The first look finds nothing; then another request creates it.
        nonlocal calls
        calls += 1
        if calls == 1:
            async with async_sessionmaker(db_engine)() as db:
                db.add(
                    Client(
                        name=DENTAL,
                        name_key=name_key(DENTAL),
                        notes="",
                        aliases=[],
                        archived=False,
                        created_at=clock.now(),
                    )
                )
                await db.commit()
            return None
        return await find_by_name(*args, **kwargs)

    monkeypatch.setattr(ClientRepository, "find_by_name", created_meanwhile)
    made = await post(client, csrf, f"{result_id}/create-job", {"client_name": DENTAL})
    assert made.status_code == 201, made.text
    assert made.json()["client_created"] is False
    clients = (await client.get("/api/v1/clients")).json()["items"]
    assert [item["name"] for item in clients] == [DENTAL]
