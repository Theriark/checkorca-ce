"""How fresh the worker heartbeat is: /readyz and System status read it.

The worker writes the heartbeat every 60 seconds; older than 3 minutes is
stale (rnd-report-2 5.10 and 5.11), and so is no heartbeat at all.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.access import SYSTEM, AccessPolicy
from app.db.models import WorkerHeartbeat
from app.repos.heartbeat import HeartbeatRepository

STALE_AFTER: Final = timedelta(minutes=3)


@dataclass(frozen=True, slots=True)
class HeartbeatView:
    at: datetime | None
    age_seconds: float | None
    stale: bool
    holder: str | None
    started_at: datetime | None


def heartbeat_view(row: WorkerHeartbeat | None, now: datetime) -> HeartbeatView:
    """The heartbeat as of now; a heartbeat from the future has age 0."""
    if row is None:
        return HeartbeatView(None, None, True, None, None)
    age = max(now - row.beat_at, timedelta(0))
    return HeartbeatView(
        at=row.beat_at,
        age_seconds=round(age.total_seconds(), 3),
        stale=age >= STALE_AFTER,
        holder=row.holder,
        started_at=row.started_at,
    )


async def read_heartbeat(
    sessionmaker: async_sessionmaker[AsyncSession],
    policy: AccessPolicy,
    now: datetime,
) -> HeartbeatView:
    async with sessionmaker() as db:
        row = await HeartbeatRepository(db, policy).get(SYSTEM)
    return heartbeat_view(row, now)
