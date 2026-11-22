"""dashboard/today, ribbon, trend, breakdown, activity, jobs acknowledge and
digest/preview (phase C8-B), against the fixed scenario of helpers.py on the
fake clock, with the worker's evaluator hook.

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import Services
from app.api.v1.dashboard import NO_PACK_LABEL
from app.db.models import AppSettings, AppUser, Job
from app.evaluator.tick import evaluate_jobs
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from app.worker.parse import ParseHook
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    MAIL_INBOX,
    MAIL_SECRET,
    SCENARIO_END,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    another_browser,
    build_scenario,
    deliver_mail,
    make_client,
    make_job,
    move_to,
    ping_path,
    sign_in,
)

DENTAL, FREIGHT, LAW = CLIENT_NAMES
SPARK_ZEROS = [0] * 12
# Built-in packs for the jobs added in the query count test.
PACKS = ("veeam-br", "synology-abb", "msp360")


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
    names = [job["name"] for lane in problems.json()["clients"] for job in lane["jobs"]]
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
    longest = await client.get(
        "/api/v1/dashboard/ribbon",
        params={"from": stamp(3, 12), "to": stamp(6, 12)},
    )
    assert longest.status_code == 200
    # A bound outside 2000 to 2099 is refused (a window there would overflow).
    for params in (
        {"from": "0001-01-01T00:00:00Z"},
        {"to": "9999-12-31T23:00:00Z"},
        {"from": "2100-01-01T00:00:00Z", "to": "2100-01-01T06:00:00Z"},
    ):
        far = await client.get("/api/v1/dashboard/ribbon", params=params)
        assert far.status_code == 422, params


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
    longest = await client.get("/api/v1/dashboard/trend", params={"days": 90})
    assert len(longest.json()["items"]) == 90
    for days in (0, 91):
        wrong = await client.get("/api/v1/dashboard/trend", params={"days": days})
        assert wrong.status_code == 422, days


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
    too_many = await client.get("/api/v1/activity", params={"limit": 201})
    assert too_many.status_code == 422


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
    assert (
        "- Missed: Example Freight Ltd / Offsite copy, due 2027-01-05 21:00"
        in (preview["text"])
    )
    earlier = await client.get("/api/v1/digest/preview", params={"date": "2027-01-05"})
    assert earlier.json()["subject"].endswith(": 1 silent, 3 verified")
    empty = await client.get("/api/v1/digest/preview", params={"date": "2026-12-01"})
    assert empty.json()["subject"].endswith(": no runs were due")
    last = await client.get("/api/v1/digest/preview", params={"date": "2099-12-31"})
    assert last.json()["subject"].endswith(": no runs were due")
    for day in ("1999-12-31", "2100-01-01"):
        wrong = await client.get("/api/v1/digest/preview", params={"date": day})
        assert wrong.status_code == 422, day


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
    # Ten more clients with three jobs each, one per parser pack (three more
    # vendor groups); a day later each has a missed run to count, list and
    # show.
    for number in range(10):
        made = await make_client(client, csrf, f"Example Client {number:02d}")
        for job, pack in enumerate(PACKS):
            await make_job(
                client,
                csrf,
                made["id"],
                f"Job {job}",
                schedule_expr="20:00",
                parser_pack_id=pack,
            )
    await move_to(client, clock, SCENARIO_END + timedelta(days=1))
    await evaluate_jobs(worker, clock.now())
    today = (await client.get("/api/v1/dashboard/today")).json()
    assert len(today["attention"]) > 30
    vendors = (await client.get("/api/v1/dashboard/breakdown")).json()["items"]
    assert {item["key"] for item in vendors} == {"none", *PACKS}
    after = await measure()
    assert after == before
    assert max(before.values()) <= 12

    # Within a group the same deadline is ordered by client and job name; an
    # acknowledged job goes after the ones nobody acknowledged.
    def missed(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return [
            (item["client_name"], item["job_name"])
            for item in items
            if item["state"] == "missed"
        ]

    order = missed(today["attention"])
    assert order[:4] == [
        ("Example Client 00", "Job 0"),
        ("Example Client 00", "Job 1"),
        ("Example Client 00", "Job 2"),
        ("Example Client 01", "Job 0"),
    ]
    first = today["attention"][0]
    acknowledged = await client.post(
        f"/api/v1/jobs/{first['job_id']}/acknowledge", headers={CSRF_HEADER: csrf}
    )
    assert acknowledged.status_code == 200
    again = (await client.get("/api/v1/dashboard/today")).json()["attention"]
    assert missed(again) == order[1:] + order[:1]


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


def csv_lines(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return response.content.decode("utf-8-sig").splitlines()


async def test_archived_jobs_and_clients_leave_the_dashboard(
    client: httpx.AsyncClient, csrf: str, jobs: dict[str, dict[str, Any]]
) -> None:
    # The law office (mail archive and paused job) and the offsite copy go.
    law = jobs["archive"]["client_id"]
    for path in (
        f"/api/v1/clients/{law}/archive",
        f"/api/v1/jobs/{jobs['offsite']['id']}/archive",
    ):
        archived = await client.post(path, headers={CSRF_HEADER: csrf})
        assert archived.status_code == 200, archived.text
    today = (await client.get("/api/v1/dashboard/today")).json()
    stats = today["stats"]
    assert stats["verified"] == {
        "value": 1,
        "delta_vs_yesterday": -1,
        "spark14": SPARK_ZEROS + [2, 1],
    }
    assert stats["failed"]["value"] == 1
    assert stats["silent"] == {
        "value": 0,
        "delta_vs_yesterday": 0,
        "spark14": [0] * 14,
    }
    assert stats["paused"]["value"] == 0
    assert today["coverage"] == {"verified": 1, "expected": 2, "ratio": 0.5}
    assert [(item["job_name"], item["state"]) for item in today["attention"]] == [
        ("Database dump", "failed")
    ]
    ribbon = (await client.get("/api/v1/dashboard/ribbon")).json()
    assert [
        (lane["name"], [job["name"] for job in lane["jobs"]])
        for lane in ribbon["clients"]
    ] == [(DENTAL, ["Database dump", "Nightly server backup"])]
    trend = (await client.get("/api/v1/dashboard/trend", params={"days": 3})).json()
    assert trend["items"] == [
        {"date": "2027-01-04", "verified": 2, "failed": 0, "silent": 0},
        {"date": "2027-01-05", "verified": 1, "failed": 1, "silent": 0},
        {"date": "2027-01-06", "verified": 0, "failed": 0, "silent": 0},
    ]
    by_client = await client.get(
        "/api/v1/dashboard/breakdown", params={"by": "client", "days": 3}
    )
    assert [
        (item["label"], item["verified"], item["failed"], item["silent"])
        for item in by_client.json()["items"]
    ] == [(DENTAL, 3, 1, 0)]
    by_vendor = await client.get("/api/v1/dashboard/breakdown", params={"days": 3})
    assert [
        (item["key"], item["verified"], item["failed"], item["silent"])
        for item in by_vendor.json()["items"]
    ] == [("none", 3, 1, 0)]
    preview = (await client.get("/api/v1/digest/preview")).json()
    assert preview["subject"].endswith(": 1 failed, 1 verified")
    assert "Offsite copy" not in preview["text"]

    # The exports keep them: history is history.
    history = await client.get(
        "/api/v1/exports/history.csv",
        params={"from": "2027-01-04", "to": "2027-01-05"},
    )
    lines = csv_lines(history)
    assert len(lines) == 9
    assert sum(",Mail archive," in line for line in lines) == 2
    assert sum(",Offsite copy," in line for line in lines) == 2
    day = await client.get("/api/v1/exports/day.csv", params={"date": "2027-01-05"})
    assert len(csv_lines(day)) == 5
    export = csv_lines(await client.get(f"/api/v1/clients/{law}/export.csv"))
    assert export[1].startswith(f"client,{LAW},,2027-01-04T09:00:00Z,archived,")
    assert any(line.startswith(f"job,{LAW},Mail archive,") for line in export)


async def test_calendar_days_and_the_night_follow_the_digest_zone(
    client: httpx.AsyncClient,
    jobs: dict[str, dict[str, Any]],
    db_engine: AsyncEngine,
) -> None:
    # Tokyo is UTC+9 all year: the runs of the evening of 4 January (UTC)
    # fall on 5 January there, those of 5 January on the 6th, and the
    # scenario ends at 18:00 on 6 January.
    async with db_engine.begin() as connection:
        await connection.execute(
            update(AppSettings).values(digest_timezone="Asia/Tokyo")
        )
    trend = (await client.get("/api/v1/dashboard/trend", params={"days": 3})).json()
    assert trend["items"] == [
        {"date": "2027-01-04", "verified": 0, "failed": 0, "silent": 0},
        {"date": "2027-01-05", "verified": 3, "failed": 0, "silent": 1},
        {"date": "2027-01-06", "verified": 1, "failed": 1, "silent": 1},
    ]
    day = await client.get("/api/v1/exports/day.csv", params={"date": "2027-01-05"})
    rows = [line.split(",") for line in csv_lines(day)[1:]]
    assert [(row[0], row[2], row[5]) for row in rows] == [
        ("2027-01-05", "Mail archive", "2027-01-04T20:00:00Z"),
        ("2027-01-05", "Offsite copy", "2027-01-04T21:00:00Z"),
        ("2027-01-05", "Database dump", "2027-01-04T22:00:00Z"),
        ("2027-01-05", "Nightly server backup", "2027-01-04T23:00:00Z"),
    ]
    # The digest of 6 January: due from 07:30 on the 5th to 07:30 on the 6th
    # in Tokyo (22:30 UTC to 22:30 UTC).
    preview = (await client.get("/api/v1/digest/preview")).json()
    assert preview["date"] == "2027-01-06"
    assert preview["subject"].endswith(": 1 failed, 1 silent, 1 warning, 1 verified")
    text = preview["text"]
    assert "Runs due from 2027-01-05 07:30 to 2027-01-06 07:30 (Asia/Tokyo)" in text
    assert f"- Missed: {FREIGHT} / Offsite copy, due 2027-01-06 06:00" in text
    earlier = await client.get("/api/v1/digest/preview", params={"date": "2027-01-05"})
    assert earlier.json()["subject"].endswith(": 1 silent, 2 verified")
    # 18:00 in Tokyo: tonight's night, to 12:00 tomorrow there.
    ribbon = (await client.get("/api/v1/dashboard/ribbon")).json()
    assert ribbon["window"] == {"from": stamp(6, 9), "to": "2027-01-07T03:00:00Z"}
    assert ribbon["morning_line_at"] == stamp(6, 22, 30)


async def test_the_vendor_is_the_pack_set_on_the_job(
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    # The parse hook writes the built-in packs (no mail waits).
    await ParseHook()(worker, clock.now())
    for key, pack in (
        ("nightly", "veeam-br"),
        ("offsite", "veeam-br"),
        ("dump", "synology-abb"),
    ):
        changed = await client.patch(
            f"/api/v1/jobs/{jobs[key]['id']}",
            json={"parser_pack_id": pack},
            headers={CSRF_HEADER: csrf},
        )
        assert changed.status_code == 200, changed.text
    # Every result came by ping or the results API, none through a pack: the
    # vendor is the pack set on the job.
    by_vendor = await client.get("/api/v1/dashboard/breakdown", params={"days": 3})
    assert by_vendor.json()["items"] == [
        {
            "key": "none",
            "label": NO_PACK_LABEL,
            "verified": 1,
            "failed": 0,
            "silent": 0,
        },
        {
            "key": "synology-abb",
            "label": "Synology Active Backup for Business",
            "verified": 1,
            "failed": 1,
            "silent": 0,
        },
        {
            "key": "veeam-br",
            "label": "Veeam Backup & Replication",
            "verified": 2,
            "failed": 0,
            "silent": 2,
        },
    ]


async def test_a_received_mail_is_ingest_activity(
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    async def parse() -> None:
        await ParseHook()(worker, clock.now())

    message_id = await deliver_mail(client, csrf, parse)
    ingest = (await client.get("/api/v1/activity", params={"kind": "ingest"})).json()
    assert ingest["items"] == [
        {
            "id": message_id,
            "at": "2027-01-06T09:00:00Z",
            "kind": "ingest",
            "summary": f"Message received in {MAIL_INBOX}: parsed",
            "ref_kind": "message",
            "ref_id": message_id,
        }
    ]
    every = await client.get("/api/v1/activity", params={"limit": 200})
    assert MAIL_SECRET not in every.text


async def test_a_technician_acknowledges_and_a_read_token_cannot(
    app: FastAPI,
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    technician: AppUser,
    db_engine: AsyncEngine,
) -> None:
    url = f"/api/v1/jobs/{jobs['dump']['id']}/acknowledge"
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Wallboard", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    async with another_browser(app) as other:
        assert (await other.post(url, headers=bearer)).status_code == 401
        token = await sign_in(other, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
        done = await other.post(url, headers={CSRF_HEADER: token})
        assert done.status_code == 200, done.text
        assert done.json()["acknowledged_at"] == "2027-01-06T09:00:00Z"
    async with db_engine.connect() as connection:
        query = select(Job.acknowledged_by).where(
            Job.id == uuid.UUID(jobs["dump"]["id"])
        )
        assert (await connection.execute(query)).scalar_one() == technician.id
