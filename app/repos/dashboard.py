"""What the Morning check reads (phase C8-B): counts of due runs, the
needs-attention list, the Night Ribbon, the trend, the breakdown, the
activity timeline, and the rows of the CSV exports and the digest.

Each method runs a fixed number of queries, whatever the number of clients
and jobs (tests/api/test_dashboard_api.py counts them). The dashboard reads
live jobs only: a job that is archived, or whose client is archived, is left
out. The exports keep them: history is history.

A due run is an occurrence whose outcome is known or late: verified, warning,
failed, overdue or missed. Pending and running ones are still waiting;
maintenance is neither good nor bad. Silent means overdue or missed.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final, Literal

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Integer,
    SQLColumnExpression,
    and_,
    case,
    cast,
    func,
    literal,
    not_,
    or_,
    select,
    true,
    tuple_,
)
from sqlalchemy.orm import defer

from app.access import Principal
from app.db.models import (
    AuditEvent,
    Client,
    Flip,
    Inbox,
    Job,
    JobResult,
    JobStateRecord,
    Occurrence,
    ParserPack,
    RawMessage,
)
from app.repos.base import Repository, guarded
from app.repos.jobs import paused_clause

DAY: Final = timedelta(days=1)
DAY_SECONDS: Final = 86400
DUE_STATES: Final[tuple[str, ...]] = (
    "verified",
    "warning",
    "failed",
    "overdue",
    "missed",
)
SILENT_STATES: Final[tuple[str, ...]] = ("overdue", "missed")
# Job states that put a job on the needs-attention list (an overdue run does
# too, whatever the job state).
ATTENTION_JOB_STATES: Final[tuple[str, ...]] = ("missed", "failing", "warning")
# Audit actions shown as config activity: changes to what is monitored, not
# sign-ins or the seed.
CONFIG_PREFIXES: Final[tuple[str, ...]] = (
    "client.",
    "job.",
    "inbox.",
    "pack.",
    "unmatched.",
    "token.",
    "user.",
)
BreakdownBy = Literal["vendor", "client"]
ActivityKind = Literal["ingest", "flip", "notification", "config"]


def live() -> ColumnElement[bool]:
    """The job and its client are not archived (Job and Client joined)."""
    return and_(Job.archived.is_(False), Client.archived.is_(False))


def _moment(value: datetime) -> ColumnElement[datetime]:
    return literal(value, DateTime(timezone=True))


def _age_days(
    now: datetime, column: SQLColumnExpression[datetime]
) -> ColumnElement[int]:
    """Whole days from column to now: 0 for the 24 hours up to now (a time
    after now counts as 0 too)."""
    seconds = func.extract("epoch", _moment(now) - column)
    return cast(func.greatest(func.floor(seconds / DAY_SECONDS), 0), Integer)


@dataclass(frozen=True, slots=True)
class AttentionRow:
    """A live job that needs a look. occurrence_state, deadline and
    raw_message_id are of its newest due run."""

    client_id: uuid.UUID
    client_name: str
    job_id: uuid.UUID
    job_name: str
    job_state: str | None
    occurrence_state: str | None
    deadline: datetime | None
    last_success_at: datetime | None
    raw_message_id: uuid.UUID | None
    acknowledged_at: datetime | None


@dataclass(frozen=True, slots=True)
class RibbonRow:
    """One stored occurrence with its job and client."""

    client_id: uuid.UUID
    client_name: str
    job_id: uuid.UUID
    job_name: str
    scheduled_for: datetime
    deadline: datetime
    state: str
    result_at: datetime | None


@dataclass(frozen=True, slots=True)
class LiveJob:
    """A live job that is not paused, for the runs still expected."""

    job: Job
    client_name: str
    eval_from: datetime | None


@dataclass(frozen=True, slots=True)
class BreakdownRow:
    key: str | None
    label: str | None
    verified: int
    failed: int
    silent: int


@dataclass(frozen=True, slots=True)
class ActivityRow:
    """One entry of the timeline, from a flip, a message or an audit event."""

    id: uuid.UUID
    at: datetime
    kind: ActivityKind
    summary: str
    ref_kind: str | None
    ref_id: str | None


@dataclass(frozen=True, slots=True)
class HistoryRow:
    """One occurrence with its job, its client and the result that decided
    it, for the CSV exports and the digest."""

    client_id: uuid.UUID
    client_name: str
    job_id: uuid.UUID
    job_name: str
    job_kind: str
    parser_pack_id: str | None
    scheduled_for: datetime
    deadline: datetime
    state: str
    note: str | None
    result_status: str | None
    started_at: datetime | None
    finished_at: datetime | None
    received_at: datetime | None


@dataclass(frozen=True, slots=True)
class ClientHistory:
    """Everything recorded for one client (legal D-4), oldest first."""

    client: Client
    jobs: Sequence[tuple[Job, str | None]]
    occurrences: Sequence[HistoryRow]
    results: Sequence[tuple[JobResult, str | None]]
    flips: Sequence[tuple[Flip, str]]
    messages: Sequence[RawMessage]


def _summary_of_action(action: str) -> str:
    """The words of an audit action: job.pause gives Job pause."""
    words = action.replace(".", " ").replace("_", " ").strip()
    return words[:1].upper() + words[1:]


class DashboardRepository(Repository):
    resource = "dashboard"

    @guarded("list")
    async def due_counts(
        self, principal: Principal, *, now: datetime, days: int
    ) -> dict[tuple[int, str], int]:
        """Due runs of live jobs by (day, state). Day 0 is the 24 hours up to
        now (scheduled_for in (now - 24 h, now]), day 1 the 24 hours before,
        and so on up to day days - 1."""
        rows = (
            select(
                _age_days(now, Occurrence.scheduled_for).label("day"),
                Occurrence.state.label("state"),
            )
            .select_from(Occurrence)
            .join(Job, Job.id == Occurrence.job_id)
            .join(Client, Client.id == Job.client_id)
            .where(
                Occurrence.scheduled_for > now - days * DAY,
                Occurrence.scheduled_for <= now,
                Occurrence.state.in_(DUE_STATES),
                live(),
            )
        )
        rows = self.policy.scope(principal, self.resource, rows)
        found = rows.subquery()
        query = select(found.c.day, found.c.state, func.count()).group_by(
            found.c.day, found.c.state
        )
        return {
            (int(day), str(state)): int(count)
            for day, state, count in await self.db.execute(query)
        }

    @guarded("list")
    async def unmatched_counts(
        self, principal: Principal, *, now: datetime, days: int
    ) -> dict[int, int]:
        """Results waiting in Unmatched now, by the day they arrived (day 0:
        the last 24 hours); days collects every older one."""
        day = case(
            (
                JobResult.received_at > now - days * DAY,
                _age_days(now, JobResult.received_at),
            ),
            else_=literal(days),
        )
        rows = select(day.label("day")).where(JobResult.job_id.is_(None))
        rows = self.policy.scope(principal, self.resource, rows)
        found = rows.subquery()
        query = select(found.c.day, func.count()).group_by(found.c.day)
        return {int(key): int(count) for key, count in await self.db.execute(query)}

    @guarded("list")
    async def paused_count(self, principal: Principal, *, now: datetime) -> int:
        """Live jobs that are paused now."""
        query = (
            select(func.count())
            .select_from(Job)
            .join(Client, Client.id == Job.client_id)
            .where(live(), paused_clause(now))
        )
        query = self.policy.scope(principal, self.resource, query)
        return int((await self.db.execute(query)).scalar_one())

    @guarded("list")
    async def attention(
        self, principal: Principal, *, now: datetime
    ) -> list[AttentionRow]:
        """Live jobs that are not paused and are missed, failing or warning,
        or whose newest due run is overdue (one query: the newest due run of
        each job is a LATERAL join)."""
        newest = (
            select(
                Occurrence.state.label("state"),
                Occurrence.deadline.label("deadline"),
                Occurrence.result_id.label("result_id"),
            )
            .where(
                Occurrence.job_id == Job.id,
                Occurrence.scheduled_for <= now,
                Occurrence.state.in_(DUE_STATES),
            )
            .order_by(Occurrence.scheduled_for.desc())
            .limit(1)
            .lateral("newest")
        )
        query = (
            select(
                Client.id,
                Client.name,
                Job.id,
                Job.name,
                JobStateRecord.state,
                newest.c.state,
                newest.c.deadline,
                JobStateRecord.last_success_at,
                JobResult.raw_message_id,
                Job.acknowledged_at,
            )
            .select_from(Job)
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobStateRecord, JobStateRecord.job_id == Job.id)
            .outerjoin(newest, true())
            .outerjoin(JobResult, JobResult.id == newest.c.result_id)
            .where(
                live(),
                not_(paused_clause(now)),
                or_(
                    JobStateRecord.state.in_(ATTENTION_JOB_STATES),
                    newest.c.state == "overdue",
                ),
            )
        )
        query = self.policy.scope(principal, self.resource, query)
        return [
            AttentionRow(
                client_id=row[0],
                client_name=row[1],
                job_id=row[2],
                job_name=row[3],
                job_state=row[4],
                occurrence_state=row[5],
                deadline=row[6],
                last_success_at=row[7],
                raw_message_id=row[8],
                acknowledged_at=row[9],
            )
            for row in await self.db.execute(query)
        ]

    @guarded("list")
    async def ribbon(
        self, principal: Principal, *, start: datetime, end: datetime
    ) -> list[RibbonRow]:
        """Stored occurrences of live jobs due in [start, end), by client
        name, job name and time. result_at is when the deciding result says
        the run ended (finished, else received)."""
        query = (
            select(
                Client.id,
                Client.name,
                Job.id,
                Job.name,
                Occurrence.scheduled_for,
                Occurrence.deadline,
                Occurrence.state,
                func.coalesce(JobResult.finished_at, JobResult.received_at),
            )
            .select_from(Occurrence)
            .join(Job, Job.id == Occurrence.job_id)
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobResult, JobResult.id == Occurrence.result_id)
            .where(
                Occurrence.scheduled_for >= start,
                Occurrence.scheduled_for < end,
                live(),
            )
            .order_by(
                Client.name_key,
                Client.id,
                Job.name_key,
                Job.id,
                Occurrence.scheduled_for,
            )
        )
        query = self.policy.scope(principal, self.resource, query)
        return [
            RibbonRow(
                client_id=row[0],
                client_name=row[1],
                job_id=row[2],
                job_name=row[3],
                scheduled_for=row[4],
                deadline=row[5],
                state=row[6],
                result_at=row[7],
            )
            for row in await self.db.execute(query)
        ]

    @guarded("list")
    async def expecting(self, principal: Principal, *, now: datetime) -> list[LiveJob]:
        """Live jobs that are not paused, with the start of their evaluation
        (the end of their last pause), for the runs still to come."""
        query = (
            select(Job, Client.name, JobStateRecord.eval_from)
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobStateRecord, JobStateRecord.job_id == Job.id)
            .where(live(), not_(paused_clause(now)))
        )
        query = self.policy.scope(principal, self.resource, query)
        return [
            LiveJob(job=job, client_name=name, eval_from=eval_from)
            for job, name, eval_from in (await self.db.execute(query)).all()
        ]

    @guarded("list")
    async def trend(
        self,
        principal: Principal,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> dict[tuple[date, str], int]:
        """Due runs of live jobs in [start, end) by (local date in timezone,
        state)."""
        local_day = func.date(func.timezone(timezone, Occurrence.scheduled_for))
        rows = (
            select(local_day.label("day"), Occurrence.state.label("state"))
            .select_from(Occurrence)
            .join(Job, Job.id == Occurrence.job_id)
            .join(Client, Client.id == Job.client_id)
            .where(
                Occurrence.scheduled_for >= start,
                Occurrence.scheduled_for < end,
                Occurrence.state.in_(DUE_STATES),
                live(),
            )
        )
        rows = self.policy.scope(principal, self.resource, rows)
        found = rows.subquery()
        query = select(found.c.day, found.c.state, func.count()).group_by(
            found.c.day, found.c.state
        )
        return {
            (day, str(state)): int(count)
            for day, state, count in await self.db.execute(query)
        }

    @guarded("list")
    async def breakdown(
        self,
        principal: Principal,
        *,
        by: BreakdownBy,
        start: datetime,
        end: datetime,
    ) -> list[BreakdownRow]:
        """Due runs of live jobs in [start, end) counted per parser pack of
        the job (vendor) or per client. A job without a parser pack has the
        key None (pings and the results API)."""
        verified = func.count().filter(Occurrence.state == "verified")
        failed = func.count().filter(Occurrence.state == "failed")
        silent = func.count().filter(Occurrence.state.in_(SILENT_STATES))
        query = (
            select(verified, failed, silent)
            .select_from(Occurrence)
            .join(Job, Job.id == Occurrence.job_id)
            .join(Client, Client.id == Job.client_id)
            .where(
                Occurrence.scheduled_for >= start,
                Occurrence.scheduled_for < end,
                Occurrence.state.in_(DUE_STATES),
                live(),
            )
        )
        if by == "vendor":
            query = (
                query.add_columns(Job.parser_pack_id, ParserPack.vendor)
                .outerjoin(ParserPack, ParserPack.id == Job.parser_pack_id)
                .group_by(Job.parser_pack_id, ParserPack.vendor)
            )
        else:
            query = query.add_columns(Client.id, Client.name).group_by(
                Client.id, Client.name
            )
        query = self.policy.scope(principal, self.resource, query)
        return [_breakdown_row(row) for row in await self.db.execute(query)]

    @guarded("list")
    async def activity(
        self,
        principal: Principal,
        *,
        kinds: frozenset[ActivityKind],
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[ActivityRow]:
        """The newest limit entries of the timeline before the (at, id)
        cursor, newest first: one query per kind (notifications arrive in
        phase C9)."""
        found: list[ActivityRow] = []
        if "flip" in kinds:
            flips = (
                select(
                    Flip.id,
                    Flip.at,
                    Flip.job_id,
                    Flip.from_state,
                    Flip.to_state,
                    Job.name,
                    Client.name,
                )
                .join(Job, Job.id == Flip.job_id)
                .join(Client, Client.id == Flip.client_id)
                .order_by(Flip.at.desc(), Flip.id.desc())
                .limit(limit)
            )
            if after is not None:
                flips = flips.where(tuple_(Flip.at, Flip.id) < after)
            flips = self.policy.scope(principal, self.resource, flips)
            for row in await self.db.execute(flips):
                found.append(
                    ActivityRow(
                        id=row[0],
                        at=row[1],
                        kind="flip",
                        summary=f"{row[5]} ({row[6]}): {row[3]} to {row[4]}",
                        ref_kind="job",
                        ref_id=str(row[2]),
                    )
                )
        if "ingest" in kinds:
            messages = (
                select(
                    RawMessage.id,
                    RawMessage.received_at,
                    RawMessage.parse_state,
                    Inbox.label,
                )
                .outerjoin(Inbox, Inbox.id == RawMessage.inbox_id)
                .order_by(RawMessage.received_at.desc(), RawMessage.id.desc())
                .limit(limit)
            )
            if after is not None:
                messages = messages.where(
                    tuple_(RawMessage.received_at, RawMessage.id) < after
                )
            messages = self.policy.scope(principal, self.resource, messages)
            for message in await self.db.execute(messages):
                where = "a deleted inbox" if message[3] is None else message[3]
                found.append(
                    ActivityRow(
                        id=message[0],
                        at=message[1],
                        kind="ingest",
                        summary=f"Message received in {where}: {message[2]}",
                        ref_kind="message",
                        ref_id=str(message[0]),
                    )
                )
        if "config" in kinds:
            events = (
                select(
                    AuditEvent.id,
                    AuditEvent.at,
                    AuditEvent.action,
                    AuditEvent.target_kind,
                    AuditEvent.target_id,
                )
                .where(
                    or_(
                        *(
                            AuditEvent.action.startswith(prefix, autoescape=True)
                            for prefix in CONFIG_PREFIXES
                        )
                    )
                )
                .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
                .limit(limit)
            )
            if after is not None:
                events = events.where(tuple_(AuditEvent.at, AuditEvent.id) < after)
            events = self.policy.scope(principal, self.resource, events)
            for event in await self.db.execute(events):
                found.append(
                    ActivityRow(
                        id=event[0],
                        at=event[1],
                        kind="config",
                        summary=_summary_of_action(event[2]),
                        ref_kind=event[3],
                        ref_id=event[4],
                    )
                )
        found.sort(key=lambda item: (item.at, item.id), reverse=True)
        return found[:limit]

    @guarded("update")
    async def acknowledge(
        self, principal: Principal, job: Job, *, user_id: uuid.UUID, at: datetime
    ) -> None:
        """Mark the job's state as acknowledged by the user (the caller locked
        the job). updated_at stays: the settings do not change. The next flip
        clears it (EvaluationRepository.save)."""
        job.acknowledged_by = user_id
        job.acknowledged_at = at
        await self.db.flush()

    @guarded("read")
    async def oldest_due(
        self, principal: Principal, *, now: datetime
    ) -> datetime | None:
        """The oldest moment the evaluator still owes work for: the earliest
        due_at that has passed among jobs it evaluates, or the creation of a
        live job it never evaluated. None when it is up to date."""
        waiting = select(func.min(JobStateRecord.due_at)).where(
            JobStateRecord.suppressed.is_(False), JobStateRecord.due_at <= now
        )
        waiting = self.policy.scope(principal, self.resource, waiting)
        never = (
            select(func.min(Job.created_at))
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobStateRecord, JobStateRecord.job_id == Job.id)
            .where(live(), JobStateRecord.job_id.is_(None))
        )
        never = self.policy.scope(principal, self.resource, never)
        query = select(waiting.scalar_subquery(), never.scalar_subquery())
        first, second = (await self.db.execute(query)).one()
        moments: list[datetime] = [
            moment for moment in (first, second) if moment is not None
        ]
        return min(moments) if moments else None

    @guarded("export")
    async def history(
        self,
        principal: Principal,
        *,
        start: datetime,
        end: datetime,
        client_id: uuid.UUID | None = None,
        live_only: bool = False,
        limit: int,
    ) -> list[HistoryRow]:
        """Occurrences due in [start, end) with their job, client and result,
        by time, client and job; at most limit rows. live_only leaves out
        archived jobs and clients (the digest); the exports keep them."""
        query = (
            select(
                Client.id,
                Client.name,
                Job.id,
                Job.name,
                Job.kind,
                Job.parser_pack_id,
                Occurrence.scheduled_for,
                Occurrence.deadline,
                Occurrence.state,
                Occurrence.note,
                JobResult.status,
                JobResult.started_at,
                JobResult.finished_at,
                JobResult.received_at,
            )
            .select_from(Occurrence)
            .join(Job, Job.id == Occurrence.job_id)
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobResult, JobResult.id == Occurrence.result_id)
            .where(Occurrence.scheduled_for >= start, Occurrence.scheduled_for < end)
            .order_by(
                Occurrence.scheduled_for,
                Client.name_key,
                Client.id,
                Job.name_key,
                Job.id,
            )
            .limit(limit)
        )
        if client_id is not None:
            query = query.where(Job.client_id == client_id)
        if live_only:
            query = query.where(live())
        query = self.policy.scope(principal, self.resource, query)
        return [_history_row(row) for row in await self.db.execute(query)]

    @guarded("export")
    async def client_history(
        self, principal: Principal, client_id: uuid.UUID, *, limit: int
    ) -> ClientHistory | None:
        """Everything recorded for the client, archived jobs included; at most
        limit rows of each kind. Never a ping token or a stored secret."""
        clients = select(Client).where(Client.id == client_id)
        clients = self.policy.scope(principal, self.resource, clients)
        client = (await self.db.scalars(clients)).one_or_none()
        if client is None:
            return None
        jobs = (
            select(Job, JobStateRecord.state)
            .outerjoin(JobStateRecord, JobStateRecord.job_id == Job.id)
            .where(Job.client_id == client_id)
            .order_by(Job.name_key, Job.id)
            .limit(limit)
        )
        jobs = self.policy.scope(principal, self.resource, jobs)
        job_rows = [(job, state) for job, state in (await self.db.execute(jobs)).all()]
        occurrences = (
            select(
                Client.id,
                Client.name,
                Job.id,
                Job.name,
                Job.kind,
                Job.parser_pack_id,
                Occurrence.scheduled_for,
                Occurrence.deadline,
                Occurrence.state,
                Occurrence.note,
                JobResult.status,
                JobResult.started_at,
                JobResult.finished_at,
                JobResult.received_at,
            )
            .select_from(Occurrence)
            .join(Job, Job.id == Occurrence.job_id)
            .join(Client, Client.id == Job.client_id)
            .outerjoin(JobResult, JobResult.id == Occurrence.result_id)
            .where(Job.client_id == client_id)
            .order_by(Occurrence.scheduled_for, Job.name_key, Job.id)
            .limit(limit)
        )
        occurrences = self.policy.scope(principal, self.resource, occurrences)
        history = [_history_row(row) for row in await self.db.execute(occurrences)]
        own_jobs = select(Job.id).where(Job.client_id == client_id)
        own_messages = select(RawMessage.id).where(RawMessage.client_id == client_id)
        results = (
            select(JobResult, Job.name)
            .outerjoin(Job, Job.id == JobResult.job_id)
            .where(
                or_(
                    JobResult.job_id.in_(own_jobs),
                    JobResult.raw_message_id.in_(own_messages),
                )
            )
            .order_by(JobResult.received_at, JobResult.id)
            .limit(limit)
        )
        results = self.policy.scope(principal, self.resource, results)
        result_rows = [
            (result, name) for result, name in (await self.db.execute(results)).all()
        ]
        flips = (
            select(Flip, Job.name)
            .join(Job, Job.id == Flip.job_id)
            .where(or_(Flip.client_id == client_id, Flip.job_id.in_(own_jobs)))
            .order_by(Flip.at, Job.name_key, Flip.id)
            .limit(limit)
        )
        flips = self.policy.scope(principal, self.resource, flips)
        flip_rows = [
            (flip, name) for flip, name in (await self.db.execute(flips)).all()
        ]
        messages = (
            select(RawMessage)
            .options(defer(RawMessage.body_zlib))
            .where(RawMessage.client_id == client_id)
            .order_by(RawMessage.received_at, RawMessage.id)
            .limit(limit)
        )
        messages = self.policy.scope(principal, self.resource, messages)
        return ClientHistory(
            client=client,
            jobs=job_rows,
            occurrences=history,
            results=result_rows,
            flips=flip_rows,
            messages=list((await self.db.scalars(messages)).all()),
        )


def _breakdown_row(row: Sequence[Any]) -> BreakdownRow:
    """verified, failed, silent, then the key and label columns that
    breakdown adds (outside the row type of its select)."""
    return BreakdownRow(
        key=None if row[3] is None else str(row[3]),
        label=None if row[4] is None else str(row[4]),
        verified=int(row[0]),
        failed=int(row[1]),
        silent=int(row[2]),
    )


def _history_row(row: Sequence[Any]) -> HistoryRow:
    return HistoryRow(
        client_id=row[0],
        client_name=row[1],
        job_id=row[2],
        job_name=row[3],
        job_kind=row[4],
        parser_pack_id=row[5],
        scheduled_for=row[6],
        deadline=row[7],
        state=row[8],
        note=row[9],
        result_status=row[10],
        started_at=row[11],
        finished_at=row[12],
        received_at=row[13],
    )


def group_due_counts(
    counts: dict[tuple[int, str], int], days: int
) -> dict[str, list[int]]:
    """verified, warning, failed and silent per day, oldest day first."""
    series: dict[str, list[int]] = defaultdict(lambda: [0] * days)
    for (day, state), count in counts.items():
        if not 0 <= day < days:
            continue
        group = "silent" if state in SILENT_STATES else state
        series[group][days - 1 - day] += count
    names = ("verified", "warning", "failed", "silent")
    return {name: list(series[name]) for name in names}
