"""jobs: list, create, get, change, pause, resume and archive jobs; CSV export
and import.

Admins and technicians alike; the list, get and export routes also take an API
token of scope read. Schedules are checked by the schedule library and stored
in their normal form. A job is paused until resumed (pause without until) or
until a time (pause with until).
"""

import codecs
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    DbDep,
    ReaderDep,
    Services,
    ServicesDep,
    SessionContext,
    SessionDep,
    record_audit,
)
from app.api.pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, encode_cursor
from app.api.problems import FieldProblem, ProblemError
from app.api.v1 import jobs_csv
from app.api.v1.clients import SearchQuery, parse_name_cursor
from app.api.v1.job_schemas import (
    ImportProblem,
    ImportResult,
    JobKind,
    JobOut,
    JobPage,
    JobPatch,
    JobSettings,
    Name,
    NewJob,
    PauseRequest,
)
from app.api.v1.schedule import check_schedule
from app.db.models import Client, Job, name_key
from app.repos.clients import ClientRepository
from app.repos.jobs import JobFilters, JobRepository, JobState, job_state
from app.schedule import ScheduleSpec

router = APIRouter(prefix="/jobs", tags=["jobs"])

COLUMNS = frozenset(Job.__table__.columns.keys())

CSV_MEDIA_TYPE = "text/csv"
CSV_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {CSV_MEDIA_TYPE: {"schema": {"type": "string"}}},
        "description": "The jobs as CSV (UTF-8 with a byte order mark).",
    }
}
# Fields that can be set back to null.
NULLABLE_FIELDS = frozenset({"parser_pack_id", "match_key"})
# The settings a job takes from the request body as they are.
SETTINGS_FIELDS = (
    "kind",
    "parser_pack_id",
    "match_key",
    "max_runtime_minutes",
    "grace_minutes",
    "escalate_minutes",
    "attribution_basis",
    "warning_policy",
    "consecutive_failures_to_alert",
)


def job_not_found() -> ProblemError:
    return ProblemError(404, "Job not found")


def job_name_taken() -> ProblemError:
    return ProblemError(
        409, "Job name taken", "The client already has a job with this name."
    )


def unknown_client() -> ProblemError:
    message = "No client with this id."
    return ProblemError(
        422,
        "Unknown client",
        message,
        errors=[FieldProblem(field="body.client_id", message=message)],
    )


def ping_url(services: Services, job: Job) -> str:
    return f"{services.settings.base_url.rstrip('/')}/api/v1/ping/{job.ping_token}"


def job_out(services: Services, job: Job, client_name: str, now: datetime) -> JobOut:
    # Every column JobOut shares with the table, then the derived fields.
    stored = {
        field: getattr(job, field) for field in JobOut.model_fields if field in COLUMNS
    }
    return JobOut(
        **stored,
        client_name=client_name,
        ping_url=ping_url(services, job),
        state=job_state(job, now),
        state_since=None,
        last_success_at=None,
    )


def schedule_fields(spec: ScheduleSpec) -> dict[str, str]:
    return {
        "schedule_kind": spec.kind,
        "schedule_expr": spec.expr,
        "timezone": spec.timezone,
    }


@router.get("")
async def list_jobs(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    client_id: uuid.UUID | None = None,
    q: SearchQuery = None,
    state: JobState | None = None,
    kind: JobKind | None = None,
    pack: Annotated[str | None, Query(max_length=100)] = None,
    archived: bool = False,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> JobPage:
    """Jobs ordered by name, filtered by client, name, state, kind or pack."""
    after = None if cursor is None else parse_name_cursor(cursor)
    now = services.clock.now()
    filters = JobFilters(
        now=now,
        client_id=client_id,
        q=q,
        kind=kind,
        pack=pack,
        state=state,
        archived=archived,
    )
    jobs = JobRepository(db, services.policy)
    found = await jobs.page(principal, filters=filters, after=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last, _ = items[-1]
        next_cursor = encode_cursor({"name_key": last.name_key, "id": str(last.id)})
    return JobPage(
        items=[job_out(services, job, name, now) for job, name in items],
        next_cursor=next_cursor,
    )


@router.post("", status_code=201)
async def create_job(
    body: NewJob,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> JobOut:
    """Create a job; 422 names an unusable schedule, 409 a name the client
    already uses."""
    now = services.clock.now()
    spec = check_schedule(
        body.schedule_kind, body.schedule_expr, body.timezone, now, now
    )
    client = await ClientRepository(db, services.policy).get(
        context.principal, body.client_id, for_update=True
    )
    if client is None:
        raise unknown_client()
    jobs = JobRepository(db, services.policy)
    if await jobs.find(context.principal, client.id, body.name) is not None:
        raise job_name_taken()
    settings = body.model_dump(include=set(SETTINGS_FIELDS))
    try:
        job = await jobs.create(
            context.principal,
            client_id=client.id,
            name=body.name,
            now=now,
            enabled=body.enabled,
            **settings,
            **schedule_fields(spec),
        )
    except IntegrityError:
        await db.rollback()
        raise job_name_taken() from None
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "job.create",
        target_kind="job",
        target_id=job.id,
    )
    await db.commit()
    return job_out(services, job, client.name, now)


@router.get("/export.csv", response_class=Response, responses=CSV_RESPONSE)
async def export_jobs(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    client_id: uuid.UUID | None = None,
) -> Response:
    """Jobs that are not archived, of clients that are not archived, as CSV.

    The columns are those of the import; a cell that a spreadsheet would read
    as a formula starts with an apostrophe.
    """
    rows = await JobRepository(db, services.policy).export_rows(principal, client_id)
    text = jobs_csv.render(
        (
            client_name,
            job.name,
            job.kind,
            job.schedule_kind,
            job.schedule_expr,
            job.timezone,
            job.max_runtime_minutes,
            job.grace_minutes,
            job.escalate_minutes,
            job.warning_policy,
            job.consecutive_failures_to_alert,
            job.match_key,
            job.parser_pack_id,
        )
        for job, client_name in rows
    )
    return Response(
        # The byte order mark makes spreadsheets read the file as UTF-8.
        content=codecs.BOM_UTF8 + text.encode("utf-8"),
        media_type=f"{CSV_MEDIA_TYPE}; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="jobs.csv"'},
    )


class ImportRow(JobSettings):
    """One CSV row, checked with the rules of the API."""

    client: Name
    job: Name


def row_problem(error: ValidationError) -> str:
    """The columns of a row that failed, with the reason; never the values."""
    parts = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ())) or "row"
        parts.append(f"{location}: {item.get('msg', 'invalid')}")
    return "; ".join(parts)


