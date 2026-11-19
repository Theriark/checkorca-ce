"""The worker loop: one lock for two workers, the heartbeat, tick hooks and
receivers."""

import asyncio
import importlib
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.locks import WORKER_LOCK
from app.db.models import WorkerHeartbeat
from app.settings import load_settings
from app.worker.heartbeat import STALE_AFTER, heartbeat_view
from app.worker.loop import Worker, WorkerContext, build_context, run_worker
from helpers import UNREACHABLE_DATABASE_URL, FakeClock

FAST = {"tick_seconds": 0.05, "lock_retry_seconds": 0.05}


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


async def until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


async def heartbeat(engine: AsyncEngine) -> WorkerHeartbeat | None:
    async with engine.connect() as connection:
        row = (await connection.execute(select(WorkerHeartbeat))).one_or_none()
    return None if row is None else WorkerHeartbeat(**row._mapping)


async def test_one_lock_for_two_workers(
    context: WorkerContext, db_engine: AsyncEngine
) -> None:
    first = Worker(context, hooks=(), receivers=(), holder="first", **FAST)
    second = Worker(context, hooks=(), receivers=(), holder="second", **FAST)
    stop_first, stop_second = asyncio.Event(), asyncio.Event()
    running_first = asyncio.create_task(first.run(stop_first))
    await until(lambda: first.ticks >= 2)
    running_second = asyncio.create_task(second.run(stop_second))
    try:
        # The second worker waits for the lock without ticking.
        await asyncio.sleep(0.4)
        assert first.holds_lock and not second.holds_lock
        assert second.ticks == 0
        row = await heartbeat(db_engine)
        assert row is not None and row.holder == "first"

        # When the first one stops, the second takes over and ticks.
        stop_first.set()
        await asyncio.wait_for(running_first, timeout=5)
        assert not first.holds_lock
        await until(lambda: second.ticks >= 1)
        assert second.holds_lock
        row = await heartbeat(db_engine)
        assert row is not None and row.holder == "second"
    finally:
        stop_first.set()
        stop_second.set()
        await asyncio.wait_for(running_second, timeout=5)
    assert not second.holds_lock


async def test_a_worker_that_loses_its_lock_session_takes_the_lock_again(
    context: WorkerContext, db_engine: AsyncEngine
) -> None:
    worker = Worker(context, hooks=(), receivers=(), holder="only", **FAST)
    stop = asyncio.Event()
    running = asyncio.create_task(worker.run(stop))
    try:
        await until(lambda: worker.ticks >= 1)
        holder = text(
            "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted"
            " AND classid = 0 AND objid = :key AND objsubid = 1"
        )
        async with db_engine.connect() as connection:
            found = await connection.execute(holder, {"key": WORKER_LOCK})
            pid = found.scalar_one()
            await connection.execute(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
            )
            await connection.commit()
        ticks = worker.ticks
        await until(lambda: worker.ticks >= ticks + 2)
        async with db_engine.connect() as connection:
            found = await connection.execute(holder, {"key": WORKER_LOCK})
            assert found.scalar_one() != pid
    finally:
        stop.set()
        await asyncio.wait_for(running, timeout=5)


async def test_a_holder_that_loses_its_session_stops_its_receivers_at_once(
    context: WorkerContext, db_engine: AsyncEngine
) -> None:
    events: list[str] = []
    # A long tick: the loss must be noticed between ticks, not at the next one.
    first = Worker(
        context,
        hooks=(),
        receivers=(lambda context: FakeReceiver("first", events),),
        holder="first",
        tick_seconds=30,
        lock_retry_seconds=0.05,
    )
    second = Worker(context, hooks=(), receivers=(), holder="second", **FAST)
    stop_first, stop_second = asyncio.Event(), asyncio.Event()
    running_first = asyncio.create_task(first.run(stop_first))
    await until(lambda: first.ticks >= 1)
    running_second = asyncio.create_task(second.run(stop_second))
    try:
        await asyncio.sleep(0.2)
        assert second.ticks == 0
        holder = text(
            "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted"
            " AND classid = 0 AND objid = :key AND objsubid = 1"
        )
        async with db_engine.connect() as connection:
            found = await connection.execute(holder, {"key": WORKER_LOCK})
            await connection.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": found.scalar_one()},
            )
            await connection.commit()
        # Within a lock check, not after the 30 second tick.
        await until(lambda: "stop first" in events, timeout=5)
        # Whoever takes the lock next, exactly one worker holds it.
        await until(lambda: first.holds_lock or second.ticks >= 1, timeout=5)
        async with db_engine.connect() as connection:
            found = await connection.execute(holder, {"key": WORKER_LOCK})
            assert len(found.all()) == 1
        # Once the first stops, the second ticks and its heartbeat shows it.
        stop_first.set()
        await asyncio.wait_for(running_first, timeout=5)
        await until(lambda: second.holds_lock and second.ticks >= 1, timeout=5)
        row = await heartbeat(db_engine)
        assert row is not None and row.holder == "second"
    finally:
        stop_first.set()
        stop_second.set()
        await asyncio.wait_for(running_second, timeout=5)
        await asyncio.wait_for(running_first, timeout=5)


