"""The evaluator hook on PostgreSQL: jobs, results and the injected clock in,
occurrences, job_state rows, flips and events out (phase C7).

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

import dataclasses
import logging
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Row, delete, event, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.models import (
    Client,
    Flip,
    Job,
    JobResult,
    JobStateRecord,
    Occurrence,
    name_key,
)
from app.evaluator.model import MaintenanceWindow
from app.evaluator.tick import Evaluator, evaluate_jobs
from app.ext.events import Event, FlipCreated, OccurrenceChanged
from app.ext.suppression import MaintenanceTarget
from app.ingest.results import ParsedResult
from app.ingest.store import record_result
from app.repos.clients import ClientRepository
from app.repos.evaluation import EvaluationRepository
from app.security.tokens import new_ping_token
from app.settings import load_settings
from app.worker import loop
from app.worker.loop import WorkerContext, build_context
from app.worker.parse import parse_messages
from helpers import FakeClock

DENTAL = "Fictional Dental Clinic"
NIGHTLY = "Nightly server backup"
CREATED = datetime(2027, 1, 4, 12, tzinfo=UTC)
NIGHT = datetime(2027, 1, 4, 23, tzinfo=UTC)
# Daily 23:00 Europe/Lisbon with the default rules: overdue at 07:00Z, missed
# from 07:30Z.
OVERDUE_AT = datetime(2027, 1, 5, 7, tzinfo=UTC)
MISSED_AT = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


def session(engine: AsyncEngine) -> AsyncSession:
    return async_sessionmaker(engine, expire_on_commit=False)()


def at(clock: FakeClock, moment: datetime) -> None:
    clock.advance(seconds=(moment - clock.now()).total_seconds())


async def add_client(engine: AsyncEngine, name: str = DENTAL) -> Client:
    client = Client(name=name, name_key=name_key(name), created_at=CREATED)
    async with session(engine) as db:
        db.add(client)
        await db.commit()
    return client


async def add_job(
    engine: AsyncEngine,
    client: Client,
    name: str = NIGHTLY,
    expr: str = "23:00",
    **fields: Any,
) -> Job:
    """A daily job of the client, created at CREATED unless fields say."""
    values: dict[str, Any] = {
        "client_id": client.id,
        "name": name,
        "name_key": name_key(name),
        "kind": "backup",
        "schedule_kind": "daily",
        "schedule_expr": expr,
        "timezone": "Europe/Lisbon",
        "ping_token": new_ping_token(),
        "created_at": CREATED,
        "updated_at": CREATED,
    }
    job = Job(**(values | fields))
    async with session(engine) as db:
        db.add(job)
        await db.commit()
    return job


async def report(
    engine: AsyncEngine, job: Job, status: str, finished: datetime
) -> uuid.UUID:
    """A result of the job, as a ping or the results API records it."""
    async with session(engine) as db:
        result_id = await record_result(
            db,
            AllowAllPolicy(),
            SYSTEM,
            ParsedResult(status=status, finished_at=finished),
            received_at=finished + timedelta(minutes=1),
            job_id=job.id,
        )
        await db.commit()
    return result_id


async def occurrences(engine: AsyncEngine, job: Job) -> list[Occurrence]:
    async with session(engine) as db:
        query = (
            select(Occurrence)
            .where(Occurrence.job_id == job.id)
            .order_by(Occurrence.scheduled_for)
        )
        return list((await db.scalars(query)).all())


async def record_of(engine: AsyncEngine, job: Job) -> JobStateRecord | None:
    async with session(engine) as db:
        return await db.get(JobStateRecord, job.id)


async def flips(engine: AsyncEngine) -> list[Flip]:
    async with session(engine) as db:
        query = select(Flip).order_by(Flip.at, Flip.id)
        return list((await db.scalars(query)).all())


async def snapshot(engine: AsyncEngine) -> list[list[Row[Any]]]:
    """Every evaluator row, for before-and-after comparisons."""
    async with engine.connect() as connection:
        return [
            list((await connection.execute(select(table))).all())
            for table in (Occurrence, JobStateRecord, Flip)
        ]


async def test_the_evaluator_runs_on_every_tick_after_the_parse() -> None:
    hooks = list(loop.TICK_HOOKS)
    assert evaluate_jobs in hooks
    assert hooks.index(parse_messages) < hooks.index(evaluate_jobs)


async def test_a_silent_job_goes_overdue_then_missed_with_one_flip(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    at(clock, OVERDUE_AT)
    await evaluate_jobs(context, clock.now())
    (night,) = await occurrences(db_engine, job)
    assert (night.scheduled_for, night.state) == (NIGHT, "overdue")
    assert night.deadline == OVERDUE_AT
    record = await record_of(db_engine, job)
    assert record is not None and record.state == "unknown"
    assert await flips(db_engine) == []

    at(clock, MISSED_AT)
    await evaluate_jobs(context, clock.now())
    (night,) = await occurrences(db_engine, job)
    assert night.state == "missed" and night.evaluated_at == MISSED_AT
    record = await record_of(db_engine, job)
    assert record is not None
    assert (record.state, record.since, record.consecutive_failures) == (
        "missed",
        MISSED_AT,
        1,
    )
    (flip,) = await flips(db_engine)
    assert (flip.job_id, flip.client_id) == (job.id, client.id)
    assert (flip.from_state, flip.to_state, flip.at) == ("unknown", "missed", MISSED_AT)
    assert flip.scheduled_for == NIGHT
    assert "was missed" in flip.reason


async def test_a_late_success_gives_verified_and_one_recovery_flip(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    at(clock, MISSED_AT)
    await evaluate_jobs(context, clock.now())
    clock.advance(hours=3)
    finished = clock.now() - timedelta(minutes=5)
    result_id = await report(db_engine, job, "success", finished)
    await evaluate_jobs(context, clock.now())
    (night,) = await occurrences(db_engine, job)
    assert (night.state, night.result_id, night.note) == (
        "verified",
        result_id,
        "late result",
    )
    record = await record_of(db_engine, job)
    assert record is not None
    assert (record.state, record.last_success_at) == ("ok", finished)
    names = [(flip.from_state, flip.to_state) for flip in await flips(db_engine)]
    assert names == [("unknown", "missed"), ("missed", "ok")]


async def test_a_second_tick_at_the_same_time_changes_nothing(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    await add_job(db_engine, client, "Weekly image backup", "02:00")
    await report(db_engine, job, "failed", NIGHT + timedelta(hours=1))
    at(clock, MISSED_AT)
    first = await Evaluator(context).run(clock.now())
    assert (first.candidates, first.due, first.evaluated) == (2, 2, 2)
    # The failed night flips; the other job's first run is still pending.
    assert first.flips == 1
    before = await snapshot(db_engine)
    again = await Evaluator(context).run(clock.now())
    assert (again.due, again.evaluated, again.rows, again.flips) == (0, 0, 0, 0)
    assert await snapshot(db_engine) == before


async def test_a_new_result_or_a_changed_job_is_evaluated_at_once(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    at(clock, NIGHT + timedelta(hours=1))
    await evaluate_jobs(context, clock.now())
    clock.advance(minutes=1)
    # Nothing new: the job is not due again before its deadline.
    assert (await Evaluator(context).run(clock.now())).due == 0
    await report(db_engine, job, "success", clock.now())
    assert (await Evaluator(context).run(clock.now())).evaluated == 1
    (night,) = await occurrences(db_engine, job)
    assert night.state == "verified"
    async with session(db_engine) as db:
        changed = update(Job).where(Job.id == job.id)
        await db.execute(changed.values(grace_minutes=60, updated_at=clock.now()))
        await db.commit()
    assert (await Evaluator(context).run(clock.now())).evaluated == 1
    (night,) = await occurrences(db_engine, job)
    assert night.deadline == NIGHT + timedelta(hours=7)


async def test_events_follow_the_commit_and_a_failing_subscriber_is_logged(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    seen: list[Event] = []
    committed: list[int] = []

    class Broken:
        name = "broken"

        async def handle(self, event: Event) -> None:
            raise RuntimeError("synthetic subscriber failure")

    class Recorder:
        name = "recorder"

        async def handle(self, event: Event) -> None:
            seen.append(event)
            if isinstance(event, FlipCreated):
                # The flip is already committed when its event arrives.
                async with session(db_engine) as db:
                    query = select(func.count()).select_from(Flip)
                    committed.append(int((await db.execute(query)).scalar_one()))

    with_subscribers = dataclasses.replace(context, subscribers=(Broken(), Recorder()))
    at(clock, MISSED_AT)
    with caplog.at_level(logging.ERROR, logger="app.ext.events"):
        tick = await Evaluator(with_subscribers).run(clock.now())
    assert tick.evaluated == 1 and tick.events == 2
    created, flipped = seen
    assert created == OccurrenceChanged(job.id, NIGHT, None, "missed", MISSED_AT)
    assert isinstance(flipped, FlipCreated)
    assert (flipped.job_id, flipped.client_id) == (job.id, client.id)
    assert (flipped.from_state, flipped.to_state) == ("unknown", "missed")
    assert committed == [1]
    assert (await flips(db_engine))[0].id == flipped.flip_id
    failures = [
        record
        for record in caplog.records
        if "subscriber broken failed" in record.getMessage()
    ]
    assert len(failures) == 2


async def test_a_subscriber_error_never_stops_the_worker_tick(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    class Broken:
        name = "broken"

        async def handle(self, event: Event) -> None:
            raise RuntimeError("synthetic subscriber failure")

    calls: list[str] = []

    async def after(context: WorkerContext, now: datetime) -> None:
        calls.append("after")

    client = await add_client(db_engine)
    await add_job(db_engine, client)
    at(clock, MISSED_AT)
    with_broken = dataclasses.replace(context, subscribers=(Broken(),))
    worker = loop.Worker(
        with_broken, hooks=(evaluate_jobs, after), receivers=(), holder="tick"
    )
    await worker.tick()
    assert calls == ["after"] and worker.ticks == 1
    assert len(await flips(db_engine)) == 1


async def test_a_paused_job_keeps_its_state_and_starts_again_when_resumed(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    at(clock, OVERDUE_AT)
    await evaluate_jobs(context, clock.now())
    assert [item.state for item in await occurrences(db_engine, job)] == ["overdue"]
    async with session(db_engine) as db:
        paused = update(Job).where(Job.id == job.id)
        await db.execute(paused.values(enabled=False, updated_at=clock.now()))
        await db.commit()
    clock.advance(hours=1)
    await evaluate_jobs(context, clock.now())
    assert await occurrences(db_engine, job) == []
    record = await record_of(db_engine, job)
    assert record is not None and record.suppressed and record.state == "unknown"
    # While paused nothing is due, even a day later.
    clock.advance(days=1)
    assert (await Evaluator(context).run(clock.now())).due == 0
    async with session(db_engine) as db:
        resumed = update(Job).where(Job.id == job.id)
        await db.execute(resumed.values(enabled=True, updated_at=clock.now()))
        await db.commit()
    await evaluate_jobs(context, clock.now())
    record = await record_of(db_engine, job)
    assert record is not None and not record.suppressed
    assert record.eval_from == clock.now()
    assert await occurrences(db_engine, job) == []
    assert await flips(db_engine) == []


async def test_an_archived_client_suppresses_its_jobs(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    async with session(db_engine) as db:
        archived = update(Client).where(Client.id == client.id)
        await db.execute(archived.values(archived=True))
        await db.commit()
    at(clock, MISSED_AT)
    await evaluate_jobs(context, clock.now())
    assert await occurrences(db_engine, job) == []
    record = await record_of(db_engine, job)
    assert record is not None and record.suppressed
    assert await flips(db_engine) == []


async def test_maintenance_windows_come_from_the_provider(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    asked: list[tuple[list[MaintenanceTarget], datetime, datetime]] = []

    class Windows:
        async def maintenance(
            self, targets: Sequence[MaintenanceTarget], start: datetime, end: datetime
        ) -> Mapping[uuid.UUID, Sequence[MaintenanceWindow]]:
            asked.append((list(targets), start, end))
            return {job.id: [MaintenanceWindow(NIGHT, NIGHT + timedelta(hours=1))]}

    at(clock, MISSED_AT)
    await evaluate_jobs(dataclasses.replace(context, suppression=Windows()), MISSED_AT)
    (night,) = await occurrences(db_engine, job)
    assert night.state == "maintenance"
    ((targets, start, end),) = asked
    assert targets == [MaintenanceTarget(job.id, client.id)]
    assert start == MISSED_AT - timedelta(days=14)
    assert end > MISSED_AT


async def test_a_failing_provider_leaves_the_batch_for_the_next_tick(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Broken:
        async def maintenance(
            self, targets: Sequence[MaintenanceTarget], start: datetime, end: datetime
        ) -> Mapping[uuid.UUID, Sequence[MaintenanceWindow]]:
            raise RuntimeError("synthetic provider failure")

    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    at(clock, MISSED_AT)
    with caplog.at_level(logging.ERROR, logger="app.evaluator.tick"):
        tick = await Evaluator(dataclasses.replace(context, suppression=Broken())).run(
            clock.now()
        )
    assert (tick.failed_batches, tick.evaluated) == (1, 0)
    assert "suppression provider failed" in caplog.text
    assert await snapshot(db_engine) == [[], [], []]
    await evaluate_jobs(context, clock.now())
    assert [item.state for item in await occurrences(db_engine, job)] == ["missed"]


async def test_a_conflicting_batch_is_rolled_back_and_retried(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    original = EvaluationRepository.save
    calls: list[int] = []

    async def conflicting(self: Any, principal: Any, changes: Any) -> None:
        calls.append(1)
        await original(self, principal, changes)
        if len(calls) == 1:
            raise IntegrityError("synthetic", {}, Exception("job deleted meanwhile"))

    monkeypatch.setattr(EvaluationRepository, "save", conflicting)
    at(clock, MISSED_AT)
    tick = await Evaluator(context).run(clock.now())
    assert (tick.failed_batches, tick.evaluated, tick.flips) == (1, 0, 0)
    assert await snapshot(db_engine) == [[], [], []]
    tick = await Evaluator(context).run(clock.now())
    assert (tick.failed_batches, tick.evaluated, tick.flips) == (0, 1, 1)
    assert [item.state for item in await occurrences(db_engine, job)] == ["missed"]


async def test_a_schedule_that_no_longer_parses_is_skipped_and_kept(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = await add_client(db_engine)
    broken = await add_job(db_engine, client, timezone="Mars/Olympus_Mons")
    fine = await add_job(db_engine, client, "Weekly image backup")
    at(clock, MISSED_AT)
    with caplog.at_level(logging.WARNING, logger="app.evaluator.tick"):
        tick = await Evaluator(context).run(clock.now())
    assert (tick.evaluated, tick.skipped) == (1, 1)
    assert "no longer parses" in caplog.text
    assert await occurrences(db_engine, broken) == []
    assert len(await occurrences(db_engine, fine)) == 1
    record = await record_of(db_engine, broken)
    assert record is not None
    assert (record.state, record.due_at, record.evaluated_at) == (
        "unknown",
        None,
        MISSED_AT,
    )
    # Tried again only after an hour.
    clock.advance(minutes=59)
    assert (await Evaluator(context).run(clock.now())).due == 0
    clock.advance(minutes=1)
    assert (await Evaluator(context).run(clock.now())).due == 2


async def test_a_job_the_evaluator_cannot_evaluate_is_skipped(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise ValueError("synthetic: too many occurrences")

    monkeypatch.setattr("app.evaluator.tick.evaluate", refuse)
    at(clock, MISSED_AT)
    tick = await Evaluator(context).run(clock.now())
    assert (tick.evaluated, tick.skipped, tick.failed_batches) == (0, 1, 0)
    record = await record_of(db_engine, job)
    assert record is not None and record.due_at is None
    assert await occurrences(db_engine, job) == []


async def test_an_empty_database_is_a_quiet_tick(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    await evaluate_jobs(context, clock.now())
    assert await snapshot(db_engine) == [[], [], []]


async def test_the_cap_and_the_budget_leave_jobs_for_the_next_tick(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    for index in range(3):
        await add_job(db_engine, client, f"Backup {index}")
    at(clock, MISSED_AT)
    tick = await Evaluator(context, max_jobs=2, batch_size=1, budget_seconds=0).run(
        clock.now()
    )
    # One batch of one job; the cap left one job, the budget another.
    assert (tick.due, tick.evaluated, tick.left) == (3, 1, 2)
    tick = await Evaluator(context).run(clock.now())
    assert (tick.due, tick.evaluated, tick.left) == (2, 2, 0)


async def test_a_deleted_result_unlinks_its_occurrence(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    result_id = await report(db_engine, job, "success", NIGHT + timedelta(hours=1))
    at(clock, MISSED_AT)
    await evaluate_jobs(context, clock.now())
    assert (await occurrences(db_engine, job))[0].result_id == result_id
    async with session(db_engine) as db:
        await db.execute(delete(JobResult).where(JobResult.id == result_id))
        await db.commit()
    (night,) = await occurrences(db_engine, job)
    assert night.result_id is None
    # The next evaluation decides again: without the result the run is missed.
    await evaluate_jobs(context, clock.now())
    (night,) = await occurrences(db_engine, job)
    assert night.state == "missed"


async def test_a_weekly_job_counts_missed_weeks_past_the_window(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(
        db_engine,
        client,
        expr="7d",
        schedule_kind="interval",
        consecutive_failures_to_alert=3,
    )
    week = timedelta(days=7)
    # Due a week after creation at 12:00Z, missed from 20:30Z.
    for number in range(1, 4):
        at(clock, CREATED + week * number + timedelta(hours=9))
        await evaluate_jobs(context, clock.now())
    first = (await occurrences(db_engine, job))[0]
    assert first.scheduled_for == CREATED + week
    assert first.scheduled_for < clock.now() - timedelta(days=14)
    record = await record_of(db_engine, job)
    assert record is not None
    assert (record.state, record.consecutive_failures) == ("missed", 3)
    names = [(flip.from_state, flip.to_state) for flip in await flips(db_engine)]
    assert names == [("unknown", "warning"), ("warning", "missed")]
    # Week 4: the window holds weeks 3 and 4, so the tick must read weeks 1
    # and 2 before it (two runs, up to the threshold of 3).
    at(clock, CREATED + week * 4 + timedelta(hours=9))
    await evaluate_jobs(context, clock.now())
    record = await record_of(db_engine, job)
    assert record is not None
    assert (record.state, record.consecutive_failures) == ("missed", 4)
    assert len(await flips(db_engine)) == 2


async def add_occurrences(
    engine: AsyncEngine, job: Job, states: Mapping[int, str]
) -> None:
    """Stored occurrences of the job, one per day after CREATED."""
    async with session(engine) as db:
        for day, state in states.items():
            due = CREATED + timedelta(days=day)
            db.add(
                Occurrence(
                    job_id=job.id,
                    scheduled_for=due,
                    deadline=due + timedelta(hours=8),
                    state=state,
                    evaluated_at=CREATED,
                )
            )
        await db.commit()


async def test_earlier_reads_the_newest_counted_runs_and_the_newest_closed_one(
    db_engine: AsyncEngine,
) -> None:
    client = await add_client(db_engine)
    counted = await add_job(db_engine, client)
    ending = await add_job(db_engine, client, name="Weekly archive copy")
    empty = await add_job(db_engine, client, name="Mailbox export")
    await add_occurrences(
        db_engine,
        counted,
        {
            1: "verified",
            2: "missed",
            3: "failed",
            4: "maintenance",
            5: "missed",
            6: "running",
            10: "missed",
            11: "missed",
        },
    )
    await add_occurrences(db_engine, ending, {1: "missed", 2: "maintenance"})
    async with session(db_engine) as db:
        found = await EvaluationRepository(db, AllowAllPolicy()).earlier(
            SYSTEM,
            [counted.id, ending.id, empty.id],
            CREATED + timedelta(days=10),
            3,
        )

    def days(items: Sequence[Any]) -> list[tuple[int, str]]:
        return sorted(
            {((item.scheduled_for - CREATED).days, item.state) for item in items}
        )

    assert set(found) == {counted.id, ending.id}
    # The newest 3 closed runs that are not maintenance; nothing open, nothing
    # at or after before.
    assert days(found[counted.id]) == [(2, "missed"), (3, "failed"), (5, "missed")]
    # The newest closed run even when it is maintenance.
    assert days(found[ending.id]) == [(1, "missed"), (2, "maintenance")]


async def test_a_verified_run_out_of_the_window_keeps_the_job_ok(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client, expr="30d", schedule_kind="interval")
    due = CREATED + timedelta(days=30)
    await report(db_engine, job, "success", due + timedelta(hours=1))
    at(clock, due + timedelta(hours=2))
    await evaluate_jobs(context, clock.now())
    at(clock, due + timedelta(days=20))
    # Evaluated again (an hour passed) with no run in the window.
    assert (await Evaluator(context).run(clock.now())).evaluated == 1
    record = await record_of(db_engine, job)
    assert record is not None and record.state == "ok"
    names = [(flip.from_state, flip.to_state) for flip in await flips(db_engine)]
    assert names == [("unknown", "ok")]


async def test_a_job_another_worker_evaluated_meanwhile_is_left_out(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = await add_client(db_engine)
    await add_job(db_engine, client)
    at(clock, OVERDUE_AT)
    await evaluate_jobs(context, clock.now())
    at(clock, MISSED_AT)
    async with session(db_engine) as db:
        stale = await EvaluationRepository(db, AllowAllPolicy()).candidates(
            SYSTEM, results_since=MISSED_AT - timedelta(days=30)
        )
    # A second worker (after a lost worker lock) evaluates the job first.
    await evaluate_jobs(context, clock.now())
    before = await snapshot(db_engine)

    async def read_before(self: Any, principal: Any, **kwargs: Any) -> Any:
        return stale

    monkeypatch.setattr(EvaluationRepository, "candidates", read_before)
    tick = await Evaluator(context).run(clock.now())
    assert (tick.due, tick.evaluated, tick.stale, tick.flips) == (1, 0, 1, 0)
    assert await snapshot(db_engine) == before
    (flip,) = await flips(db_engine)
    assert (flip.from_state, flip.to_state) == ("unknown", "missed")


@pytest.mark.parametrize("change", ["pause", "move", "client archive"])
async def test_a_job_changed_meanwhile_is_left_out(
    change: str,
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    other = await add_client(db_engine, "Fictional Law Office")
    at(clock, MISSED_AT)
    async with session(db_engine) as db:
        stale = await EvaluationRepository(db, AllowAllPolicy()).candidates(
            SYSTEM, results_since=MISSED_AT - timedelta(days=30)
        )
    # Committed after the candidates were read, before the batch claims. The
    # move keeps updated_at, so only the client_id tells it.
    job_row = update(Job).where(Job.id == job.id)
    client_row = update(Client).where(Client.id == client.id)
    statements = {
        "pause": job_row.values(enabled=False, updated_at=MISSED_AT),
        "move": job_row.values(client_id=other.id),
        "client archive": client_row.values(archived=True),
    }
    async with session(db_engine) as db:
        await db.execute(statements[change])
        await db.commit()

    async def read_before(self: Any, principal: Any, **kwargs: Any) -> Any:
        return stale

    monkeypatch.setattr(EvaluationRepository, "candidates", read_before)
    tick = await Evaluator(context).run(clock.now())
    assert (tick.due, tick.evaluated, tick.stale, tick.flips) == (1, 0, 1, 0)
    assert await snapshot(db_engine) == [[], [], []]


async def test_a_locked_job_state_row_is_not_taken_for_a_missing_one(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    at(clock, OVERDUE_AT)
    async with session(db_engine) as db:
        stale = await EvaluationRepository(db, AllowAllPolicy()).candidates(
            SYSTEM, results_since=CREATED
        )
    assert stale[0].record is None
    # Another worker evaluated the job first and now evaluates it again.
    await evaluate_jobs(context, clock.now())
    async with session(db_engine) as other:
        held = select(JobStateRecord).where(JobStateRecord.job_id == job.id)
        await other.execute(held.with_for_update())
        async with session(db_engine) as batch:
            # A wait for the held row fails the test instead of hanging it.
            await batch.execute(text("SET LOCAL lock_timeout = '2s'"))
            repository = EvaluationRepository(batch, AllowAllPolicy())
            assert await repository.claim(SYSTEM, stale) == set()
            await batch.rollback()
        await other.rollback()
    # Not locked either: a row the candidates did not see is not fresh.
    async with session(db_engine) as batch:
        repository = EvaluationRepository(batch, AllowAllPolicy())
        assert await repository.claim(SYSTEM, stale) == set()
        await batch.rollback()


async def test_a_client_being_deleted_is_left_out_without_waiting(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    # Without SKIP LOCKED the batch would wait for the delete below for ever;
    # a lock timeout on the worker's connections turns that into an error.
    # The driver runs the SET in a transaction, so commit it: a rollback (the
    # first session closing) would undo it on the pooled connection.
    @event.listens_for(context.engine.sync_engine, "connect")
    def bounded(connection: Any, record: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("SET lock_timeout = '2s'")
        cursor.close()
        connection.commit()

    async with context.sessionmaker() as first:
        await first.execute(text("SELECT 1"))
    async with context.sessionmaker() as second:
        assert await second.scalar(text("SHOW lock_timeout")) == "2s"

    client = await add_client(db_engine)
    await add_job(db_engine, client)
    at(clock, MISSED_AT)
    async with session(db_engine) as deleting:
        clients = ClientRepository(deleting, AllowAllPolicy())
        locked = await clients.get(SYSTEM, client.id, for_update=True)
        assert locked is not None
        tick = await Evaluator(context).run(clock.now())
        assert (tick.evaluated, tick.stale, tick.failed_batches) == (0, 1, 0)
        await clients.delete(SYSTEM, locked)
        await deleting.commit()
    tick = await Evaluator(context).run(clock.now())
    assert (tick.candidates, tick.failed_batches) == (0, 0)
    assert await snapshot(db_engine) == [[], [], []]


async def test_a_client_delete_waits_for_a_batch_that_holds_its_jobs(
    db_engine: AsyncEngine,
) -> None:
    client = await add_client(db_engine)
    job = await add_job(db_engine, client)
    async with session(db_engine) as batch:
        repository = EvaluationRepository(batch, AllowAllPolicy())
        assert await repository.claim(SYSTEM, []) == set()
        candidates = await repository.candidates(SYSTEM, results_since=CREATED)
        assert await repository.claim(SYSTEM, candidates) == {job.id}
        async with session(db_engine) as deleting:
            # A lock timeout instead of a wait: the delete cannot start.
            await deleting.execute(text("SET LOCAL lock_timeout = '200ms'"))
            clients = ClientRepository(deleting, AllowAllPolicy())
            with pytest.raises(DBAPIError):
                await clients.get(SYSTEM, client.id, for_update=True)
        await batch.rollback()
    async with session(db_engine) as deleting:
        clients = ClientRepository(deleting, AllowAllPolicy())
        found = await clients.get(SYSTEM, client.id, for_update=True)
        assert found is not None
        await clients.delete(SYSTEM, found)
        await deleting.commit()
    async with session(db_engine) as db:
        assert await db.get(Job, job.id) is None


async def test_100_clients_with_4_jobs_over_14_days_evaluate_in_under_2_seconds(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    now = datetime(2027, 1, 20, 12, tzinfo=UTC)
    created = now - timedelta(days=20)
    async with session(db_engine) as db:
        for number in range(100):
            name = f"Fictional Client {number:03d}"
            client = Client(name=name, name_key=name_key(name), created_at=created)
            db.add(client)
            await db.flush()
            for kind in range(4):
                job_name = f"Synthetic job {kind}"
                db.add(
                    Job(
                        client_id=client.id,
                        name=job_name,
                        name_key=name_key(job_name),
                        kind="backup",
                        schedule_kind="daily",
                        schedule_expr="23:00",
                        timezone="Europe/Lisbon",
                        ping_token=new_ping_token(),
                        created_at=created,
                        updated_at=created,
                    )
                )
        await db.commit()
    at(clock, now)
    started = time.perf_counter()
    tick = await Evaluator(context).run(now)
    elapsed = time.perf_counter() - started
    assert (tick.candidates, tick.evaluated, tick.failed_batches) == (400, 400, 0)
    assert tick.rows == 400 * 14
    assert elapsed < 2.0, f"{elapsed:.2f} s"
    again = await Evaluator(context).run(now)
    assert (again.due, again.rows) == (0, 0)
