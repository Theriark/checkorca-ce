"""The demo data (phase C8-B, app/seed/demo.py): the plan, the mail
templates against the real packs, the host rule, the full seed through the
pipeline on PostgreSQL, and that a second run adds nothing.

Every client, job and address is synthetic (legal R-11).
"""

import dataclasses
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, get_args

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.__main__ import main
from app.db.models import (
    AppSettings,
    AppUser,
    AuditEvent,
    Client,
    Flip,
    Job,
    JobResult,
    Occurrence,
    RawMessage,
    name_key,
)
from app.ext.events import Event
from app.main import create_app
from app.matcher import tokens
from app.parsers.engine import Parsed, mail_from_raw, parse
from app.parsers.loader import builtin_packs
from app.schedule import parse_spec
from app.seed.accounts import SeedError
from app.seed.demo import (
    CLIENTS,
    SEED_NOTE,
    SOURCES,
    ZONE,
    DemoSeedHook,
    demo_plan,
    seed_demo,
)
from app.seed.demo_mail import NAMES_CLIENT, TEMPLATES, Outcome, Run, render_mail
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    FakeClock,
    running,
    sign_in,
)

COUNTED = (Client, Job, RawMessage, JobResult, Occurrence, Flip, AuditEvent)


class Recorder:
    """An event subscriber that keeps what it receives."""

    name = "recorder"

    def __init__(self) -> None:
        self.events: list[Event] = []

    async def handle(self, event: Event) -> None:
        self.events.append(event)


