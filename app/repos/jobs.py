"""Jobs: what should report, on which schedule, for which client.

Until the evaluator of phase C7 keeps job_state, a job's state is derived
here: paused while it is paused, otherwise unknown.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from sqlalchemy import ColumnElement, and_, false, not_, or_, select, tuple_

from app.access import Principal
from app.db.models import Client, Job, name_key
from app.repos.base import Repository, guarded
from app.repos.clients import contains_pattern
from app.security.tokens import new_ping_token

JobState = Literal[
    "ok", "warning", "failing", "missed", "unknown", "paused", "maintenance"
]
JOB_STATES: Final[tuple[JobState, ...]] = (
    "ok",
    "warning",
    "failing",
    "missed",
    "unknown",
    "paused",
    "maintenance",
)
# Worst first: silent before failed before warning (the dashboard order).
STATE_SEVERITY: Final[tuple[JobState, ...]] = (
    "missed",
    "failing",
    "warning",
    "unknown",
    "maintenance",
    "paused",
    "ok",
)

# The fields update() may change; id, ping_token and created_at never change.
_UPDATABLE: Final = frozenset(
    {
        "client_id",
        "name",
        "kind",
        "parser_pack_id",
        "match_key",
        "schedule_kind",
        "schedule_expr",
        "timezone",
        "max_runtime_minutes",
        "grace_minutes",
        "escalate_minutes",
        "attribution_basis",
        "warning_policy",
        "consecutive_failures_to_alert",
        "enabled",
        "paused_until",
        "archived",
        "updated_at",
    }
)


def is_paused(job: Job, now: datetime) -> bool:
    """Paused until resumed (enabled false) or until paused_until."""
    return not job.enabled or (job.paused_until is not None and job.paused_until > now)


def paused_clause(now: datetime) -> ColumnElement[bool]:
    """is_paused in SQL; never NULL, so its negation is safe."""
    until_later = and_(Job.paused_until.is_not(None), Job.paused_until > now)
    return or_(Job.enabled.is_(False), until_later)


def job_state(job: Job, now: datetime) -> JobState:
    return "paused" if is_paused(job, now) else "unknown"


def worst_state(states: Sequence[JobState]) -> JobState | None:
    present = set(states)
    return next((state for state in STATE_SEVERITY if state in present), None)


@dataclass(frozen=True, slots=True)
class JobFilters:
    """Filters of the job list; None means any."""

    now: datetime
    client_id: uuid.UUID | None = None
    q: str | None = None
    kind: str | None = None
    pack: str | None = None
    state: JobState | None = None
    archived: bool = False


class JobRepository(Repository):
    resource = "job"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        filters: JobFilters,
        after: tuple[str, uuid.UUID] | None,
        limit: int,
    ) -> list[tuple[Job, str]]:
        """Jobs with their client's name, ordered by job name, after the
        (name_key, id) cursor."""
        query = (
            select(Job, Client.name)
            .join(Client, Client.id == Job.client_id)
            .where(Job.archived.is_(filters.archived))
            .order_by(Job.name_key, Job.id)
            .limit(limit)
        )
        if filters.client_id is not None:
            query = query.where(Job.client_id == filters.client_id)
        if filters.q:
            query = query.where(
                Job.name.ilike(contains_pattern(filters.q), escape="\\")
            )
        if filters.kind is not None:
            query = query.where(Job.kind == filters.kind)
        if filters.pack is not None:
            query = query.where(Job.parser_pack_id == filters.pack)
        if filters.state == "paused":
            query = query.where(paused_clause(filters.now))
        elif filters.state == "unknown":
            query = query.where(not_(paused_clause(filters.now)))
        elif filters.state is not None:
            # No job reaches the evaluator's states before phase C7.
            query = query.where(false())
        if after is not None:
            query = query.where(tuple_(Job.name_key, Job.id) > after)
        query = self.policy.scope(principal, self.resource, query)
        return [(job, name) for job, name in (await self.db.execute(query)).all()]

    @guarded("read")
    async def get(
        self, principal: Principal, job_id: uuid.UUID, *, for_update: bool = False
    ) -> Job | None:
        """The job; for_update locks its row until the transaction ends."""
        query = select(Job).where(Job.id == job_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def find(
        self, principal: Principal, client_id: uuid.UUID, name: str
    ) -> Job | None:
        """The client's job with this name, ignoring case and spacing."""
        query = select(Job).where(
            Job.client_id == client_id, Job.name_key == name_key(name)
        )
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("list")
    async def for_clients(
        self, principal: Principal, client_ids: Sequence[uuid.UUID]
    ) -> list[Job]:
        """The jobs of these clients that are not archived."""
        if not client_ids:
            return []
        query = select(Job).where(
            Job.client_id.in_(client_ids), Job.archived.is_(False)
        )
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("export")
    async def export_rows(
        self, principal: Principal, client_id: uuid.UUID | None
    ) -> list[tuple[Job, str]]:
        """Jobs and client names for the CSV export, without archived jobs or
        clients, ordered by client then job."""
        query = (
            select(Job, Client.name)
            .join(Client, Client.id == Job.client_id)
            .where(Job.archived.is_(False), Client.archived.is_(False))
            .order_by(Client.name_key, Job.name_key, Job.id)
        )
        if client_id is not None:
            query = query.where(Job.client_id == client_id)
        query = self.policy.scope(principal, self.resource, query)
        return [(job, name) for job, name in (await self.db.execute(query)).all()]

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        client_id: uuid.UUID,
        name: str,
        now: datetime,
        **fields: Any,
    ) -> Job:
        """A new job with a fresh ping token; fields are the job's settings."""
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot set {sorted(unknown)}")
        job = Job(
            client_id=client_id,
            name=name,
            name_key=name_key(name),
            ping_token=new_ping_token(),
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    @guarded("update")
    async def update(self, principal: Principal, job: Job, **changes: Any) -> None:
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for field, value in changes.items():
            setattr(job, field, value)
        if "name" in changes:
            job.name_key = name_key(changes["name"])
        await self.db.flush()
