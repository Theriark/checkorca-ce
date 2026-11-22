"""CSV exports (phase C8-B): exports/day.csv, exports/history.csv and
clients/{client_id}/export.csv.

Admins and technicians, or an API token of scope read. UTF-8 with a byte
order mark and CRLF line ends; a cell a spreadsheet would read as a formula
starts with an apostrophe (app/api/v1/jobs_csv.py). Times are ISO 8601 UTC
with Z; date is the calendar day in the digest zone. docs/dashboard.md
lists the columns.

The day and history exports have one row per occurrence (an expected run)
with its job, client and the result that decided it. The client export is
the full history of one client (legal D-4): the client, its jobs with their
settings, their occurrences, results, flips and messages, one record per
row. Archived jobs and clients are included: history is history.

No export holds a secret: no IMAP password, webhook or API token, ping
token, token hash or relay credential (tests/api/test_exports_api.py plants
canaries); a job's ping URL is left out on purpose.
"""

import codecs
import json
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Final
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DbDep, ReaderDep, ServicesDep
from app.api.problems import ProblemError
from app.api.v1.dashboard import DayQuery, app_settings, check_day, invalid_query
from app.api.v1.jobs_csv import render_table
from app.api.v1.messages import first_header
from app.db.models import Job
from app.notify.windows import day_bounds, days_bounds, local_date
from app.repos.clients import ClientRepository
from app.repos.dashboard import ClientHistory, DashboardRepository, HistoryRow

router = APIRouter(tags=["exports"])

type Cell = str | int | None

CSV_MEDIA_TYPE: Final = "text/csv"
HISTORY_COLUMNS: Final = (
    "date",
    "client",
    "job",
    "kind",
    "parser_pack_id",
    "scheduled_for",
    "deadline",
    "state",
    "note",
    "result_status",
    "started_at",
    "finished_at",
    "received_at",
)
CLIENT_COLUMNS: Final = (
    "record",
    "client",
    "job",
    "at",
    "state",
    "status",
    "scheduled_for",
    "deadline",
    "started_at",
    "finished_at",
    "received_at",
    "from_state",
    "to_state",
    "reason",
    "note",
    "details",
)
# The job settings a client export lists (never the ping token).
JOB_SETTINGS: Final = (
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
    "acknowledged_at",
)
# Rows of one export at most (per record kind for a client).
MAX_ROWS: Final = 100_000
MAX_HISTORY_DAYS: Final = 366
DEFAULT_HISTORY_DAYS: Final = 30

FromDayQuery = Annotated[
    date | None,
    Query(
        alias="from",
        description="First day in the digest zone; default 29 days before to.",
    ),
]
ToDayQuery = Annotated[
    date | None,
    Query(
        alias="to",
        description="Last day in the digest zone, included; default today.",
    ),
]


def csv_responses(description: str) -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "content": {CSV_MEDIA_TYPE: {"schema": {"type": "string"}}},
            "description": description,
        }
    }


def csv_response(text: str, filename: str) -> Response:
    """The CSV as a download; the byte order mark makes spreadsheets read it
    as UTF-8. filename holds only letters, digits, - and . (no name)."""
    return Response(
        content=codecs.BOM_UTF8 + text.encode("utf-8"),
        media_type=f"{CSV_MEDIA_TYPE}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def iso(moment: datetime | None) -> str | None:
    """ISO 8601 UTC with Z."""
    if moment is None:
        return None
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def as_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )


def too_many(advice: str = "choose fewer days") -> ProblemError:
    return ProblemError(
        422,
        "Export too large",
        f"The export would have more than {MAX_ROWS} rows; {advice}.",
    )


def history_cells(rows: Sequence[HistoryRow], zone: ZoneInfo) -> Iterator[list[Cell]]:
    for row in rows:
        yield [
            local_date(row.scheduled_for, zone).isoformat(),
            row.client_name,
            row.job_name,
            row.job_kind,
            row.parser_pack_id,
            iso(row.scheduled_for),
            iso(row.deadline),
            row.state,
            row.note,
            row.result_status,
            iso(row.started_at),
            iso(row.finished_at),
            iso(row.received_at),
        ]


@router.get(
    "/exports/day.csv",
    response_class=Response,
    responses=csv_responses("The runs due on the day, as CSV."),
)
async def export_day(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    day: DayQuery = None,
) -> Response:
    """Every run due on date (a calendar day in the digest zone, default
    today), with its result: one row per occurrence, by time."""
    settings = await app_settings(services, db, principal)
    zone = ZoneInfo(settings.digest_timezone)
    now = services.clock.now()
    chosen = local_date(now, zone) if day is None else check_day(day, "date")
    start, end = day_bounds(chosen, zone)
    rows = await DashboardRepository(db, services.policy).history(
        principal, start=start, end=end, limit=MAX_ROWS + 1
    )
    if len(rows) > MAX_ROWS:
        raise too_many()
    text = render_table(HISTORY_COLUMNS, history_cells(rows, zone))
    return csv_response(text, f"checkorca-day-{chosen.isoformat()}.csv")