class Importer:
    """Imports checked rows one by one, each in its own savepoint."""

    def __init__(
        self,
        services: Services,
        db: AsyncSession,
        context: SessionContext,
        now: datetime,
    ) -> None:
        self.db = db
        self.principal = context.principal
        self.now = now
        self.clients = ClientRepository(db, services.policy)
        self.jobs = JobRepository(db, services.policy)
        self.known: dict[str, Client] = {}
        self.seen: dict[tuple[str, str], int] = {}
        self.result = ImportResult(
            created=0, updated=0, clients_created=0, errors=[], dry_run=False
        )

    def fail(self, row: int, message: str) -> None:
        self.result.errors.append(ImportProblem(row=row, message=message))

    async def client(self, name: str) -> tuple[Client, bool]:
        key = name_key(name)
        if key in self.known:
            return self.known[key], False
        found = await self.clients.find_by_name(self.principal, name)
        if found is not None:
            return found, False
        created = await self.clients.create(
            self.principal, name=name, notes="", aliases=[], now=self.now
        )
        return created, True

    async def run(self, row: jobs_csv.CsvRow) -> None:
        if "" in row.cells:
            self.fail(row.number, "The row has more cells than the first line.")
            return
        try:
            checked = ImportRow.model_validate(row.cells)
        except ValidationError as error:
            self.fail(row.number, row_problem(error))
            return
        key = (name_key(checked.client), name_key(checked.job))
        if key in self.seen:
            self.fail(row.number, f"Same client and job as row {self.seen[key]}.")
            return
        self.seen[key] = row.number
        try:
            spec = check_schedule(
                checked.schedule_kind,
                checked.schedule_expr,
                checked.timezone,
                self.now,
                self.now,
            )
        except ProblemError as error:
            self.fail(row.number, error.detail or error.title)
            return
        settings = checked.model_dump(include=set(SETTINGS_FIELDS))
        # An existing job keeps the settings whose column the file lacks.
        kept = set(SETTINGS_FIELDS) - row.columns
        changes = {name: value for name, value in settings.items() if name not in kept}
        settings.update(schedule_fields(spec))
        changes.update(schedule_fields(spec))
        try:
            async with self.db.begin_nested():
                client, client_created = await self.client(checked.client)
                job = await self.jobs.find(self.principal, client.id, checked.job)
                if job is None:
                    await self.jobs.create(
                        self.principal,
                        client_id=client.id,
                        name=checked.job,
                        now=self.now,
                        **settings,
                    )
                else:
                    await self.jobs.update(
                        self.principal, job, updated_at=self.now, **changes
                    )
        except IntegrityError:
            self.fail(row.number, "The row conflicts with a change made meanwhile.")
            return
        self.known[name_key(client.name)] = client
        self.result.clients_created += int(client_created)
        if job is None:
            self.result.created += 1
        else:
            self.result.updated += 1


