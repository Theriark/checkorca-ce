"""The Morning check (phase C8-B): dashboard/today, dashboard/ribbon,
dashboard/trend, dashboard/breakdown, activity and digest/preview.

Admins and technicians, or an API token of scope read. docs/dashboard.md
defines every number; in short: a due run is an occurrence that is verified,
warning, failed, overdue or missed, silent means overdue or missed, and the
dashboard counts live jobs only (not archived, client not archived). Calendar
days and the night of the ribbon are those of the digest zone
(settings.digest_timezone). Each route runs a fixed number of queries,
whatever the number of clients and jobs.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Final
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import Principal
from app.api.deps import DbDep, ReaderDep, Services, ServicesDep
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import FieldProblem, ProblemError
from app.api.v1.dashboard_schemas import (
    ActivityItem,
    ActivityKindOut,
    ActivityPage,
    AttentionItem,
    AttentionState,
    Breakdown,
    BreakdownByOut,
    BreakdownItem,
    Coverage,
    DashboardToday,
    DigestPreview,
    HeartbeatOut,
    Ribbon,
    RibbonClient,
    RibbonJob,
    RibbonOccurrence,
    RibbonWindow,
    Stat,
    Stats,
    Trend,
    TrendDay,
)
from app.api.v1.evaluation import expected
from app.db.models import AppSettings, name_key
from app.evaluator.model import as_occurrence_state
from app.notify.digest import build_digest
from app.notify.windows import days_bounds, local_date, morning_line, night_window
from app.repos.dashboard import (
    ActivityKind,
    AttentionRow,
    DashboardRepository,
    group_due_counts,
)
from app.repos.heartbeat import HeartbeatRepository
from app.repos.settings import SettingsRepository
from app.worker.heartbeat import heartbeat_view

router = APIRouter(tags=["dashboard"])

# The stat cards' sparklines: one value per 24 hours.
SPARK_DAYS: Final = 14
DEFAULT_DAYS: Final = 30
MAX_DAYS: Final = 90
DEFAULT_RIBBON_SPAN: Final = timedelta(hours=18)
MAX_RIBBON_SPAN: Final = timedelta(hours=72)
# Runs still expected per job in one ribbon at most.
MAX_EXPECTED: Final = 200
# A day asked for must lie in these years.
FIRST_DAY: Final = date(2000, 1, 1)
LAST_DAY: Final = date(2099, 12, 31)
PROBLEM_STATES: Final = frozenset({"warning", "failed", "overdue", "missed"})
# Silent first, then failed, then warning (the Interfaces chapter).
ATTENTION_ORDER: Final[dict[str, int]] = {
    "missed": 0,
    "overdue": 0,
    "failed": 1,
    "warning": 2,
}
ACTIVITY_KINDS: Final[frozenset[ActivityKind]] = frozenset(
    {"ingest", "flip", "notification", "config"}
)
NO_PACK_KEY: Final = "none"
NO_PACK_LABEL: Final = "No parser pack (pings and the results API)"
_INSTANT: Final = timedelta(microseconds=1)
_LATEST: Final = datetime.max.replace(tzinfo=UTC)

DaysQuery = Annotated[
    int,
    Query(
        ge=1,
        le=MAX_DAYS,
        description="Calendar days in the digest zone, ending today.",
    ),
]
FromQuery = Annotated[
    AwareDatetime | None,
    Query(
        alias="from",
        description="Start (inclusive); default 18:00 of the night in the digest zone.",
    ),
]
ToQuery = Annotated[
    AwareDatetime | None,
    Query(description="End (exclusive); default 12:00 after that night."),
]
DayQuery = Annotated[
    date | None,
    Query(alias="date", description="A day in the digest zone; default today."),
]


def invalid_query(field: str, message: str) -> ProblemError:
    return ProblemError(
        422,
        "Invalid query",
        message,
        errors=[FieldProblem(field=f"query.{field}", message=message)],
    )


def check_day(day: date, field: str) -> date:
    if not FIRST_DAY <= day <= LAST_DAY:
        raise invalid_query(field, f"Choose a day from {FIRST_DAY} to {LAST_DAY}.")
    return day


async def app_settings(
    services: Services, db: AsyncSession, principal: Principal
) -> AppSettings:
    """The settings row: the digest zone and time, demo_seeded."""
    settings = SettingsRepository(db, services.policy, services.secret_box)
    return await settings.get(principal)


def stat(series: list[int]) -> Stat:
    return Stat(
        value=series[-1],
        delta_vs_yesterday=series[-1] - series[-2],
        spark14=series,
    )


def waiting_series(counts: dict[int, int], days: int) -> list[int]:
    """Results waiting in Unmatched at the end of each of the last days 24-hour
    periods, oldest first: those waiting now, less those that arrived later.
    A result assigned since then is not counted on the earlier days."""
    total = sum(counts.values())
    series: list[int] = []
    arrived_later = 0
    for day in range(days):
        series.append(total - arrived_later)
        arrived_later += counts.get(day, 0)
    return series[::-1]


def attention_state(row: AttentionRow) -> AttentionState | None:
    """Missed, overdue (the newest due run is late), failed or warning."""
    if row.job_state == "missed":
        return "missed"
    if row.occurrence_state == "overdue":
        return "overdue"
    if row.job_state == "failing":
        return "failed"
    if row.job_state == "warning":
        return "warning"
    return None


def attention_items(rows: list[AttentionRow]) -> list[AttentionItem]:
    """Silent first, then failed, then warning; within each, the ones nobody
    acknowledged first, then the oldest deadline first."""
    items: list[AttentionItem] = []
    for row in rows:
        state = attention_state(row)
        if state is None:
            continue
        items.append(
            AttentionItem(
                client_id=row.client_id,
                client_name=row.client_name,
                job_id=row.job_id,
                job_name=row.job_name,
                state=state,
                expected_by=row.deadline,
                last_success_at=row.last_success_at,
                raw_message_id=row.raw_message_id,
                acknowledged_at=row.acknowledged_at,
            )
        )
    items.sort(
        key=lambda item: (
            ATTENTION_ORDER[item.state],
            item.acknowledged_at is not None,
            item.expected_by or _LATEST,
            name_key(item.client_name),
            name_key(item.job_name),
            item.job_id,
        )
    )
    return items


@router.get("/dashboard/today")
async def dashboard_today(
    principal: ReaderDep, services: ServicesDep, db: DbDep
) -> DashboardToday:
    """The Morning check's numbers: the stat cards (each a value for the 24
    hours up to now, its change against the 24 hours before and 14 values,
    oldest first), coverage of the last 24 hours, the jobs that need
    attention, the worker heartbeat and whether the demo data was seeded."""
    now = services.clock.now()
    dashboard = DashboardRepository(db, services.policy)
    due = group_due_counts(
        await dashboard.due_counts(principal, now=now, days=SPARK_DAYS), SPARK_DAYS
    )
    unmatched = waiting_series(
        await dashboard.unmatched_counts(principal, now=now, days=SPARK_DAYS),
        SPARK_DAYS,
    )
    paused = await dashboard.paused_count(principal, now=now)
    rows = await dashboard.attention(principal, now=now)
    heartbeat = await HeartbeatRepository(db, services.policy).get(principal)
    beat = heartbeat_view(heartbeat, now)
    settings = await app_settings(services, db, principal)
    expected_now = sum(series[-1] for series in due.values())
    verified_now = due["verified"][-1]
    return DashboardToday(
        generated_at=now,
        stats=Stats(
            verified=stat(due["verified"]),
            failed=stat(due["failed"]),
            silent=stat(due["silent"]),
            unmatched=stat(unmatched),
            # Pauses keep no history: the line is flat at today's value.
            paused=stat([paused] * SPARK_DAYS),
        ),
        coverage=Coverage(
            verified=verified_now,
            expected=expected_now,
            ratio=round(verified_now / expected_now, 4) if expected_now else None,
        ),
        attention=attention_items(rows),
        heartbeat=HeartbeatOut(
            at=beat.at, age_seconds=beat.age_seconds, stale=beat.stale
        ),
        demo_seeded=settings.demo_seeded,
    )


def ribbon_window(
    now: datetime,
    zone: ZoneInfo,
    start: datetime | None,
    to: datetime | None,
) -> tuple[datetime, datetime]:
    """The night by default; one bound alone gives an 18-hour window."""
    if start is None:
        if to is None:
            return night_window(now, zone)
        start = to - DEFAULT_RIBBON_SPAN
    if to is None:
        to = start + DEFAULT_RIBBON_SPAN
    if to <= start:
        raise invalid_query("to", "to must be later than from.")
    if to - start > MAX_RIBBON_SPAN:
        raise invalid_query("to", "The window may span at most 72 hours.")
    return start.astimezone(UTC), to.astimezone(UTC)


@router.get("/dashboard/ribbon")
async def dashboard_ribbon(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    start: FromQuery = None,
    to: ToQuery = None,
    problems_only: bool = False,
) -> Ribbon:
    """The Night Ribbon: every live job's runs due in [from, to), by client
    and job. Runs after now that are not written yet are listed as pending
    from the schedule (none for a paused job). problems_only keeps the jobs
    with a warning, failed, overdue or missed run in the window."""
    now = services.clock.now()
    settings = await app_settings(services, db, principal)
    zone = ZoneInfo(settings.digest_timezone)
    begin, end = ribbon_window(now, zone, start, to)
    dashboard = DashboardRepository(db, services.policy)
    client_names: dict[uuid.UUID, str] = {}
    job_names: dict[uuid.UUID, str] = {}
    lanes: dict[uuid.UUID, dict[uuid.UUID, list[RibbonOccurrence]]]
    lanes = defaultdict(dict)

    def lane(
        client_id: uuid.UUID, client_name: str, job_id: uuid.UUID, job_name: str
    ) -> list[RibbonOccurrence]:
        client_names[client_id] = client_name
        job_names[job_id] = job_name
        return lanes[client_id].setdefault(job_id, [])

    for row in await dashboard.ribbon(principal, start=begin, end=end):
        lane(row.client_id, row.client_name, row.job_id, row.job_name).append(
            RibbonOccurrence(
                scheduled_for=row.scheduled_for,
                deadline=row.deadline,
                state=as_occurrence_state(row.state),
                result_at=row.result_at,
            )
        )
    if end > now:
        floor = max(begin - _INSTANT, now)
        for item in await dashboard.expecting(principal, now=now):
            job = item.job
            known = {
                run.scheduled_for
                for run in lanes.get(job.client_id, {}).get(job.id, [])
            }
            not_before = job.created_at
            if item.eval_from is not None:
                not_before = max(not_before, item.eval_from)
            pending = [
                run
                for run in expected(job, floor, end, MAX_EXPECTED, not_before)
                if run.scheduled_for not in known
            ]
            if not pending:
                continue
            lane(job.client_id, item.client_name, job.id, job.name).extend(
                RibbonOccurrence(
                    scheduled_for=run.scheduled_for,
                    deadline=run.deadline,
                    state="pending",
                    result_at=None,
                )
                for run in pending
            )
    clients: list[RibbonClient] = []
    for client_id in sorted(
        lanes, key=lambda key: (name_key(client_names[key]), str(key))
    ):
        jobs: list[RibbonJob] = []
        for job_id in sorted(
            lanes[client_id], key=lambda key: (name_key(job_names[key]), str(key))
        ):
            runs = sorted(lanes[client_id][job_id], key=lambda run: run.scheduled_for)
            if problems_only and not any(run.state in PROBLEM_STATES for run in runs):
                continue
            jobs.append(RibbonJob(id=job_id, name=job_names[job_id], occurrences=runs))
        if jobs:
            clients.append(
                RibbonClient(id=client_id, name=client_names[client_id], jobs=jobs)
            )
    return Ribbon(
        window=RibbonWindow.model_validate({"from": begin, "to": end}),
        morning_line_at=morning_line(begin, end, zone, settings.digest_time_local),
        clients=clients,
    )


def calendar_window(
    now: datetime, zone: ZoneInfo, days: int
) -> tuple[list[date], datetime, datetime]:
    """The last days calendar days in the zone, ending today, and their
    [start, end) as UTC instants."""
    last = local_date(now, zone)
    first = last - timedelta(days=days - 1)
    start, end = days_bounds(first, last, zone)
    return [first + timedelta(days=offset) for offset in range(days)], start, end


@router.get("/dashboard/trend")
async def dashboard_trend(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    days: DaysQuery = DEFAULT_DAYS,
) -> Trend:
    """Due runs per calendar day in the digest zone (verified, failed and
    silent), oldest day first; today so far is the last day."""
    settings = await app_settings(services, db, principal)
    zone = ZoneInfo(settings.digest_timezone)
    dates, start, end = calendar_window(services.clock.now(), zone, days)
    counts = await DashboardRepository(db, services.policy).trend(
        principal, start=start, end=end, timezone=settings.digest_timezone
    )
    return Trend(
        items=[
            TrendDay(
                date=day,
                verified=counts.get((day, "verified"), 0),
                failed=counts.get((day, "failed"), 0),
                silent=counts.get((day, "overdue"), 0) + counts.get((day, "missed"), 0),
            )
            for day in dates
        ]
    )


@router.get("/dashboard/breakdown")
async def dashboard_breakdown(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    by: BreakdownByOut = "vendor",
    days: DaysQuery = DEFAULT_DAYS,
) -> Breakdown:
    """Due runs of the same days as the trend, per vendor (the parser pack
    of the job) or per client, by label."""
    settings = await app_settings(services, db, principal)
    zone = ZoneInfo(settings.digest_timezone)
    _, start, end = calendar_window(services.clock.now(), zone, days)
    rows = await DashboardRepository(db, services.policy).breakdown(
        principal, by=by, start=start, end=end
    )
    items = [
        BreakdownItem(
            key=row.key or NO_PACK_KEY,
            label=row.label or row.key or NO_PACK_LABEL,
            verified=row.verified,
            failed=row.failed,
            silent=row.silent,
        )
        for row in rows
    ]
    items.sort(key=lambda item: (item.label.casefold(), item.key))
    return Breakdown(by=by, items=items)


@router.get("/activity")
async def list_activity(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    kind: ActivityKindOut | None = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> ActivityPage:
    """What happened, newest first: messages received (ingest), changes of
    job states (flip), configuration changes (config) and, from phase C9,
    notifications. kind narrows the list to one of them."""
    after = None if cursor is None else decode_time_cursor(cursor, "at")
    kinds = ACTIVITY_KINDS if kind is None else frozenset({kind})
    found = await DashboardRepository(db, services.policy).activity(
        principal, kinds=kinds, after=after, limit=limit + 1
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("at", last.at, last.id)
    return ActivityPage(
        items=[
            ActivityItem(
                id=item.id,
                at=item.at,
                kind=item.kind,
                summary=item.summary,
                ref_kind=item.ref_kind,
                ref_id=item.ref_id,
            )
            for item in items
        ],
        next_cursor=next_cursor,
    )


@router.get("/digest/preview")
async def digest_preview(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    day: DayQuery = None,
) -> DigestPreview:
    """The morning digest of date as the ReportRenderer makes it: the runs
    due in the 24 hours up to the digest time of that day. The HTML has no
    script and every name in it is escaped; show it in a sandboxed frame."""
    now = services.clock.now()
    settings = await app_settings(services, db, principal)
    zone = ZoneInfo(settings.digest_timezone)
    chosen = local_date(now, zone) if day is None else check_day(day, "date")
    digest = await build_digest(
        db,
        services.policy,
        principal,
        day=chosen,
        timezone=settings.digest_timezone,
        digest_time=settings.digest_time_local,
        now=now,
        url=f"{services.settings.base_url}/",
    )
    report = services.report_renderer.render(digest)
    return DigestPreview(
        date=chosen, subject=report.subject, html=report.html, text=report.text
    )
