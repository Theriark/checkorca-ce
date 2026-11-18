"""Spike 1: a session-level advisory lock has one holder at a time.

The worker loop of phase C4-B holds one fixed pg_advisory_lock key for as long
as it runs, so two workers never tick together. Two asyncpg sessions show the
three cases it needs: the second session cannot take the key while the first
holds it, it gets the key once the first unlocks, and it gets the key when the
first session ends without unlocking (a worker that crashed).
"""

import asyncio
import time
from collections.abc import Callable

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Spike-only key; migrations/env.py takes 4_270_001 for the migration lock.
KEY = 4_270_901

TRY_LOCK = text("SELECT pg_try_advisory_lock(:key)")
LOCK = text("SELECT pg_advisory_lock(:key)")
UNLOCK = text("SELECT pg_advisory_unlock(:key)")
# A bigint key below 2**32 shows as classid 0, objid key, objsubid 1.
HOLDERS = text(
    "SELECT pid FROM pg_locks"
    " WHERE locktype = 'advisory' AND granted"
    " AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    " AND classid = 0 AND objid = :key AND objsubid = 1"
)


async def call(connection: AsyncConnection, statement: TextClause) -> object:
    return (await connection.execute(statement, {"key": KEY})).scalar_one()


async def backend_pid(connection: AsyncConnection) -> int:
    return int((await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one())


async def holders(connection: AsyncConnection) -> list[int]:
    result = await connection.execute(HOLDERS, {"key": KEY})
    return [int(pid) for pid in result.scalars()]


async def test_second_session_gets_the_key_after_the_first_unlocks(
    engine: AsyncEngine, report: Callable[..., None]
) -> None:
    async with engine.connect() as first, engine.connect() as second:
        first_pid = await backend_pid(first)
        second_pid = await backend_pid(second)
        assert await call(first, TRY_LOCK) is True
        assert await call(second, TRY_LOCK) is False
        assert await holders(first) == [first_pid]

        # pg_advisory_lock blocks the second session behind the first.
        waiting = asyncio.create_task(second.execute(LOCK, {"key": KEY}))
        try:
            await asyncio.sleep(0.3)
            assert not waiting.done()
            released = time.perf_counter()
            assert await call(first, UNLOCK) is True
            await asyncio.wait_for(waiting, timeout=5)
        finally:
            # After a failed assertion the blocked call must not outlive the test.
            waiting.cancel()
        handover_ms = (time.perf_counter() - released) * 1000

        assert await holders(first) == [second_pid]
        # The first session no longer holds it, so it cannot take it either.
        assert await call(first, TRY_LOCK) is False
        assert await call(second, UNLOCK) is True
        assert await holders(first) == []
    report("advisory-lock", handover_ms=f"{handover_ms:.1f}")


async def test_key_is_freed_when_the_holding_session_ends(
    engine: AsyncEngine, report: Callable[..., None]
) -> None:
    async with engine.connect() as second:
        async with engine.connect() as first:
            assert await call(first, TRY_LOCK) is True
            assert await call(second, TRY_LOCK) is False
        # first is closed without an unlock: its server session ends and the
        # server frees the key once the backend has exited.
        closed = time.perf_counter()
        async with asyncio.timeout(5):
            while not await call(second, TRY_LOCK):
                await asyncio.sleep(0.02)
        takeover_ms = (time.perf_counter() - closed) * 1000
        assert await holders(second) == [await backend_pid(second)]
        assert await call(second, UNLOCK) is True
    report("advisory-lock-session-end", takeover_ms=f"{takeover_ms:.1f}")
