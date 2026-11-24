"""Job results: one row per reported run, bound to a job or still unmatched."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, tuple_, update

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
        unmatched: bool = False,
        after: tuple[datetime, uuid.UUID] | None = None,
        limit: int,
    ) -> list[JobResult]:
        """Results, newest first, before the (received_at, id) cursor;
        unmatched: only those no job is bound to."""
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
        if unmatched:
            query = query.where(JobResult.job_id.is_(None))
        if after is not None:
            query = query.where(tuple_(JobResult.received_at, JobResult.id) < after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, result_id: uuid.UUID, *, for_update: bool = False
    ) -> JobResult | None:
        """The result; for_update locks its row until the transaction ends."""
        query = select(JobResult).where(JobResult.id == result_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("list")
    async def unmatched_count(self, principal: Principal) -> int:
        """How many results no job is bound to (the Unmatched queue)."""
        query = select(func.count()).select_from(JobResult).where(
            JobResult.job_id.is_(None)
        )
        query = self.policy.scope(principal, self.resource, query)
        return int((await self.db.execute(query)).scalar_one())

    @guarded("list")
    async def named(
        self, principal: Principal, *, unmatched: bool, limit: int
    ) -> list[JobResult]:
        """The newest results that name a job (job_name set), for the matcher
        to compare in Python; unmatched: only those no job is bound to."""
        query = (
            select(JobResult)
            .where(JobResult.job_name.is_not(None))
            .order_by(JobResult.received_at.desc(), JobResult.id.desc())
            .limit(limit)
        )
        if unmatched:
            query = query.where(JobResult.job_id.is_(None))
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("update")
    async def bind(
        self, principal: Principal, result: JobResult, job_id: uuid.UUID
    ) -> None:
        """Bind the result to a job (assign, create-job and the matcher)."""
        result.job_id = job_id
        await self.db.flush()

    @guarded("update")
    async def bind_unbound(
        self, principal: Principal, result_ids: Sequence[uuid.UUID], job_id: uuid.UUID
    ) -> list[uuid.UUID | None]:
        """Bind those of the results that are still unbound, in one statement,
        and give their raw message ids. A result another transaction holds is
        skipped (FOR UPDATE SKIP LOCKED), never waited for: two assigns that
        each hold the result the other would bind cannot deadlock, and the
        result stays with the transaction that holds it. A result another
        transaction bound and committed keeps its job (job_id IS NULL)."""
        if not result_ids:
            return []
        free = (
            select(JobResult.id)
            .where(JobResult.id.in_(result_ids), JobResult.job_id.is_(None))
            .with_for_update(skip_locked=True)
        )
        statement = (
            update(JobResult)
            .where(JobResult.id.in_(free), JobResult.job_id.is_(None))
            .values(job_id=job_id)
            .returning(JobResult.raw_message_id)
        )
        return list((await self.db.scalars(statement)).all())
