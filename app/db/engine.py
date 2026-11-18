"""The async SQLAlchemy engine on asyncpg and the readiness probe."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger(__name__)


def make_engine(url: str) -> AsyncEngine:
    """Create the engine. It opens no connection until first use.

    hide_parameters keeps bound values (addresses, hashes) out of the text of
    database errors, which can reach a log outside a request (D-6).
    """
    return create_async_engine(
        url, pool_pre_ping=True, pool_size=5, max_overflow=5, hide_parameters=True
    )


async def check_database(engine: AsyncEngine, timeout: float = 3.0) -> bool:
    """True when a trivial query answers within the timeout."""
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as error:  # any failure means not ready
        # Only the class name: driver messages can carry host names or users.
        logger.warning("database check failed: %s", type(error).__name__)
        return False
    return True