async def test_a_tick_writes_the_heartbeat_and_runs_every_hook(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[datetime] = []

    async def broken(context: WorkerContext, now: datetime) -> None:
        raise RuntimeError("hook failure")

    async def records(context: WorkerContext, now: datetime) -> None:
        seen.append(now)

    worker = Worker(context, hooks=(broken, records), receivers=(), holder="tick")
    with caplog.at_level(logging.ERROR, logger="app.worker.loop"):
        await worker.tick()
        clock.advance(seconds=60)
        await worker.tick()
    # A failing hook never stops the tick or the hooks after it.
    assert seen == [clock.now() - timedelta(seconds=60), clock.now()]
    assert worker.ticks == 2
    assert "tick hook" in caplog.text and "broken" in caplog.text
    row = await heartbeat(db_engine)
    assert row is not None
    assert row.beat_at == clock.now()
    assert row.holder == "tick"


async def test_a_failed_heartbeat_is_logged_and_the_hooks_still_run(
    clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    settings = load_settings(database_url=UNREACHABLE_DATABASE_URL)
    context = build_context(settings, clock)
    seen: list[datetime] = []

    async def records(context: WorkerContext, now: datetime) -> None:
        seen.append(now)

    try:
        worker = Worker(context, hooks=(records,), receivers=(), holder="x")
        with caplog.at_level(logging.ERROR, logger="app.worker.loop"):
            await worker.tick()
    finally:
        await context.engine.dispose()
    assert seen == [clock.now()]
    assert "worker heartbeat failed" in caplog.text


class FakeReceiver:
    def __init__(self, name: str, events: list[str], fail_stop: bool = False) -> None:
        self.name = name
        self.events = events
        self.fail_stop = fail_stop

    async def start(self, context: WorkerContext) -> None:
        self.events.append(f"start {self.name}")

    async def stop(self) -> None:
        self.events.append(f"stop {self.name}")
        if self.fail_stop:
            raise RuntimeError("stop failed")


async def test_receivers_run_while_the_lock_is_held(context: WorkerContext) -> None:
    events: list[str] = []

    def broken(context: WorkerContext) -> FakeReceiver:
        raise RuntimeError("cannot bind")

    worker = Worker(
        context,
        hooks=(),
        receivers=(
            lambda context: FakeReceiver("smtp", events),
            broken,
            lambda context: FakeReceiver("imap", events, fail_stop=True),
        ),
        holder="receivers",
        **FAST,
    )
    stop = asyncio.Event()
    running = asyncio.create_task(worker.run(stop))
    await until(lambda: worker.ticks >= 1)
    assert events == ["start smtp", "start imap"]
    stop.set()
    await asyncio.wait_for(running, timeout=5)
    # Stopped in reverse order; a receiver that fails to stop does not stop
    # the others.
    assert events == ["start smtp", "start imap", "stop imap", "stop smtp"]


async def test_the_worker_returns_at_once_when_already_stopped(
    context: WorkerContext,
) -> None:
    stop = asyncio.Event()
    stop.set()
    worker = Worker(context, hooks=(), receivers=(), **FAST)
    await asyncio.wait_for(worker.run(stop), timeout=1)
    assert worker.ticks == 0


async def test_a_worker_without_a_database_keeps_trying_until_stopped(
    clock: FakeClock,
) -> None:
    settings = load_settings(database_url=UNREACHABLE_DATABASE_URL)
    context = build_context(settings, clock)
    worker = Worker(context, hooks=(), receivers=(), **FAST)
    stop = asyncio.Event()
    try:
        running = asyncio.create_task(worker.run(stop))
        await asyncio.sleep(0.3)
        assert not running.done() and worker.ticks == 0
        stop.set()
        await asyncio.wait_for(running, timeout=5)
    finally:
        await context.engine.dispose()


async def test_run_worker_builds_and_disposes_its_context(
    db_engine: AsyncEngine,
) -> None:
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(run_worker(load_settings(), stop), timeout=5)


def test_the_heartbeat_is_stale_after_3_minutes() -> None:
    now = datetime(2027, 1, 4, 9, 0, tzinfo=UTC)
    assert heartbeat_view(None, now).stale
    assert heartbeat_view(None, now).at is None

    def row(age: timedelta) -> WorkerHeartbeat:
        return WorkerHeartbeat(id=1, beat_at=now - age, holder="h", started_at=now)

    assert not heartbeat_view(row(STALE_AFTER - timedelta(seconds=1)), now).stale
    assert heartbeat_view(row(STALE_AFTER), now).stale
    # A heartbeat ahead of this clock (another container's clock) has age 0.
    ahead = heartbeat_view(row(timedelta(seconds=-5)), now)
    assert ahead.age_seconds == 0 and not ahead.stale


@pytest.mark.parametrize("name", ["app.schedule", "app.evaluator", "app.parsers"])
def test_core_packages_exist_for_the_strict_gates(name: str) -> None:
    # mypy strict and the 95 percent coverage gate apply to these packages.
    exported = importlib.import_module(name).__all__
    # The schedule library is built (phase C3); the others are still empty.
    assert bool(exported) == (name == "app.schedule")
