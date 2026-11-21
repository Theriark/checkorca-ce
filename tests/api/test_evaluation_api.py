"""jobs/{id}/occurrences and flips, and the job state the evaluator keeps
(phase C7), through the API with the worker's hook on the same fake clock.

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AppUser, Flip, JobStateRecord, Occurrence
from app.evaluator.tick import evaluate_jobs
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    FakeClock,
    make_client,
    make_job,
    sign_in,
)

DENTAL, FREIGHT, _ = CLIENT_NAMES
NIGHTLY = "Nightly server backup"
OCCURRENCE_FIELDS = {
    "job_id",
    "scheduled_for",
    "deadline",
    "state",
    "result_id",
    "note",
}
FLIP_FIELDS = {"id", "job_id", "client_id", "from_state", "to_state", "reason", "at"}
# FakeClock starts at 2027-01-04 09:00Z; a daily 23:00 Lisbon job made then is
# overdue at 07:00Z the next morning and missed from 07:30Z.
NIGHT = "2027-01-04T23:00:00Z"
MISSED_AT = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)
STEP = timedelta(hours=11)


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
async def worker(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


async def at(client: httpx.AsyncClient, clock: FakeClock, moment: datetime) -> None:
    """Moves the clock to moment, using the session at least every 11 hours so
    the 12-hour idle limit never signs the test out."""
    while moment - clock.now() > STEP:
        clock.advance(seconds=STEP.total_seconds())
        assert (await client.get("/api/v1/auth/me")).status_code == 200
    clock.advance(seconds=(moment - clock.now()).total_seconds())


async def tick(worker: WorkerContext, clock: FakeClock) -> None:
    await evaluate_jobs(worker, clock.now())


async def nightly_job(client: httpx.AsyncClient, csrf: str) -> dict[str, Any]:
    dental = await make_client(client, csrf, DENTAL)
    return await make_job(client, csrf, dental["id"], NIGHTLY)


async def test_a_silent_night_shows_as_missed_with_one_flip(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    job = await nightly_job(client, csrf)
    await at(client, clock, MISSED_AT - timedelta(minutes=30))
    await tick(worker, clock)
    url = f"/api/v1/jobs/{job['id']}/occurrences"
    (night, tonight) = (await client.get(url)).json()["items"]
    assert set(night) == OCCURRENCE_FIELDS
    assert (night["scheduled_for"], night["state"]) == (NIGHT, "overdue")
    assert night["deadline"] == "2027-01-05T07:00:00Z"
    # Tonight's run is not written yet; the list shows it as pending.
    assert (tonight["scheduled_for"], tonight["state"]) == (
        "2027-01-05T23:00:00Z",
        "pending",
    )
    assert (await client.get("/api/v1/flips")).json()["items"] == []

    await at(client, clock, MISSED_AT)
    await tick(worker, clock)
    night = (await client.get(url)).json()["items"][0]
    assert night == {
        "job_id": job["id"],
        "scheduled_for": NIGHT,
        "deadline": "2027-01-05T07:00:00Z",
        "state": "missed",
        "result_id": None,
        "note": None,
    }
    (flip,) = (await client.get("/api/v1/flips")).json()["items"]
    assert set(flip) == FLIP_FIELDS
    assert (flip["job_id"], flip["client_id"]) == (job["id"], job["client_id"])
    assert (flip["from_state"], flip["to_state"]) == ("unknown", "missed")
    assert flip["at"] == "2027-01-05T07:30:00Z"
    assert "was missed" in flip["reason"]

    shown = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert (shown["state"], shown["state_since"]) == ("missed", "2027-01-05T07:30:00Z")
    assert shown["last_success_at"] is None
    listed = (await client.get("/api/v1/jobs", params={"state": "missed"})).json()
    assert [item["id"] for item in listed["items"]] == [job["id"]]
    assert listed["items"][0]["state"] == "missed"
    unknown = (await client.get("/api/v1/jobs", params={"state": "unknown"})).json()
    assert unknown["items"] == []
    described = (await client.get(f"/api/v1/clients/{job['client_id']}")).json()
    assert described["status_counts"] == {"missed": 1}
    assert described["worst_state"] == "missed"


async def test_a_late_ping_gives_verified_and_one_recovery_flip(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    job = await nightly_job(client, csrf)
    await at(client, clock, MISSED_AT)
    await tick(worker, clock)
    clock.advance(hours=2)
    path = "/api/v1/ping/" + str(job["ping_url"]).rsplit("/", 1)[1]
    assert (await client.get(path + "/start")).status_code == 200
    clock.advance(minutes=20)
    assert (await client.get(path)).status_code == 200
    await tick(worker, clock)

    url = f"/api/v1/jobs/{job['id']}/occurrences"
    night = (await client.get(url)).json()["items"][0]
    assert (night["state"], night["note"]) == ("verified", "late result")
    assert night["result_id"] is not None
    flips = (await client.get("/api/v1/flips")).json()["items"]
    # Newest first: one recovery after the missed night.
    assert [(flip["from_state"], flip["to_state"]) for flip in flips] == [
        ("missed", "ok"),
        ("unknown", "missed"),
    ]
    assert flips[0]["reason"].startswith("Recovered: the run due " + NIGHT)
    shown = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert shown["state"] == "ok"
    assert shown["last_success_at"] == "2027-01-05T09:50:00Z"


async def test_flips_filter_by_job_client_and_time(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    freight = await make_client(client, csrf, FREIGHT)
    first = await make_job(client, csrf, dental["id"], NIGHTLY)
    second = await make_job(client, csrf, freight["id"], NIGHTLY, schedule_expr="22:00")
    await at(client, clock, MISSED_AT)
    await tick(worker, clock)
    every = (await client.get("/api/v1/flips")).json()["items"]
    assert {flip["job_id"] for flip in every} == {first["id"], second["id"]}
    by_job = await client.get("/api/v1/flips", params={"job_id": second["id"]})
    assert [flip["job_id"] for flip in by_job.json()["items"]] == [second["id"]]
    by_client = await client.get("/api/v1/flips", params={"client_id": dental["id"]})
    assert [flip["job_id"] for flip in by_client.json()["items"]] == [first["id"]]
    later = await client.get("/api/v1/flips", params={"since": "2027-01-05T07:31:00Z"})
    assert later.json()["items"] == []
    page = await client.get("/api/v1/flips", params={"limit": 1})
    assert len(page.json()["items"]) == 1
    rest = await client.get(
        "/api/v1/flips", params={"limit": 1, "cursor": page.json()["next_cursor"]}
    )
    assert rest.json()["next_cursor"] is None
    seen = {page.json()["items"][0]["id"], rest.json()["items"][0]["id"]}
    assert seen == {flip["id"] for flip in every}
    naive = await client.get("/api/v1/flips", params={"since": "2027-01-05T07:00:00"})
    assert naive.status_code == 422
    broken = await client.get("/api/v1/flips", params={"cursor": "not-a-cursor"})
    assert broken.status_code == 400


async def test_occurrences_take_a_range_and_pages(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    job = await nightly_job(client, csrf)
    await at(client, clock, MISSED_AT + timedelta(days=2))
    await tick(worker, clock)
    url = f"/api/v1/jobs/{job['id']}/occurrences"
    window = {"from": "2027-01-04T00:00:00Z", "to": "2027-01-10T00:00:00Z"}
    every = (await client.get(url, params=window)).json()
    times = [item["scheduled_for"] for item in every["items"]]
    assert times == [f"2027-01-{day:02d}T23:00:00Z" for day in range(4, 10)]
    states = [item["state"] for item in every["items"]]
    assert states == ["missed", "missed", "missed", "pending", "pending", "pending"]
    first = (await client.get(url, params=window | {"limit": 4})).json()
    assert len(first["items"]) == 4 and first["next_cursor"] is not None
    rest = await client.get(
        url, params=window | {"limit": 4, "cursor": first["next_cursor"]}
    )
    assert [item["scheduled_for"] for item in rest.json()["items"]] == times[4:]
    assert rest.json()["next_cursor"] is None
    only = await client.get(
        url, params={"from": "2027-01-05T00:00:00Z", "to": "2027-01-06T00:00:00Z"}
    )
    assert [item["scheduled_for"] for item in only.json()["items"]] == [
        "2027-01-05T23:00:00Z"
    ]
    backwards = await client.get(
        url, params={"from": window["to"], "to": window["from"]}
    )
    assert backwards.status_code == 422
    assert backwards.json()["errors"][0]["field"] == "query.to"
    missing = await client.get(
        "/api/v1/jobs/00000000-0000-4000-8000-000000000000/occurrences"
    )
    assert missing.status_code == 404
    broken = await client.get(url, params={"cursor": "bm90LWEtY3Vyc29y"})
    assert broken.status_code == 400


async def test_a_paused_job_lists_no_expected_runs(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
    db_engine: AsyncEngine,
) -> None:
    job = await nightly_job(client, csrf)
    paused = await client.post(
        f"/api/v1/jobs/{job['id']}/pause", headers={CSRF_HEADER: csrf}
    )
    assert paused.status_code == 200
    await at(client, clock, MISSED_AT)
    await tick(worker, clock)
    url = f"/api/v1/jobs/{job['id']}/occurrences"
    assert (await client.get(url)).json()["items"] == []
    assert (await client.get(f"/api/v1/jobs/{job['id']}")).json()["state"] == "paused"
    async with db_engine.connect() as connection:
        query = select(func.count()).select_from(Occurrence)
        assert (await connection.execute(query)).scalar_one() == 0
        query = select(JobStateRecord.suppressed)
        assert (await connection.execute(query)).scalar_one() is True
        query = select(func.count()).select_from(Flip)
        assert (await connection.execute(query)).scalar_one() == 0


async def test_deleting_the_client_leaves_no_evaluator_row(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
    db_engine: AsyncEngine,
) -> None:
    job = await nightly_job(client, csrf)
    await at(client, clock, MISSED_AT)
    await tick(worker, clock)

    async def count() -> list[int]:
        found = []
        async with db_engine.connect() as connection:
            for table in (Occurrence, JobStateRecord, Flip):
                query = select(func.count()).select_from(table)
                found.append(int((await connection.execute(query)).scalar_one()))
        return found

    assert await count() == [1, 1, 1]
    deleted = await client.delete(
        f"/api/v1/clients/{job['client_id']}",
        params={"confirm_name": DENTAL},
        headers={CSRF_HEADER: csrf},
    )
    assert deleted.status_code == 204
    assert await count() == [0, 0, 0]
    gone = await client.get(f"/api/v1/clients/{job['client_id']}")
    assert gone.status_code == 404
