"""The worker lock: one session-level PostgreSQL advisory lock (WORKER_LOCK).

The lock lives on one dedicated connection in autocommit mode (no transaction
stays open). It is held while that server session lives: an unlock, a closed
connection or a crashed process frees it, and a waiting worker takes it on its
next try (spike 1, docs/spikes.md). The connection is never given back to the
pool, where it would keep the lock.
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db.locks import WORKER_LOCK

TRY_LOCK = text("SELECT pg_try_advisory_lock(:key)")
UNLOCK = text("SELECT pg_advisory_unlock(:key)")
# A dead connection must not stall the loop.
CHECK_TIMEOUT_SECONDS = 10.0

logger = logging.getLogger(__name__)


async def wait_for_stop(stop: asyncio.Event, seconds: float) -> bool:
    """Wait up to seconds; True when stop was set."""
    if stop.is_set():
        return True
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(seconds, 0.0))
    except TimeoutError:
        return False
    return True


class WorkerLock:
    """Take, check and release the worker's advisory lock."""

    def __init__(self, engine: AsyncEngine, key: int = WORKER_LOCK) -> None:
        self._engine = engine
        self._key = key
        self._connection: AsyncConnection | None = None
        self.held = False

    async def acquire(self, stop: asyncio.Event, retry_seconds: float) -> bool:
        """Try until the lock is ours (True) or stop is set (False).

        A worker that finds the lock taken logs it once and keeps trying every
        retry_seconds; a database error is logged and retried the same way.
        """
        told = False
        while not stop.is_set():
            try:
                if await self._try():
                    self.held = True
                    return True
                if not told:
                    logger.info("worker waits: another worker holds the lock")
                    told = True
            except Exception as error:
                logger.warning("worker lock attempt failed", exc_info=error)
                await self._close()
            if await wait_for_stop(stop, retry_seconds):
                break
        return False

    async def _try(self) -> bool:
        if self._connection is None:
            connection = await self._engine.connect()
            self._connection = await connection.execution_options(
                isolation_level="AUTOCOMMIT"
            )
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            result = await self._connection.execute(TRY_LOCK, {"key": self._key})
        return bool(result.scalar_one())

    async def still_held(self) -> bool:
        """True while the lock's connection answers; a lost connection means
        the server has freed the lock."""
        if self._connection is None or not self.held:
            return False
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                await self._connection.execute(text("SELECT 1"))
        except Exception as error:
            logger.error("worker lost the lock connection", exc_info=error)
            self.held = False
            await self._close()
            return False
        return True

    async def release(self) -> None:
        """Unlock and close the connection; safe to call more than once."""
        if self._connection is not None and self.held:
            try:
                async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                    await self._connection.execute(UNLOCK, {"key": self._key})
            except Exception as error:
                # Closing the connection below frees the lock anyway.
                logger.warning("worker unlock failed", exc_info=error)
        self.held = False
        await self._close()

    async def _close(self) -> None:
        """Discard the connection. Invalidated, not returned to the pool: a
        pooled connection would keep a lock that an unlock failed to free."""
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            await connection.invalidate()
            await connection.close()
        except Exception as error:
            logger.warning("closing the lock connection failed", exc_info=error)
