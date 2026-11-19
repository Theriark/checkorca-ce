"""The worker heartbeat: one row, written on every tick by the lock holder."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.access import Principal
from app.db.models import WorkerHeartbeat
from app.repos.base import Repository, guarded


class HeartbeatRepository(Repository):
    resource = "worker_heartbeat"

    @guarded("read")
    async def get(self, principal: Principal) -> WorkerHeartbeat | None:
        query = select(WorkerHeartbeat)
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("update")
    async def beat(
        self, principal: Principal, *, at: datetime, holder: str, started_at: datetime
    ) -> None:
        """Write the single row (insert it the first time)."""
        values = {"beat_at": at, "holder": holder, "started_at": started_at}
        statement = insert(WorkerHeartbeat).values(id=1, **values)
        statement = statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.id], set_=values
        )
        await self.db.execute(statement)