@router.post("/import.csv")
async def import_jobs(
    file: Annotated[UploadFile, File(description="The CSV file (UTF-8).")],
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
    dry_run: bool = False,
) -> ImportResult:
    """Create or update jobs from CSV, matched by client and job name.

    A client that does not exist yet is created. An empty cell takes the
    default; a column the file lacks keeps an existing job's value. Rows with
    an error are left out and reported by row number (the first line is row 1);
    the other rows are imported. dry_run checks everything and saves nothing.
    """
    try:
        rows = jobs_csv.parse(await file.read(jobs_csv.MAX_IMPORT_BYTES + 1))
    except jobs_csv.CsvFileError as error:
        raise ProblemError(422, "Unusable CSV file", str(error)) from None
    importer = Importer(services, db, context, services.clock.now())
    for row in rows:
        await importer.run(row)
    result = importer.result
    if dry_run:
        await db.rollback()
        return result.model_copy(update={"dry_run": True})
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "job.import",
        target_kind="job",
        created=result.created,
        updated=result.updated,
        clients_created=result.clients_created,
        errors=len(result.errors),
    )
    await db.commit()
    return result


async def load_job(
    services: Services, db: AsyncSession, context: SessionContext, job_id: uuid.UUID
) -> tuple[Job, Client]:
    """The job, locked for the change, and its client."""
    job = await JobRepository(db, services.policy).get(
        context.principal, job_id, for_update=True
    )
    if job is None:
        raise job_not_found()
    client = await ClientRepository(db, services.policy).get(
        context.principal, job.client_id
    )
    if client is None:
        raise job_not_found()
    return job, client


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> JobOut:
    job = await JobRepository(db, services.policy).get(principal, job_id)
    if job is None:
        raise job_not_found()
    client = await ClientRepository(db, services.policy).get(principal, job.client_id)
    if client is None:
        raise job_not_found()
    return job_out(services, job, client.name, services.clock.now())


async def save(
    services: Services,
    db: AsyncSession,
    request: Request,
    context: SessionContext,
    job: Job,
    client: Client,
    action: str,
    changes: dict[str, Any],
) -> JobOut:
    """Apply the changes, audit the names of the changed fields, commit."""
    now = services.clock.now()
    changes = {
        field: value for field, value in changes.items() if getattr(job, field) != value
    }
    if changes:
        try:
            await JobRepository(db, services.policy).update(
                context.principal, job, updated_at=now, **changes
            )
        except IntegrityError:
            await db.rollback()
            raise job_name_taken() from None
        await record_audit(
            services,
            db,
            request,
            context.principal.actor,
            action,
            target_kind="job",
            target_id=job.id,
            fields=",".join(sorted(changes)),
        )
    # Without changes this only ends the transaction and its row lock.
    await db.commit()
    return job_out(services, job, client.name, now)


@router.patch("/{job_id}")
async def update_job(
    job_id: uuid.UUID,
    body: JobPatch,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> JobOut:
    """Change a job. Sent schedule fields are checked together with the stored
    ones; moving a job to another client keeps its ping URL."""
    job, client = await load_job(services, db, context, job_id)
    # A null clears parser_pack_id and match_key; for the others it is no change.
    changes: dict[str, Any] = {
        field: value
        for field, value in body.model_dump(exclude_unset=True).items()
        if value is not None or field in NULLABLE_FIELDS
    }
    if {"schedule_kind", "schedule_expr", "timezone"} & changes.keys():
        spec = check_schedule(
            changes.get("schedule_kind", job.schedule_kind),
            changes.get("schedule_expr", job.schedule_expr),
            changes.get("timezone", job.timezone),
            job.created_at,
            services.clock.now(),
        )
        changes.update(schedule_fields(spec))
    moved = changes.get("client_id", job.client_id) != job.client_id
    if moved:
        target = await ClientRepository(db, services.policy).get(
            context.principal, changes["client_id"], for_update=True
        )
        if target is None:
            raise unknown_client()
        client = target
    name = changes.get("name", job.name)
    if moved or name_key(name) != job.name_key:
        other = await JobRepository(db, services.policy).find(
            context.principal, client.id, name
        )
        if other is not None and other.id != job.id:
            raise job_name_taken()
    return await save(
        services, db, request, context, job, client, "job.update", changes
    )


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
    body: PauseRequest | None = None,
) -> JobOut:
    """Pause a job: no state or alerts while paused. Without until it stays
    paused until resumed; until must be in the future."""
    job, client = await load_job(services, db, context, job_id)
    until = None if body is None else body.until
    if until is not None and until <= services.clock.now():
        message = "until must be in the future."
        raise ProblemError(
            422,
            "Invalid pause",
            message,
            errors=[FieldProblem(field="body.until", message=message)],
        )
    changes: dict[str, Any] = (
        {"enabled": False, "paused_until": None}
        if until is None
        else {"enabled": True, "paused_until": until.astimezone(UTC)}
    )
    return await save(services, db, request, context, job, client, "job.pause", changes)


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> JobOut:
    """End a pause now."""
    job, client = await load_job(services, db, context, job_id)
    changes = {"enabled": True, "paused_until": None}
    return await save(
        services, db, request, context, job, client, "job.resume", changes
    )


@router.post("/{job_id}/archive")
async def archive_job(
    job_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> JobOut:
    """Archive a job: hidden from the default list, never evaluated. PATCH
    archived false restores it."""
    job, client = await load_job(services, db, context, job_id)
    changes = {"archived": True}
    return await save(
        services, db, request, context, job, client, "job.archive", changes
    )
