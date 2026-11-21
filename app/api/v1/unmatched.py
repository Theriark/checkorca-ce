"""unmatched: results no job is bound to, and the three ways out of the queue.

- assign: bind the result to an existing job. The job takes the result's job
  name as its match key when it had none, and the client takes the result's
  client hint as an alias when it does not know it yet, so the next identical
  mail binds without a visit here. Other unmatched results with the same
  names bind too when the matcher is now sure of them.
- create-job: a new job (and, by name, a new client if needed) from the
  result, bound the same way.
- suggest-schedule: a daily schedule at the median time of the runs with the
  same names (app/matcher/suggest.py).

Admins and technicians alike; the list and suggest-schedule also take an API
token of scope read. Messages no pack claimed (parse_state unmatched) have no
result yet and are listed by messages?parse_state=unmatched.
"""

import uuid
from typing import Annotated, Final, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import Principal
from app.api.deps import (
    DbDep,
    ReaderDep,
    Services,
    ServicesDep,
    SessionDep,
    record_audit,
)
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import FieldProblem, ProblemError
from app.api.v1.job_schemas import MAX_ALIASES, ZoneName, clean_name
from app.api.v1.jobs import (
    SETTINGS_FIELDS,
    job_name_taken,
    job_out,
    schedule_fields,
    unknown_client,
)
from app.api.v1.pack_schemas import (
    AssignRequest,
    Binding,
    CreateJobRequest,
    JobFromResult,
    ScheduleSuggestion,
    UnmatchedOut,
    UnmatchedPage,
)
from app.api.v1.schedule import check_schedule
from app.db.models import Client, Job, JobResult
from app.ingest.results import ResultStatus
from app.matcher import (
    MIN_RESULTS,
    Bound,
    RunTimes,
    Suggestion,
    TooFewResults,
    names_client,
    same_names,
    suggest_daily,
)
from app.repos.clients import ClientRepository
from app.repos.jobs import JobRepository
from app.repos.messages import RawMessageRepository
from app.repos.results import JobResultRepository
from app.repos.settings import SettingsRepository
from app.schedule import ScheduleError, check_timezone

router = APIRouter(prefix="/unmatched", tags=["unmatched"])

# Results read to find those with the same names (compared in Python).
NAMED_LIMIT: Final = 2000
# Runs a suggestion is taken of, newest first.
SUGGEST_RUNS: Final = 100

TimezoneQuery = Annotated[ZoneName | None, Query()]


def result_not_found() -> ProblemError:
    return ProblemError(404, "Result not found")


def already_bound() -> ProblemError:
    return ProblemError(
        409, "Result already bound", "A job is already bound to this result."
    )


