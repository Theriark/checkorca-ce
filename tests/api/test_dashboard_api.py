"""dashboard/today, ribbon, trend, breakdown, activity, jobs acknowledge and
digest/preview (phase C8-B), against the fixed scenario of helpers.py on the
fake clock, with the worker's evaluator hook.

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import Services
from app.db.models import AppUser
from app.evaluator.tick import evaluate_jobs
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    SCENARIO_END,
    FakeClock,
    build_scenario,
    make_client,
    make_job,
    move_to,
    ping_path,
    sign_in,
)

DENTAL, FREIGHT, LAW = CLIENT_NAMES
SPARK_ZEROS = [0] * 12


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


@pytest.fixture
async def jobs(
    client: httpx.AsyncClient, csrf: str, worker: WorkerContext, clock: FakeClock
) -> dict[str, dict[str, Any]]:
    async def tick() -> None:
        await evaluate_jobs(worker, clock.now())

    return await build_scenario(client, csrf, clock, tick)


def stamp(day: int, hour: int, minute: int = 0) -> str:
    moment = datetime(2027, 1, day, hour, minute, tzinfo=UTC)
    return moment.isoformat().replace("+00:00", "Z")


@contextmanager
def counted(app: FastAPI) -> Iterator[list[str]]:
    """The SQL statements the app runs inside the block."""
    services: Services = app.state.services
    statements: list[str] = []

    def count(*args: Any) -> None:
        statements.append(str(args[2]))

    target = services.engine.sync_engine
    event.listen(target, "before_cursor_execute", count)
    try:
        yield statements
    finally:
        event.remove(target, "before_cursor_execute", count)


async def test_today_counts_the_scenario(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]], clock: FakeClock
) -> None:
    today = (await client.get("/api/v1/dashboard/today")).json()
    assert today["generated_at"] == "2027-01-06T09:00:00Z"
    stats = today["stats"]
    assert stats["verified"] == {
        "value": 1,
        "delta_vs_yesterday": -2,
        "spark14": SPARK_ZEROS + [3, 1],
    }
    assert stats["failed"] == {
        "value": 1,
        "delta_vs_yesterday": 1,
        "spark14": SPARK_ZEROS + [0, 1],
    }
    assert stats["silent"] == {
        "value": 1,
        "delta_vs_yesterday": 0,
        "spark14": SPARK_ZEROS + [1, 1],
    }
    assert stats["unmatched"] == {
        "value": 1,
        "delta_vs_yesterday": 1,
        "spark14": SPARK_ZEROS + [0, 1],
    }
    assert stats["paused"] == {"value": 1, "delta_vs_yesterday": 0, "spark14": [1] * 14}
    assert today["coverage"] == {"verified": 1, "expected": 4, "ratio": 0.25}
    attention = today["attention"]
    assert [(item["job_name"], item["state"]) for item in attention] == [
        ("Offsite copy", "missed"),
        ("Database dump", "failed"),
        ("Mail archive", "warning"),
    ]
    offsite, dump, archive = attention
    assert set(offsite) == {
        "client_id",
        "client_name",
        "job_id",
        "job_name",
        "state",
        "expected_by",
        "last_success_at",
        "raw_message_id",
        "acknowledged_at",
    }
    assert offsite["client_name"] == FREIGHT
    assert offsite["client_id"] == jobs["offsite"]["client_id"]
    assert offsite["expected_by"] == stamp(6, 5)
    assert offsite["last_success_at"] is None
    assert dump["job_id"] == jobs["dump"]["id"]
    assert dump["expected_by"] == stamp(6, 6)
    assert dump["last_success_at"] == stamp(4, 22, 15)
    assert dump["raw_message_id"] is None
    assert archive["expected_by"] == stamp(6, 4)
    assert archive["last_success_at"] == stamp(4, 20, 30)
    assert today["heartbeat"] == {"at": None, "age_seconds": None, "stale": True}
    assert today["demo_seeded"] is False


async def test_an_overdue_run_needs_attention_before_it_is_missed(
    client: httpx.AsyncClient,
    csrf: str,
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    # Daily 23:00 Lisbon: overdue from 07:00Z the next morning, missed at 07:30Z.
    await move_to(client, clock, datetime(2027, 1, 5, 7, 10, tzinfo=UTC))
    await evaluate_jobs(worker, clock.now())
    (item,) = (await client.get("/api/v1/dashboard/today")).json()["attention"]
    assert (item["job_id"], item["state"]) == (job["id"], "overdue")
    assert item["expected_by"] == stamp(5, 7)
    silent = (await client.get("/api/v1/dashboard/today")).json()["stats"]["silent"]
    assert silent["value"] == 1


async def test_acknowledge_marks_the_job_until_its_next_flip(
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    dump = jobs["dump"]
    url = f"/api/v1/jobs/{dump['id']}/acknowledge"
    refused = await client.post(url)
    assert refused.status_code == 403
    acknowledged = await client.post(url, headers={CSRF_HEADER: csrf})
    assert acknowledged.status_code == 200
    body = acknowledged.json()
    assert body["acknowledged_at"] == "2027-01-06T09:00:00Z"
    assert body["updated_at"] == dump["updated_at"]
    today = (await client.get("/api/v1/dashboard/today")).json()
    marked = {item["job_name"]: item["acknowledged_at"] for item in today["attention"]}
    assert marked == {
        "Offsite copy": None,
        "Database dump": "2027-01-06T09:00:00Z",
        "Mail archive": None,
    }
    activity = await client.get("/api/v1/activity", params={"kind": "config"})
    assert activity.json()["items"][0]["summary"] == "Job acknowledge"
    assert activity.json()["items"][0]["ref_id"] == dump["id"]

    # A late success recovers the failed run: the flip ends the acknowledgement.
    await move_to(client, clock, SCENARIO_END + timedelta(hours=1))
    assert (await client.get(ping_path(dump))).status_code == 200
    await evaluate_jobs(worker, clock.now())
    shown = (await client.get(f"/api/v1/jobs/{dump['id']}")).json()
    assert (shown["state"], shown["acknowledged_at"]) == ("ok", None)
    missing = await client.post(
        "/api/v1/jobs/00000000-0000-4000-8000-000000000000/acknowledge",
        headers={CSRF_HEADER: csrf},
    )
    assert missing.status_code == 404


async def test_the_ribbon_shows_the_night_by_client_and_job(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]]
) -> None:
    ribbon = (await client.get("/api/v1/dashboard/ribbon")).json()
    assert ribbon["window"] == {"from": stamp(5, 18), "to": stamp(6, 12)}
    assert ribbon["morning_line_at"] == stamp(6, 7, 30)
    lanes = [
        (lane["name"], [job["name"] for job in lane["jobs"]])
        for lane in ribbon["clients"]
    ]
    assert lanes == [
        (FREIGHT, ["Offsite copy"]),
        (DENTAL, ["Database dump", "Nightly server backup"]),
        (LAW, ["Mail archive"]),
    ]
    runs = {
        job["name"]: job["occurrences"]
        for lane in ribbon["clients"]
        for job in lane["jobs"]
    }
    assert runs["Offsite copy"] == [
        {
            "scheduled_for": stamp(5, 21),
            "deadline": stamp(6, 5),
            "state": "missed",
            "result_at": None,
        }
    ]
    assert runs["Database dump"][0]["state"] == "failed"
    assert runs["Database dump"][0]["result_at"] == stamp(5, 22, 10)
    assert runs["Nightly server backup"][0]["result_at"] == stamp(5, 23, 20)
    assert runs["Mail archive"][0]["result_at"] == stamp(5, 20, 30)

    problems = await client.get(
        "/api/v1/dashboard/ribbon", params={"problems_only": "true"}
    )
    names = [
        job["name"] for lane in problems.json()["clients"] for job in lane["jobs"]
    ]
    assert names == ["Offsite copy", "Database dump", "Mail archive"]

    # Later in the day the window reaches the evening: tonight's runs are
    # expected (pending), none for the paused job.
    later = await client.get(
        "/api/v1/dashboard/ribbon",
        params={"from": stamp(6, 18), "to": "2027-01-07T00:00:00Z"},
    )
    expected = {
        job["name"]: [run["state"] for run in job["occurrences"]]
        for lane in later.json()["clients"]
        for job in lane["jobs"]
    }
    assert expected == {
        "Offsite copy": ["pending"],
        "Database dump": ["pending"],
        "Nightly server backup": ["pending"],
        "Mail archive": ["pending"],
    }
    assert later.json()["morning_line_at"] is None
    one_bound = await client.get(
        "/api/v1/dashboard/ribbon", params={"to": stamp(6, 12)}
    )
    assert one_bound.json()["window"] == {"from": stamp(5, 18), "to": stamp(6, 12)}
    backwards = await client.get(
        "/api/v1/dashboard/ribbon", params={"from": stamp(6, 12), "to": stamp(5, 18)}
    )
    assert backwards.status_code == 422
    too_long = await client.get(
        "/api/v1/dashboard/ribbon",
        params={"from": stamp(1, 0), "to": stamp(6, 0)},
    )
    assert too_long.status_code == 422


async def test_trend_and_breakdown_count_calendar_days(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]]
) -> None:
    trend = (await client.get("/api/v1/dashboard/trend", params={"days": 3})).json()
    assert trend["items"] == [
        {"date": "2027-01-04", "verified": 3, "failed": 0, "silent": 1},
        {"date": "2027-01-05", "verified": 1, "failed": 1, "silent": 1},
        {"date": "2027-01-06", "verified": 0, "failed": 0, "silent": 0},
    ]
    default = (await client.get("/api/v1/dashboard/trend")).json()["items"]
    assert len(default) == 30 and default[-1]["date"] == "2027-01-06"
    by_client = await client.get(
        "/api/v1/dashboard/breakdown", params={"by": "client", "days": 3}
    )
    assert by_client.json()["by"] == "client"
    assert [
        (item["label"], item["verified"], item["failed"], item["silent"])
        for item in by_client.json()["items"]
    ] == [(FREIGHT, 0, 0, 2), (DENTAL, 3, 1, 0), (LAW, 1, 0, 0)]
    assert by_client.json()["items"][0]["key"] == jobs["offsite"]["client_id"]
    by_vendor = (await client.get("/api/v1/dashboard/breakdown")).json()
    assert by_vendor["by"] == "vendor"
    assert by_vendor["items"] == [
        {
            "key": "none",
            "label": "No parser pack (pings and the results API)",
            "verified": 4,
            "failed": 1,
            "silent": 2,
        }
    ]
    wrong = await client.get("/api/v1/dashboard/trend", params={"days": 0})
    assert wrong.status_code == 422


async def test_activity_lists_flips_and_changes_newest_first(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]]
) -> None:
    flips = (await client.get("/api/v1/activity", params={"kind": "flip"})).json()
    assert len(flips["items"]) == 6 and flips["next_cursor"] is None
    newest = flips["items"][0]
    assert set(newest) == {"id", "at", "kind", "summary", "ref_kind", "ref_id"}
    assert newest["at"] == "2027-01-06T09:00:00Z" and newest["kind"] == "flip"
    assert newest["ref_kind"] == "job"
    summaries = {item["summary"] for item in flips["items"][:2]}
    assert summaries == {
        f"Database dump ({DENTAL}): ok to failing",
        f"Mail archive ({LAW}): ok to warning",
    }
    config = (await client.get("/api/v1/activity", params={"kind": "config"})).json()
    actions = [item["summary"] for item in config["items"]]
    assert actions.count("Client create") == 3
    assert actions.count("Job create") == 5
    assert "Job pause" in actions and "Token create" in actions
    every = (await client.get("/api/v1/activity", params={"limit": 200})).json()
    assert len(every["items"]) == 6 + len(actions)
    assert [item["at"] for item in every["items"]] == sorted(
        (item["at"] for item in every["items"]), reverse=True
    )
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 4}
        if cursor is not None:
            params["cursor"] = cursor
        page = (await client.get("/api/v1/activity", params=params)).json()
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [item["id"] for item in every["items"]]
    ingest = (await client.get("/api/v1/activity", params={"kind": "ingest"})).json()
    assert ingest["items"] == []
    broken = await client.get("/api/v1/activity", params={"cursor": "nope"})
    assert broken.status_code == 400


async def test_the_digest_preview_renders_the_night(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]]
) -> None:
    preview = (await client.get("/api/v1/digest/preview")).json()
    assert preview["date"] == "2027-01-06"
    assert preview["subject"] == (
        "Checkorca-CE morning check 2027-01-06: 1 failed, 1 silent, 1 warning, "
        "1 verified"
    )
    html = preview["html"]
    assert "<script" not in html.lower()
    assert html.index("Offsite copy") < html.index("Database dump")
    assert html.index("Database dump") < html.index("Mail archive")
    assert "1 of 4 runs verified (25%)" in preview["text"]
    assert "- Missed: Example Freight Ltd / Offsite copy, due 2027-01-05 21:00" in (
        preview["text"]
    )
    earlier = await client.get("/api/v1/digest/preview", params={"date": "2027-01-05"})
    assert earlier.json()["subject"].endswith(": 1 silent, 3 verified")
    empty = await client.get("/api/v1/digest/preview", params={"date": "2026-12-01"})
    assert empty.json()["subject"].endswith(": no runs were due")
    wrong = await client.get("/api/v1/digest/preview", params={"date": "1999-12-31"})
    assert wrong.status_code == 422


async def test_dashboard_routes_run_a_fixed_number_of_queries(
    app: FastAPI,
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    paths = (
        "/api/v1/dashboard/today",
        "/api/v1/dashboard/ribbon",
        "/api/v1/dashboard/trend",
        "/api/v1/dashboard/breakdown?by=client",
        "/api/v1/dashboard/breakdown?by=vendor",
        "/api/v1/activity",
        "/api/v1/digest/preview",
        "/api/v1/system/status",
    )

    async def measure() -> dict[str, int]:
        found: dict[str, int] = {}
        for path in paths:
            assert (await client.get("/api/v1/auth/me")).status_code == 200
            with counted(app) as statements:
                response = await client.get(path)
            assert response.status_code == 200, (path, response.text)
            found[path] = len(statements)
        return found

    before = await measure()
    # Ten more clients with three jobs each; a day later each has a missed run
    # to count, list and show.
    for number in range(10):
        made = await make_client(client, csrf, f"Example Client {number:02d}")
        for job in range(3):
            await make_job(
                client, csrf, made["id"], f"Job {job}", schedule_expr="20:00"
            )
    await move_to(client, clock, SCENARIO_END + timedelta(days=1))
    await evaluate_jobs(worker, clock.now())
    today = (await client.get("/api/v1/dashboard/today")).json()
    assert len(today["attention"]) > 30
    after = await measure()
    assert after == before
    assert max(before.values()) <= 12


async def test_dashboard_routes_need_a_reader(app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as anonymous:
        for path in (
            "/api/v1/dashboard/today",
            "/api/v1/dashboard/ribbon",
            "/api/v1/dashboard/trend",
            "/api/v1/dashboard/breakdown",
            "/api/v1/activity",
            "/api/v1/digest/preview",
        ):
            assert (await anonymous.get(path)).status_code == 401, path


async def test_a_read_token_reads_the_dashboard(
    client: httpx.AsyncClient, csrf: str
) -> None:
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Wallboard", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    today = await client.get("/api/v1/dashboard/today", headers=bearer)
    assert today.status_code == 200
    assert today.json()["coverage"] == {"verified": 0, "expected": 0, "ratio": None}
    assert today.json()["attention"] == []
