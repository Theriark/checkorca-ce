"""What phase C8-B adds to the evaluator hook, on PostgreSQL: a flip clears
the job's acknowledgement, and an evaluation can be limited to some jobs
(the demo seed replays its own).

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models import Client, Flip, Job, JobStateRecord, Occurrence, name_key
from app.evaluator.tick import Evaluator, evaluate_jobs
from app.security.tokens import new_ping_token
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import FakeClock

CREATED = datetime(2027, 1, 4, 12, tzinfo=UTC)
# Daily 23:00 Europe/Lisbon: overdue at 07:00Z, missed from 07:30Z.
OVERDUE_AT = datetime(2027, 1, 5, 7, tzinfo=UTC)
MISSED_AT = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


def at(clock: FakeClock, moment: datetime) -> None:
    clock.advance(seconds=(moment - clock.now()).total_seconds())


async def add_job(engine: AsyncEngine, name: str, **fields: Any) -> Job:
    """A daily 23:00 job of a new client, created at CREATED."""
    client_name = f"Fictional Client of {name}"
    client = Client(
        name=client_name, name_key=name_key(client_name), created_at=CREATED
    )
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        db.add(client)
        await db.flush()
        job = Job(
            client_id=client.id,
            name=name,
            name_key=name_key(name),
            kind="backup",
            schedule_kind="daily",
            schedule_expr="23:00",
            timezone="Europe/Lisbon",
            ping_token=new_ping_token(),
            created_at=CREATED,
            updated_at=CREATED,
            **fields,
        )
        db.add(job)
        await db.commit()
    return job


async def stored(engine: AsyncEngine, job: Job) -> Job:
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        found = await db.get(Job, job.id)
    assert found is not None
    return found


async def test_a_flip_clears_the_acknowledgement(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    job = await add_job(db_engine, "Nightly server backup", acknowledged_at=CREATED)
    at(clock, OVERDUE_AT)
    await evaluate_jobs(context, clock.now())
    assert (await stored(db_engine, job)).acknowledged_at == CREATED
    at(clock, MISSED_AT)
    await evaluate_jobs(context, clock.now())
    async with async_sessionmaker(db_engine)() as db:
        (flip,) = (await db.scalars(select(Flip))).all()
    assert (flip.job_id, flip.to_state) == (job.id, "missed")
    after = await stored(db_engine, job)
    assert (after.acknowledged_at, after.acknowledged_by) == (None, None)
    # Not a change of settings: the evaluator does not take it for one.
    assert after.updated_at == CREATED


async def test_only_limits_the_evaluation_to_those_jobs(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    chosen = await add_job(db_engine, "Nightly server backup")
    other = await add_job(db_engine, "Weekly archive")
    at(clock, MISSED_AT)
    tick = await Evaluator(context, only=frozenset({chosen.id})).run(clock.now())
    assert (tick.candidates, tick.evaluated) == (1, 1)
    async with async_sessionmaker(db_engine)() as db:
        assert await db.get(JobStateRecord, chosen.id) is not None
        assert await db.get(JobStateRecord, other.id) is None
        query = select(Occurrence).where(Occurrence.job_id == other.id)
        assert (await db.scalars(query)).all() == []