@pytest.fixture
async def demo(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    """A worker context with DEV_DEMO_DATA=1 on localhost."""
    built = build_context(load_settings(dev_demo_data=True), clock)
    yield built
    await built.engine.dispose()


async def counts(engine: AsyncEngine) -> dict[str, int]:
    found = {}
    async with engine.connect() as connection:
        for table in COUNTED:
            result = await connection.execute(select(func.count()).select_from(table))
            found[table.__tablename__] = int(result.scalar_one())
    return found


def test_the_plan_has_20_clients_and_60_jobs_of_every_source() -> None:
    plan = demo_plan()
    assert len(CLIENTS) == 20 and len({name for name, _ in CLIENTS}) == 20
    assert len(plan) == 60
    assert {job.source for job in plan} == set(SOURCES)
    assert set(SOURCES) - {"ping"} == set(TEMPLATES)
    per_client = {(name_key(job.client), name_key(job.name)) for job in plan}
    assert len(per_client) == 60
    # A vendor whose mail does not name the client needs a unique job name.
    unnamed = [job.name for job in plan if job.source not in NAMES_CLIENT | {"ping"}]
    assert len(set(unnamed)) == len(unnamed)
    created = datetime(2027, 1, 1, tzinfo=UTC)
    for job in plan:
        parse_spec(job.schedule_kind, job.schedule_expr, ZONE, created)
    profiles = {job.profile for job in plan}
    assert profiles == {
        "healthy",
        "flaky",
        "failing",
        "warning",
        "stopped",
        "never",
        "overdue",
    }
    overdue = [job for job in plan if job.profile == "overdue"]
    assert [job.source for job in overdue] == ["ping"]


@pytest.mark.parametrize("pack_id", sorted(TEMPLATES))
@pytest.mark.parametrize("outcome", get_args(Outcome))
def test_every_template_is_claimed_by_its_own_pack(
    pack_id: str, outcome: Outcome
) -> None:
    started = datetime(2027, 1, 4, 22, 1, 5, tzinfo=UTC)
    run = Run(
        job="Quillfern VM backup",
        client="Quillfern Dental Studio",
        outcome=outcome,
        started=started,
        finished=started + timedelta(minutes=37, seconds=12),
        message_id="<demo-test@seed.example.com>",
    )
    parsed = parse(builtin_packs(), mail_from_raw(render_mail(pack_id, run)))
    assert isinstance(parsed, Parsed), parsed
    assert parsed.pack_id == pack_id
    (result,) = parsed.results
    assert result.status == outcome
    assert tokens(result.job_name) == tokens(run.job)
    if pack_id in NAMES_CLIENT:
        assert tokens(result.client_hint) == tokens(run.client)
    assert result.started_at == run.started
    assert result.finished_at in (None, run.finished)


async def test_a_production_like_host_is_refused(
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    quiet_cli: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = load_settings(
        dev_demo_data=True, base_url="https://checkorca.example.com"
    )
    context = build_context(settings, clock)
    try:
        with pytest.raises(SeedError, match="DEV_DEMO_DATA=1 is refused"):
            await seed_demo(context, clock.now())
        # The hook logs the refusal; the worker goes on.
        await DemoSeedHook()(context, clock.now())
        assert "demo seed refused" in caplog.text
    finally:
        await context.engine.dispose()
    assert (await counts(db_engine))["client"] == 0
    monkeypatch.setenv("DEV_DEMO_DATA", "1")
    monkeypatch.setenv("BASE_URL", "https://checkorca.example.com")
    assert main(["seed"]) == 2


async def test_the_hook_waits_for_the_setting(
    db_engine: AsyncEngine, clock: FakeClock
) -> None:
    context = build_context(load_settings(), clock)
    try:
        await DemoSeedHook()(context, clock.now())
    finally:
        await context.engine.dispose()
    assert (await counts(db_engine))["client"] == 0


async def test_demo_clients_left_by_an_interrupted_seed_are_not_doubled(
    demo: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    name = CLIENTS[0][0]
    async with async_sessionmaker(db_engine)() as db:
        db.add(Client(name=name, name_key=name_key(name), created_at=clock.now()))
        await db.commit()
    report = await seed_demo(demo, clock.now())
    assert (report.seeded, report.reason) == (False, "demo clients exist already")
    assert (await counts(db_engine))["job"] == 0
    # The history of that seed is incomplete: it is not marked as seeded.
    async with async_sessionmaker(db_engine)() as db:
        assert (await db.scalars(select(AppSettings.demo_seeded))).one() is False


async def test_the_demo_seed_goes_through_the_pipeline_once(
    demo: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    admin: AppUser,
) -> None:
    hook = DemoSeedHook()
    recorder = Recorder()
    await hook(dataclasses.replace(demo, subscribers=(recorder,)), clock.now())
    assert hook.done
    seeded = await counts(db_engine)
    assert seeded["client"] == 20 and seeded["job"] == 60
    assert seeded["raw_message"] > 300 and seeded["flip"] > 0
    # Made-up flips never reach a subscriber (phase C9 notifies through them).
    assert recorder.events == []
    async with async_sessionmaker(db_engine)() as db:
        notes = set((await db.scalars(select(Client.notes))).all())
        assert notes == {SEED_NOTE}
        assert (await db.scalars(select(AppSettings.demo_seeded))).one() is True
        states = dict(
            (
                await db.execute(
                    select(RawMessage.parse_state, func.count()).group_by(
                        RawMessage.parse_state
                    )
                )
            ).all()
        )
        assert states == {"parsed": seeded["raw_message"]}
        waiting = select(func.count()).select_from(JobResult)
        waiting = waiting.where(JobResult.job_id.is_(None))
        assert (await db.execute(waiting)).scalar_one() == 3
        bound = (
            select(Job.parser_pack_id, func.count())
            .join(JobResult, JobResult.job_id == Job.id)
            .group_by(Job.parser_pack_id)
        )
        packs = dict((await db.execute(bound)).all())
        assert set(packs) == set(TEMPLATES) | {None}
        paused = select(func.count()).select_from(Job).where(Job.enabled.is_(False))
        assert (await db.execute(paused)).scalar_one() == 2

    # A second run adds nothing.
    again = await seed_demo(demo, clock.now())
    assert (again.seeded, again.reason) == (False, "already seeded")
    assert await counts(db_engine) == seeded

    application = create_app(load_settings(), static_dir=None, clock=clock)
    async with running(application) as client:
        csrf = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        await check_the_dashboard(client)
        # Deleting a demo client leaves nothing of it behind.
        made = (await client.get("/api/v1/clients", params={"q": "Quillfern"})).json()
        (quillfern,) = made["items"]
        deleted = await client.delete(
            f"/api/v1/clients/{quillfern['id']}",
            params={"confirm_name": quillfern["name"]},
            headers={CSRF_HEADER: csrf},
        )
        assert deleted.status_code == 204
    gone = uuid.UUID(quillfern["id"])
    async with async_sessionmaker(db_engine)() as db:
        left = select(func.count()).select_from(RawMessage)
        left = left.where(RawMessage.client_id == gone)
        assert (await db.execute(left)).scalar_one() == 0
        jobs = select(func.count()).select_from(Job).where(Job.client_id == gone)
        assert (await db.execute(jobs)).scalar_one() == 0


async def check_the_dashboard(client: httpx.AsyncClient) -> None:
    """The Morning check with the demo data: numbers, attention, ribbon,
    exports and digest, and dashboard/today well under 500 ms."""
    assert (await client.get("/api/v1/dashboard/today")).status_code == 200
    started = time.perf_counter()
    response = await client.get("/api/v1/dashboard/today")
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 0.5, elapsed
    today: dict[str, Any] = response.json()
    assert today["demo_seeded"] is True
    assert today["stats"]["paused"]["value"] == 2
    assert today["stats"]["unmatched"]["value"] == 3
    states = {item["state"] for item in today["attention"]}
    assert {"missed", "failed", "warning", "overdue"} <= states
    assert today["coverage"]["expected"] > 0
    ribbon = (await client.get("/api/v1/dashboard/ribbon")).json()
    hollow = [
        run
        for lane in ribbon["clients"]
        for job in lane["jobs"]
        for run in job["occurrences"]
        if run["state"] in ("overdue", "missed")
    ]
    assert hollow
    trend = (await client.get("/api/v1/dashboard/trend")).json()["items"]
    assert sum(day["verified"] for day in trend) > 100
    vendors = (await client.get("/api/v1/dashboard/breakdown")).json()["items"]
    assert len(vendors) == len(TEMPLATES) + 1
    day = await client.get("/api/v1/exports/day.csv")
    assert day.status_code == 200 and day.text.count("\n") > 1
    preview = (await client.get("/api/v1/digest/preview")).json()
    assert "<script" not in preview["html"].lower()
