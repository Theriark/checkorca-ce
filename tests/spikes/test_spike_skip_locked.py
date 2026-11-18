"""Spike 2: SELECT ... FOR UPDATE SKIP LOCKED hands out disjoint rows.

From phase C5-B the worker claims pending raw messages this way. Two sessions
that claim a batch at the same time get different rows, and several concurrent
workers that drain a queue claim every row exactly once.

The table lives in its own schema, dropped after each test, so the Alembic
spike (which compares the public schema with the models) never sees it.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ROWS = 40
WORKERS = 4

CLAIM_BATCH = text(
    "SELECT id FROM spike_c0b.queue WHERE claimed_by IS NULL"
    " ORDER BY id LIMIT :size FOR UPDATE SKIP LOCKED"
)
CREATE_QUEUE = text(
    "CREATE TABLE spike_c0b.queue (id integer PRIMARY KEY, claimed_by text)"
)
MARK = text("UPDATE spike_c0b.queue SET claimed_by = :worker WHERE id = :id")


@pytest.fixture
async def queue(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS spike_c0b CASCADE"))
        await connection.execute(text("CREATE SCHEMA spike_c0b"))
        await connection.execute(CREATE_QUEUE)
        await connection.execute(
            text("INSERT INTO spike_c0b.queue (id) SELECT generate_series(1, :rows)"),
            {"rows": ROWS},
        )
    yield
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA spike_c0b CASCADE"))


async def test_two_sessions_claim_disjoint_batches(
    engine: AsyncEngine, queue: None
) -> None:
    async with engine.connect() as first, engine.connect() as second:
        first_rows = list((await first.execute(CLAIM_BATCH, {"size": 4})).scalars())
        second_rows = list((await second.execute(CLAIM_BATCH, {"size": 4})).scalars())
        assert first_rows == [1, 2, 3, 4]
        assert second_rows == [5, 6, 7, 8]

        # When the first transaction ends without claiming, its rows come back.
        await first.rollback()
        again = list((await first.execute(CLAIM_BATCH, {"size": 8})).scalars())
        assert again == [1, 2, 3, 4, 9, 10, 11, 12]


async def claim_until_empty(
    engine: AsyncEngine, worker: str, claims: list[tuple[str, int]]
) -> None:
    async with engine.connect() as connection:
        while True:
            async with connection.begin():
                result = await connection.execute(CLAIM_BATCH, {"size": 1})
                row = result.scalar_one_or_none()
                if row is None:
                    return
                await connection.execute(MARK, {"worker": worker, "id": row})
                # Hold the row lock a moment so the other workers must skip it.
                await asyncio.sleep(0.01)
            claims.append((worker, row))


async def test_concurrent_workers_claim_every_row_exactly_once(
    engine: AsyncEngine, queue: None, report: Callable[..., None]
) -> None:
    claims: list[tuple[str, int]] = []
    started = time.perf_counter()
    async with asyncio.timeout(30):
        await asyncio.gather(
            *(claim_until_empty(engine, f"w{n}", claims) for n in range(WORKERS))
        )
    elapsed_ms = (time.perf_counter() - started) * 1000

    ids = [row for _, row in claims]
    assert sorted(ids) == list(range(1, ROWS + 1))
    assert len({worker for worker, _ in claims}) >= 2
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT id, claimed_by FROM spike_c0b.queue ORDER BY id")
        )
        assert sorted(claims, key=lambda claim: claim[1]) == [
            (worker, row) for row, worker in rows
        ]
    per_worker = {
        worker: sum(1 for name, _ in claims if name == worker)
        for worker in sorted({worker for worker, _ in claims})
    }
    report(
        "skip-locked",
        rows=ROWS,
        workers=WORKERS,
        per_worker=per_worker,
        elapsed_ms=f"{elapsed_ms:.1f}",
    )
