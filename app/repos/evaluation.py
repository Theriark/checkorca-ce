"""The evaluator's tables (phase C7): occurrence, job_state and flip.

EvaluationRepository is the worker's: it reads the jobs that may need an
evaluation, their occurrences and results, and writes what the evaluator
decided. OccurrenceRepository, FlipRepository and JobStateRepository serve
the API. Nothing else writes these tables except the client delete map.
"""

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, func, insert, select, true, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.access import Principal
from app.db.models import (
    Client,
    Flip,
    Job,
    JobResult,
    JobStateRecord,
    Occurrence,
)
from app.evaluator import model as values
from app.ingest.results import ResultStatus
from app.repos.base import Repository, guarded


@dataclass(frozen=True, slots=True)
class Candidate:
    """A job with what decides whether it needs an evaluation: its client's
    archived flag, its job_state row, and the count and newest receipt time
    of its recent results."""

    job: Job
    client_archived: bool
    record: JobStateRecord | None
    result_count: int
    result_last_at: datetime | None


@dataclass(frozen=True, slots=True)
class Changes:
    """Rows to write in one transaction, as column values."""

    inserts: Sequence[dict[str, Any]] = ()
    updates: Sequence[dict[str, Any]] = ()
    deletes: Sequence[tuple[uuid.UUID, datetime]] = ()
    records: Sequence[dict[str, Any]] = ()
    flips: Sequence[dict[str, Any]] = ()


# job_state columns an upsert replaces (all but the key).
_RECORD_COLUMNS = tuple(
    column.name
    for column in JobStateRecord.__table__.columns
    if column.name != "job_id"
)
# Closed states that count in a run of failures or end it.
_COUNTED_STATES = frozenset(
    state for state in values.CLOSED_STATES if state != "maintenance"
)


class EvaluationRepository(Repository):
    resource = "evaluation"

    @guarded("list")
    async def candidates(
        self, principal: Principal, *, results_since: datetime
    ) -> list[Candidate]:
        """Every job, archived ones too (an archive must be noticed), with the
        counts of its results received since results_since."""
        counts = (
            select(
                JobResult.job_id.label("job_id"),
                func.count().label("result_count"),
                func.max(JobResult.received_at).label("result_last_at"),
            )
            .where(
                JobResult.job_id.is_not(None), JobResult.received_at >= results_since
            )
            .group_by(JobResult.job_id)
            .subquery()
        )
        query = (
            select(
                Job,
                Client.archived,
                JobStateRecord,
                counts.c.result_count,
                counts.c.result_last_at,
            )
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobStateRecord, JobStateRecord.job_id == Job.id)
            .outerjoin(counts, counts.c.job_id == Job.id)
            .order_by(Job.id)
        )
        query = self.policy.scope(principal, self.resource, query)
        rows = await self.db.execute(query)
        return [
            Candidate(
                job=job,
                client_archived=archived,
                record=record,
                result_count=count or 0,
                result_last_at=last,
            )
            for job, archived, record, count, last in rows
        ]

    @guarded("list")
    async def occurrences(
        self, principal: Principal, job_ids: Sequence[uuid.UUID], since: datetime
    ) -> dict[uuid.UUID, list[values.Occurrence]]:
        """The stored occurrences of these jobs due at or after since, oldest
        first, per job."""
        query = (
            select(
                Occurrence.job_id,
                Occurrence.scheduled_for,
                Occurrence.deadline,
                Occurrence.state,
                Occurrence.result_id,
                Occurrence.note,
            )
            .where(Occurrence.job_id.in_(job_ids), Occurrence.scheduled_for >= since)
            .order_by(Occurrence.job_id, Occurrence.scheduled_for)
        )
        query = self.policy.scope(principal, self.resource, query)
        found: dict[uuid.UUID, list[values.Occurrence]] = defaultdict(list)
        for row in await self.db.execute(query):
            found[row.job_id].append(
                values.Occurrence(
                    scheduled_for=row.scheduled_for,
                    deadline=row.deadline,
                    state=values.as_occurrence_state(row.state),
                    result_id=row.result_id,
                    note=row.note,
                )
            )
        return dict(found)

    @guarded("list")
    async def earlier(
        self,
        principal: Principal,
        job_ids: Sequence[uuid.UUID],
        before: datetime,
        limit: int,
    ) -> dict[uuid.UUID, list[values.Occurrence]]:
        """For each of these jobs, the closed occurrences due before before
        that the job state can still depend on (machine.earlier_view): the
        newest limit that are not maintenance, and the newest one. Each job
        reads at most limit + 1 rows (a LATERAL join over the jobs, each an
        index scan backwards on the primary key)."""
        jobs = select(Job.id.label("job_id")).where(Job.id.in_(job_ids)).subquery()
        found: dict[uuid.UUID, list[values.Occurrence]] = defaultdict(list)
        for states, count in ((_COUNTED_STATES, limit), (values.CLOSED_STATES, 1)):
            newest = (
                select(
                    Occurrence.scheduled_for,
                    Occurrence.deadline,
                    Occurrence.state,
                    Occurrence.result_id,
                    Occurrence.note,
                )
                .where(
                    Occurrence.job_id == jobs.c.job_id,
                    Occurrence.scheduled_for < before,
                    Occurrence.state.in_(sorted(states)),
                )
                .order_by(Occurrence.scheduled_for.desc())
                .limit(count)
                .lateral()
            )
            query = select(jobs.c.job_id, newest).join(newest, true())
            query = self.policy.scope(principal, self.resource, query)
            for row in await self.db.execute(query):
                found[row.job_id].append(
                    values.Occurrence(
                        scheduled_for=row.scheduled_for,
                        deadline=row.deadline,
                        state=values.as_occurrence_state(row.state),
                        result_id=row.result_id,
                        note=row.note,
                    )
                )
        return dict(found)

    @guarded("update")
    async def claim(
        self, principal: Principal, batch: Sequence[Candidate]
    ) -> set[uuid.UUID]:
        """Lock the batch for the caller's transaction and return the ids of
        the jobs still as the candidates saw them.

        Takes the clients and the jobs FOR KEY SHARE (what the occurrence,
        job_state and flip rows written later need) and the job_state rows
        FOR UPDATE, all with SKIP LOCKED, so a batch never waits for a lock
        and never deadlocks with the API. Left out, for the next tick: a job
        that is gone; a job whose client or job row is locked FOR UPDATE (a
        client delete or a job change in progress; a delete that comes later
        waits for this batch, so it deletes the batch's rows too); a job
        whose job_state row is locked or changed since the candidates were
        read (another worker evaluates it, after a lost worker lock).
        """
        if not batch:
            return set()
        client_ids = sorted({item.job.client_id for item in batch})
        job_ids = sorted(item.job.id for item in batch)
        clients = set(
            await self.db.scalars(
                select(Client.id)
                .where(Client.id.in_(client_ids))
                .order_by(Client.id)
                .with_for_update(read=True, key_share=True, skip_locked=True)
            )
        )
        jobs = set(
            await self.db.scalars(
                select(Job.id)
                .where(Job.id.in_(job_ids))
                .order_by(Job.id)
                .with_for_update(read=True, key_share=True, skip_locked=True)
            )
        )
        rows = await self.db.execute(
            select(JobStateRecord.job_id, JobStateRecord.evaluated_at)
            .where(JobStateRecord.job_id.in_(job_ids))
            .order_by(JobStateRecord.job_id)
            .with_for_update(skip_locked=True)
        )
        evaluated = {row.job_id: row.evaluated_at for row in rows}
        fresh: set[uuid.UUID] = set()
        for item in batch:
            seen = None if item.record is None else item.record.evaluated_at
            locked = item.job.client_id in clients and item.job.id in jobs
            if locked and evaluated.get(item.job.id) == seen:
                fresh.add(item.job.id)
        return fresh

    @guarded("list")
    async def results(
        self, principal: Principal, job_ids: Sequence[uuid.UUID], since: datetime
    ) -> dict[uuid.UUID, list[values.Result]]:
        """The results bound to these jobs received at or after since, per job
        (only the columns the evaluator reads)."""
        query = select(
            JobResult.job_id,
            JobResult.id,
            JobResult.status,
            JobResult.started_at,
            JobResult.finished_at,
            JobResult.received_at,
        ).where(JobResult.job_id.in_(job_ids), JobResult.received_at >= since)
        query = self.policy.scope(principal, self.resource, query)
        found: dict[uuid.UUID, list[values.Result]] = defaultdict(list)
        for row in await self.db.execute(query):
            found[row.job_id].append(
                values.Result(
                    id=row.id,
                    status=cast(ResultStatus, row.status),
                    received_at=row.received_at,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                )
            )
        return dict(found)

    @guarded("update")
    async def save(self, principal: Principal, changes: Changes) -> None:
        """Write the changes; the caller commits."""
        if changes.deletes:
            key = tuple_(Occurrence.job_id, Occurrence.scheduled_for)
            await self.db.execute(
                delete(Occurrence).where(key.in_(list(changes.deletes)))
            )
        if changes.inserts:
            await self.db.execute(insert(Occurrence), list(changes.inserts))
        if changes.updates:
            await self.db.execute(update(Occurrence), list(changes.updates))
        if changes.records:
            upsert = pg_insert(JobStateRecord)
            upsert = upsert.on_conflict_do_update(
                index_elements=[JobStateRecord.job_id],
                set_={name: upsert.excluded[name] for name in _RECORD_COLUMNS},
            )
            await self.db.execute(upsert, list(changes.records))
        if changes.flips:
            await self.db.execute(insert(Flip), list(changes.flips))


