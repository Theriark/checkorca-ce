"""Job results: one row per reported run, bound to a job or still unmatched."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, tuple_

from app.access import Principal
from app.db.models import JobResult
from app.repos.base import Repository, guarded


class JobResultRepository(Repository):
    resource = "job_result"

    @guarded("create")
    async def create(self, principal: Principal, **fields: Any) -> JobResult:
        result = JobResult(**fields)
        self.db.add(result)
        await self.db.flush()
        return result

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        job_id: uuid.UUID | None = None,
        status: str | None = None,
        raw_message_id: uuid.UUID | None = None,
        after: tuple[datetime, uuid.UUID] | None = None,
        limit: int,
    ) -> list[JobResult]:
        """Results, newest first, before the (received_at, id) cursor."""
        query = (
            select(JobResult)
            .order_by(JobResult.received_at.desc(), JobResult.id.desc())
            .limit(limit)
        )
        if job_id is not None:
            query = query.where(JobResult.job_id == job_id)
        if status is not None:
            query = query.where(JobResult.status == status)
        if raw_message_id is not None:
            query = query.where(JobResult.raw_message_id == raw_message_id)
        if after is not None:
            query = query.where(tuple_(JobResult.received_at, JobResult.id) < after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())