@router.get(
    "/exports/history.csv",
    response_class=Response,
    responses=csv_responses("The runs due in the days, as CSV."),
)
async def export_history(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    first: FromDayQuery = None,
    last: ToDayQuery = None,
    client_id: uuid.UUID | None = None,
) -> Response:
    """Every run due from from to to (calendar days in the digest zone, both
    included, at most 366), of every client or of client_id: one row per
    occurrence, by time, with the columns of day.csv."""
    settings = await app_settings(services, db, principal)
    zone = ZoneInfo(settings.digest_timezone)
    now = services.clock.now()
    last = local_date(now, zone) if last is None else check_day(last, "to")
    if first is None:
        first = last - timedelta(days=DEFAULT_HISTORY_DAYS - 1)
    else:
        first = check_day(first, "from")
    if first > last:
        raise invalid_query("to", "to must be the same day as from or later.")
    if (last - first).days >= MAX_HISTORY_DAYS:
        raise invalid_query("from", f"Export at most {MAX_HISTORY_DAYS} days.")
    if client_id is not None:
        client = await ClientRepository(db, services.policy).get(principal, client_id)
        if client is None:
            raise ProblemError(404, "Client not found")
    start, end = days_bounds(first, last, zone)
    rows = await DashboardRepository(db, services.policy).history(
        principal, start=start, end=end, client_id=client_id, limit=MAX_ROWS + 1
    )
    if len(rows) > MAX_ROWS:
        raise too_many()
    text = render_table(HISTORY_COLUMNS, history_cells(rows, zone))
    name = f"checkorca-history-{first.isoformat()}-{last.isoformat()}.csv"
    return csv_response(text, name)


def client_row(record: str, client: str, **cells: Cell) -> list[Cell]:
    values: dict[str, Cell] = {"record": record, "client": client, **cells}
    return [values.get(column) for column in CLIENT_COLUMNS]


def job_settings(job: Job) -> dict[str, object]:
    settings: dict[str, object] = {}
    for name in JOB_SETTINGS:
        value = getattr(job, name)
        settings[name] = iso(value) if isinstance(value, datetime) else value
    return settings


def client_cells(history: ClientHistory) -> Iterator[list[Cell]]:
    """The client, then its jobs, occurrences, results, flips and messages,
    each oldest first."""
    client = history.client
    name = client.name
    yield client_row(
        "client",
        name,
        at=iso(client.created_at),
        state="archived" if client.archived else "active",
        note=client.notes,
        details=as_json({"aliases": list(client.aliases)}),
    )
    for job, state in history.jobs:
        yield client_row(
            "job",
            name,
            job=job.name,
            at=iso(job.created_at),
            state=state or "unknown",
            details=as_json(job_settings(job)),
        )
    for row in history.occurrences:
        yield client_row(
            "occurrence",
            name,
            job=row.job_name,
            at=iso(row.scheduled_for),
            state=row.state,
            status=row.result_status,
            scheduled_for=iso(row.scheduled_for),
            deadline=iso(row.deadline),
            started_at=iso(row.started_at),
            finished_at=iso(row.finished_at),
            received_at=iso(row.received_at),
            note=row.note,
        )
    for result, job_name in history.results:
        yield client_row(
            "result",
            name,
            job=job_name or result.job_name,
            at=iso(result.received_at),
            status=result.status,
            started_at=iso(result.started_at),
            finished_at=iso(result.finished_at),
            received_at=iso(result.received_at),
            details=as_json(
                {
                    "client_hint": result.client_hint,
                    "job_name": result.job_name,
                    "run_id": result.run_id,
                    "raw_message_id": result.raw_message_id,
                    "details": result.details,
                }
            ),
        )
    for flip, job_name in history.flips:
        yield client_row(
            "flip",
            name,
            job=job_name,
            at=iso(flip.at),
            from_state=flip.from_state,
            to_state=flip.to_state,
            reason=flip.reason,
        )
    for message in history.messages:
        yield client_row(
            "message",
            name,
            at=iso(message.received_at),
            state=message.parse_state,
            received_at=iso(message.received_at),
            details=as_json(
                {
                    "message_id": message.message_id,
                    "subject": first_header(message, "subject"),
                    "from": first_header(message, "from"),
                    "size": message.size,
                    "parse_pack_id": message.parse_pack_id,
                    "parse_reason": message.parse_reason,
                }
            ),
        )


@router.get(
    "/clients/{client_id}/export.csv",
    response_class=Response,
    responses=csv_responses("Everything recorded for the client, as CSV."),
)
async def export_client(
    client_id: uuid.UUID, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> Response:
    """The full history of one client (legal D-4), one record per row: the
    client, its jobs and their settings, occurrences, results, flips and
    messages (headers only; the raw message stays in the app)."""
    history = await DashboardRepository(db, services.policy).client_history(
        principal, client_id, limit=MAX_ROWS + 1
    )
    if history is None:
        raise ProblemError(404, "Client not found")
    # 422 when a record kind has more than MAX_ROWS rows: never cut short.
    kinds: tuple[Sequence[object], ...] = (
        history.jobs,
        history.occurrences,
        history.results,
        history.flips,
        history.messages,
    )
    if any(len(rows) > MAX_ROWS for rows in kinds):
        raise too_many("export the client's runs with history.csv instead")
    text = render_table(CLIENT_COLUMNS, client_cells(history))
    return csv_response(text, f"checkorca-client-{client_id}.csv")
