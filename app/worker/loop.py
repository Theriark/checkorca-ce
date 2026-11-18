"""The worker loop.

Phase C0 only keeps the worker process alive and stops cleanly. Phase C4 adds
the advisory lock, the heartbeat, the tick hooks and the SMTP listener on 2525.
"""

import asyncio
import logging

TICK_SECONDS = 60.0

logger = logging.getLogger(__name__)


async def run_worker(stop: asyncio.Event, tick_seconds: float = TICK_SECONDS) -> None:
    """Tick every tick_seconds until stop is set."""
    logger.info("worker started")
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
        except TimeoutError:
            continue
    logger.info("worker stopped")