@router.get("")
async def list_unmatched(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> UnmatchedPage:
    """Results no job is bound to, newest first."""
    after = None if cursor is None else decode_time_cursor(cursor, "received_at")
    results = JobResultRepository(db, services.policy)
    found = await results.page(principal, unmatched=True, after=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("received_at", last.received_at, last.id)
    return UnmatchedPage(
        items=[
            UnmatchedOut(
                result_id=result.id,
                raw_message_id=result.raw_message_id,
                received_at=result.received_at,
                job_name=result.job_name,
                client_hint=result.client_hint,
                status=cast(ResultStatus, result.status),
            )
            for result in items
        ],
        next_cursor=next_cursor,
    )


async def unmatched_result(
    services: Services, db: AsyncSession, principal: Principal, result_id: uuid.UUID
) -> JobResult:
    """The result, locked; 404 when there is none, 409 when it is bound."""
    results = JobResultRepository(db, services.policy)
    result = await results.get(principal, result_id, for_update=True)
    if result is None:
        raise result_not_found()
    if result.job_id is not None:
        raise already_bound()
    return result


async def bind(
    services: Services,
    db: AsyncSession,
    principal: Principal,
    result: JobResult,
    job: Job,
    client: Client,
) -> Binding:
    """Bind the result to the job and teach the matcher its names; then bind
    the other unmatched results with the same names the matcher is sure of."""
    results = JobResultRepository(db, services.policy)
    messages = RawMessageRepository(db, services.policy)
    await results.bind(principal, result, job.id)
    match_key_set = job.match_key is None and result.job_name is not None
    if match_key_set:
        await JobRepository(db, services.policy).update(
            principal, job, match_key=result.job_name, updated_at=services.clock.now()
        )
    hint = result.client_hint
    alias_added = (
        hint is not None
        and not names_client(client.name, client.aliases, hint)
        and len(client.aliases) < MAX_ALIASES
    )
    if alias_added:
        await ClientRepository(db, services.policy).update(
            principal, client, aliases=[*client.aliases, hint]
        )
    matcher = await JobRepository(db, services.policy).matcher(principal)
    names = (result.job_name, result.client_hint)
    sure: list[uuid.UUID] = []
    for other in await results.named(principal, unmatched=True, limit=NAMED_LIMIT):
        if other.id == result.id or not same_names(
            (other.job_name, other.client_hint), names
        ):
            continue
        found = matcher.match(other.job_name, other.client_hint)
        if isinstance(found, Bound) and found.job_id == job.id:
            sure.append(other.id)
    # Only those still unbound: a concurrent assign of one of them wins.
    others = await results.bind_unbound(principal, sure, job.id)
    touched = {result.raw_message_id, *others}
    for message_id in touched:
        if message_id is not None:
            await messages.refresh_client(principal, message_id)
    return Binding(
        result_id=result.id,
        job_id=job.id,
        client_id=client.id,
        match_key_set=match_key_set,
        alias_added=alias_added,
        also_bound=len(others),
    )


@router.post("/{result_id}/assign")
async def assign(
    result_id: uuid.UUID,
    body: AssignRequest,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> Binding:
    """Bind the result to a job; 422 for an unknown job, 409 when the result
    is bound already."""
    principal = context.principal
    result = await unmatched_result(services, db, principal, result_id)
    job = await JobRepository(db, services.policy).get(
        principal, body.job_id, for_update=True
    )
    client = None
    if job is not None:
        client = await ClientRepository(db, services.policy).get(
            principal, job.client_id, for_update=True
        )
    if job is None or client is None:
        message = "No job with this id."
        raise ProblemError(
            422,
            "Unknown job",
            message,
            errors=[FieldProblem(field="body.job_id", message=message)],
        )
    binding = await bind(services, db, principal, result, job, client)
    await record_audit(
        services,
        db,
        request,
        principal.actor,
        "unmatched.assign",
        target_kind="job_result",
        target_id=result.id,
        job_id=str(job.id),
        also_bound=binding.also_bound,
    )
    await db.commit()
    return binding


def run_times(result: JobResult) -> RunTimes:
    return RunTimes(result.received_at, result.started_at, result.finished_at)


async def same_runs(
    services: Services, db: AsyncSession, principal: Principal, result: JobResult
) -> list[RunTimes]:
    """The times of the result and of the newest results with the same names,
    bound or not, at most SUGGEST_RUNS."""
    results = JobResultRepository(db, services.policy)
    names = (result.job_name, result.client_hint)
    runs = [run_times(result)]
    for other in await results.named(principal, unmatched=False, limit=NAMED_LIMIT):
        if len(runs) >= SUGGEST_RUNS:
            break
        if other.id != result.id and same_names(
            (other.job_name, other.client_hint), names
        ):
            runs.append(run_times(other))
    return runs


async def zone_for(
    services: Services, db: AsyncSession, principal: Principal, name: str | None
) -> ZoneInfo:
    """The zone asked for, else the digest zone of Settings; 422 when unknown."""
    if name is None:
        settings = SettingsRepository(db, services.policy, services.secret_box)
        name = (await settings.get(principal)).digest_timezone
    try:
        return ZoneInfo(check_timezone(name))
    except ScheduleError as error:
        raise ProblemError(
            422,
            "Invalid time zone",
            error.message,
            errors=[FieldProblem(field="timezone", message=error.message)],
        ) from None


def suggestion_out(suggestion: Suggestion) -> ScheduleSuggestion:
    return ScheduleSuggestion(
        kind=suggestion.kind,
        expr=suggestion.expr,
        timezone=suggestion.timezone,
        basis=suggestion.basis,
        results=suggestion.results,
    )


@router.get("/{result_id}/suggest-schedule")
async def suggest_schedule(
    result_id: uuid.UUID,
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    timezone: TimezoneQuery = None,
) -> ScheduleSuggestion:
    """A daily schedule at the median time of the runs with this result's job
    name and client hint (the result included), in timezone (default: the
    digest zone of Settings). 422 with fewer than 3 runs."""
    result = await JobResultRepository(db, services.policy).get(principal, result_id)
    if result is None:
        raise result_not_found()
    zone = await zone_for(services, db, principal, timezone)
    runs = await same_runs(services, db, principal, result)
    try:
        return suggestion_out(suggest_daily(runs, zone))
    except TooFewResults:
        raise ProblemError(
            422,
            "Too few results",
            f"A suggestion needs at least {MIN_RESULTS} results with this job name"
            f" and client hint; {len(runs)} found.",
        ) from None


async def client_for(
    services: Services, db: AsyncSession, principal: Principal, body: CreateJobRequest
) -> tuple[Client, bool]:
    """The client, locked: by id (422 when unknown) or by name (created when
    new; when a concurrent request created it first, that one)."""
    clients = ClientRepository(db, services.policy)
    if body.client_id is not None:
        found = await clients.get(principal, body.client_id, for_update=True)
        if found is None:
            raise unknown_client()
        return found, False
    name = str(body.client_name)
    found = await clients.find_by_name(principal, name, for_update=True)
    if found is not None:
        return found, False
    try:
        async with db.begin_nested():
            created = await clients.create(
                principal, name=name, notes="", aliases=[], now=services.clock.now()
            )
    except IntegrityError:
        found = await clients.find_by_name(principal, name, for_update=True)
        if found is None:
            raise
        return found, False
    return created, True


def job_name_of(body: CreateJobRequest, result: JobResult) -> str:
    """The name sent, else the result's job name; 422 when there is none."""
    if body.name is not None:
        return body.name
    try:
        return clean_name(result.job_name or "")
    except ValueError:
        message = "The result names no usable job; send a name."
        raise ProblemError(
            422,
            "Job name needed",
            message,
            errors=[FieldProblem(field="body.name", message=message)],
        ) from None


@router.post("/{result_id}/create-job", status_code=201)
async def create_job(
    result_id: uuid.UUID,
    body: CreateJobRequest,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> JobFromResult:
    """Create a job from the result and bind the result to it. 409 when the
    client has a job of that name, or the result is bound already."""
    principal = context.principal
    now = services.clock.now()
    result = await unmatched_result(services, db, principal, result_id)
    name = job_name_of(body, result)
    zone = await zone_for(services, db, principal, body.timezone)
    if body.schedule_kind is not None and body.schedule_expr is not None:
        spec = check_schedule(
            body.schedule_kind, body.schedule_expr, zone.key, now, now
        )
    else:
        runs = await same_runs(services, db, principal, result)
        suggestion = suggest_daily(runs, zone, minimum=1)
        spec = check_schedule("daily", suggestion.expr, suggestion.timezone, now, now)
    client, client_created = await client_for(services, db, principal, body)
    jobs = JobRepository(db, services.policy)
    if await jobs.find(principal, client.id, name) is not None:
        raise job_name_taken()
    settings = body.model_dump(include=set(SETTINGS_FIELDS))
    settings["match_key"] = body.match_key or result.job_name
    try:
        job = await jobs.create(
            principal,
            client_id=client.id,
            name=name,
            now=now,
            enabled=body.enabled,
            **settings,
            **schedule_fields(spec),
        )
    except IntegrityError:
        await db.rollback()
        raise job_name_taken() from None
    binding = await bind(services, db, principal, result, job, client)
    # The new job took the match key at create, so bind saw it set already.
    binding.match_key_set = settings["match_key"] is not None
    await record_audit(
        services,
        db,
        request,
        principal.actor,
        "unmatched.create_job",
        target_kind="job",
        target_id=job.id,
        result_id=str(result.id),
        client_created=client_created,
        also_bound=binding.also_bound,
    )
    await db.commit()
    return JobFromResult(
        job=job_out(services, job, client.name, now, principal),
        client_created=client_created,
        binding=binding,
    )
