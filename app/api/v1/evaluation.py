"""jobs/{id}/occurrences and flips: what the evaluator decided (phase C7).

Admins and technicians, or an API token of scope read. Occurrences are listed
oldest first; times after the evaluator's last tick are added as pending from
the job's schedule, so a timeline can show what is still expected. Flips are
listed newest first.
"""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import DbDep, ReaderDep, ServicesDep
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_cursor,
    decode_time_cursor,
    encode_cursor,
    encode_time_cursor,
)
from app.api.problems import FieldProblem, ProblemError
from app.api.v1.evaluation_schemas import (
    FlipOut,
    FlipPage,
    OccurrenceOut,
    OccurrencePage,
)
from app.db.models import Job
from app.evaluator.machine import WINDOW
from app.repos.clients import ClientRepository
from app.repos.evaluation import (
    FlipRepository,
    JobStateRepository,
    OccurrenceRepository,
)
from app.repos.jobs import JobRepository, is_paused
from app.schedule import ScheduleError, deadline, next_n, parse_spec

router = APIRouter(tags=["evaluation"])

# Without to, the list reaches this far ahead of now.
DEFAULT_AHEAD = timedelta(days=1)
_INSTANT = timedelta(microseconds=1)

TimeQuery = Annotated[AwareDatetime | None, Query()]
FromQuery = Annotated[
    AwareDatetime | None,
    Query(alias="from", description="Start (inclusive); default 14 days ago."),
]
ToQuery = Annotated[
    AwareDatetime | None, Query(description="End (exclusive); default in 24 hours.")
]


def job_not_found() -> ProblemError:
    return ProblemError(404, "Job not found")


def invalid_cursor() -> ProblemError:
    return ProblemError(400, "Invalid cursor", "Use next_cursor as returned.")


def parse_occurrence_cursor(cursor: str) -> datetime:
    value = decode_cursor(cursor, ("scheduled_for",))["scheduled_for"]
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise invalid_cursor() from None
    if moment.utcoffset() is None:
        raise invalid_cursor()
    return moment


def expected(
    job: Job,
    after: datetime,
    end: datetime,
    count: int,
    not_before: datetime,
) -> list[OccurrenceOut]:
    """Up to count scheduled times t with after < t < end and t >= not_before,
    as pending occurrences (not written yet)."""
    try:
        spec = parse_spec(
            job.schedule_kind, job.schedule_expr, job.timezone, job.created_at
        )
    except ScheduleError:
        return []
    return [
        OccurrenceOut(
            job_id=job.id,
            scheduled_for=moment,
            deadline=deadline(moment, job.max_runtime_minutes, job.grace_minutes),
            state="pending",
            result_id=None,
            note=None,
        )
        for moment in next_n(spec, after, count)
        if not_before <= moment < end
    ]


@router.get("/jobs/{job_id}/occurrences")
async def list_occurrences(
    job_id: uuid.UUID,
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    start: FromQuery = None,
    to: ToQuery = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> OccurrencePage:
    """The job's expected runs due in [from, to), oldest first; 404 for an
    unknown job. Runs not evaluated yet are pending; a paused or archived job
    lists none of those."""
    now = services.clock.now()
    begin = start or now - WINDOW
    end = to or now + DEFAULT_AHEAD
    if end <= begin:
        message = "to must be later than from."
        raise ProblemError(
            422,
            "Invalid range",
            message,
            errors=[FieldProblem(field="query.to", message=message)],
        )
    after = None if cursor is None else parse_occurrence_cursor(cursor)
    job = await JobRepository(db, services.policy).get(principal, job_id)
    if job is None:
        raise job_not_found()
    client = await ClientRepository(db, services.policy).get(principal, job.client_id)
    if client is None:
        raise job_not_found()
    stored = await OccurrenceRepository(db, services.policy).between(
        principal, job.id, start=begin, end=end, after=after, limit=limit + 1
    )
    items = [OccurrenceOut.model_validate(item) for item in stored]
    if not (is_paused(job, now) or job.archived or client.archived):
        records = await JobStateRepository(db, services.policy).for_jobs(
            principal, [job.id]
        )
        record = records.get(job.id)
        not_before = job.created_at
        if record is not None and record.eval_from is not None:
            not_before = max(not_before, record.eval_from)
        known = {item.scheduled_for for item in items}
        floor = max(begin - _INSTANT, now, after or begin - _INSTANT)
        pending = expected(job, floor, end, limit + 1, not_before)
        items += [item for item in pending if item.scheduled_for not in known]
        items.sort(key=lambda item: item.scheduled_for)
    page = items[:limit]
    next_cursor = None
    if len(items) > limit:
        last = page[-1].scheduled_for.isoformat()
        next_cursor = encode_cursor({"scheduled_for": last})
    return OccurrencePage(items=page, next_cursor=next_cursor)


@router.get("/flips")
async def list_flips(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    job_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    since: TimeQuery = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> FlipPage:
    """Changes of job states, newest first; job_id, client_id and since (at or
    after this time) narrow the list."""
    after = None if cursor is None else decode_time_cursor(cursor, "at")
    found = await FlipRepository(db, services.policy).page(
        principal,
        job_id=job_id,
        client_id=client_id,
        since=since,
        after=after,
        limit=limit + 1,
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("at", last.at, last.id)
    return FlipPage(
        items=[FlipOut.model_validate(flip) for flip in items],
        next_cursor=next_cursor,
    )