class OccurrenceRepository(Repository):
    resource = "occurrence"

    @guarded("list")
    async def between(
        self,
        principal: Principal,
        job_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
        after: datetime | None,
        limit: int,
    ) -> list[Occurrence]:
        """The job's occurrences due in [start, end), oldest first, after the
        scheduled_for cursor."""
        query = (
            select(Occurrence)
            .where(
                Occurrence.job_id == job_id,
                Occurrence.scheduled_for >= start,
                Occurrence.scheduled_for < end,
            )
            .order_by(Occurrence.scheduled_for)
            .limit(limit)
        )
        if after is not None:
            query = query.where(Occurrence.scheduled_for > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())


class FlipRepository(Repository):
    resource = "flip"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        job_id: uuid.UUID | None,
        client_id: uuid.UUID | None,
        since: datetime | None,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[Flip]:
        """Flips, newest first, before the (at, id) cursor; job_id, client_id
        and since (at or after) narrow the list."""
        query = select(Flip).order_by(Flip.at.desc(), Flip.id.desc()).limit(limit)
        if job_id is not None:
            query = query.where(Flip.job_id == job_id)
        if client_id is not None:
            query = query.where(Flip.client_id == client_id)
        if since is not None:
            query = query.where(Flip.at >= since)
        if after is not None:
            query = query.where(tuple_(Flip.at, Flip.id) < after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())


class JobStateRepository(Repository):
    resource = "job_state"

    @guarded("list")
    async def for_jobs(
        self, principal: Principal, job_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, JobStateRecord]:
        """The evaluator's record of each of these jobs that has one."""
        if not job_ids:
            return {}
        query = select(JobStateRecord).where(JobStateRecord.job_id.in_(job_ids))
        query = self.policy.scope(principal, self.resource, query)
        return {record.job_id: record for record in await self.db.scalars(query)}
