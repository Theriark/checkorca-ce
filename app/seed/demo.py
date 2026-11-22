"""Development demo data (dev-work-plan C8-B item 3).

With DEV_DEMO_DATA=1 on a seed host (BASE_URL host ce-dev-*, ce-stg-* or
localhost, as for the seed accounts) the worker seeds, once: 20 fictional
clients (legal R-11) with the note "Seed data", 60 jobs (every CE parser
pack, plus scripts that report through their ping URL) and one SMTP inbox,
then 14 days of their history. settings.demo_seeded is set at the end; a
second run adds nothing.

The history goes through the real pipeline on an injected clock that walks
the 14 days: each alert mail is checked and stored by accept_message (the
receivers' path), each ping is recorded by record_result (the ping route's
path), then the worker's parse hook and the evaluator run every STEP of
simulated time. So the occurrences, flips, job states and Unmatched results
are the ones the product makes itself. Some jobs never report (silent),
some stopped reporting three days ago, some fail, some warn, one hourly
script is overdue right now, two jobs are paused and three mails wait in
Unmatched.

The seed runs as the first tick hook while the worker holds the worker lock,
so no other evaluator runs meanwhile; the replay evaluates the demo jobs
only and leaves every other job to the next tick. It keeps the heartbeat
fresh while it runs. Times follow the moment it runs, so the data ages from
then on (phase C11-B makes the seed deterministic, D-10).
"""

import dataclasses
import logging
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from app.access import SYSTEM
from app.db.models import Client, Inbox, Job
from app.evaluator.tick import Evaluator
from app.ext.audit import AuditRecord, DatabaseAuditSink
from app.ingest.receive import accept_message
from app.ingest.results import ParsedResult
from app.ingest.store import record_result
from app.repos.clients import ClientRepository
from app.repos.heartbeat import HeartbeatRepository
from app.repos.inboxes import InboxRepository
from app.repos.jobs import JobRepository
from app.repos.messages import RawMessageRepository
from app.repos.settings import SettingsRepository
from app.schedule import occurrences, parse_spec
from app.seed.accounts import SeedError, check_seed_host
from app.seed.demo_mail import NAMES_CLIENT, Outcome, Run, render_mail
from app.worker.parse import ParseHook

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

logger = logging.getLogger(__name__)

SEED_NOTE: Final = "Seed data"
DAYS: Final = 14
# Simulated time between two runs of the parse hook and the evaluator.
STEP: Final = timedelta(hours=3)
ZONE: Final = "Europe/Lisbon"
INBOX_LABEL: Final = "Demo alerts (seed data)"
MESSAGE_DOMAIN: Final = "seed.example.com"

# Fictional companies (legal R-11); the short name starts the names of jobs
# whose vendor mail does not name the client.
CLIENTS: Final[tuple[tuple[str, str], ...]] = (
    ("Quillfern Dental Studio", "Quillfern"),
    ("Brackenmoor Law Partners", "Brackenmoor"),
    ("Tidewick Accounting", "Tidewick"),
    ("Orchardvale Veterinary", "Orchardvale"),
    ("Lanternbrook Architects", "Lanternbrook"),
    ("Copperwell Logistics", "Copperwell"),
    ("Mistralyn Travel", "Mistralyn"),
    ("Fernhollow Pharmacy", "Fernhollow"),
    ("Saltmarsh Print Works", "Saltmarsh"),
    ("Kestrelby Engineering", "Kestrelby"),
    ("Wrenfield Primary Trust", "Wrenfield"),
    ("Amberlock Insurance Brokers", "Amberlock"),
    ("Driftmere Hotels", "Driftmere"),
    ("Thornquill Publishing", "Thornquill"),
    ("Pebblecroft Physiotherapy", "Pebblecroft"),
    ("Hollowmere Estate Agents", "Hollowmere"),
    ("Glimmerdale Opticians", "Glimmerdale"),
    ("Larkspur Row Bakery", "Larkspur"),
    ("Ironvale Machining", "Ironvale"),
    ("Bramblecote Care Homes", "Bramblecote"),
)
# The source of each job, in turn: the eight CE parser packs, then a script
# with a ping URL. Three in a row are never the same, so a client's three
# jobs have three sources.
SOURCES: Final = (
    "veeam-br",
    "synology-abb",
    "synology-hyperbackup",
    "acronis-cp-legacy",
    "acronis-cp-cloud",
    "nable-cove",
    "msp360",
    "generic-keywords",
    "ping",
)
JOBS_PER_CLIENT: Final = 3
DAILY_TIMES: Final = (
    "19:30",
    "20:00",
    "21:00",
    "21:30",
    "22:00",
    "22:30",
    "23:00",
    "23:30",
    "00:30",
    "01:00",
    "02:00",
    "03:00",
)

Profile = Literal[
    "healthy", "flaky", "failing", "warning", "stopped", "never", "overdue"
]
# How jobs behave, by job number (0 to 59); the others are healthy.
PROFILE_GROUPS: Final[tuple[tuple[Profile, tuple[int, ...]], ...]] = (
    ("never", (4, 17, 31, 46)),
    ("stopped", (10, 29, 57)),
    ("failing", (2, 14, 23, 39, 51)),
    ("warning", (6, 21, 40, 55)),
    ("flaky", (0, 12, 19, 27, 34, 45, 48, 58)),
    ("overdue", (8,)),
)
PROFILES: Final[dict[int, Profile]] = {
    number: profile for profile, numbers in PROFILE_GROUPS for number in numbers
}
# Jobs paused at the end of the seed.
PAUSED: Final = frozenset({15, 49})
# Jobs that run once a week (Saturday 03:00).
WEEKLY: Final = frozenset({5, 33})
# A stopped job sent nothing for this long.
STOPPED_FOR: Final = timedelta(days=3)
# The hourly script of the overdue profile sent nothing for this long: its
# runs since are overdue (deadline after 45 minutes, missed 2 hours later).
OVERDUE_FOR: Final = timedelta(minutes=150)
# Mails for a job nobody created, some days ago: they wait in Unmatched.
UNMATCHED_DAYS: Final = (1, 4, 9)
UNMATCHED_JOB: Final = "Tape rotation backup"
UNMATCHED_CLIENT: Final = "Example Archive Services"


@dataclass(frozen=True, slots=True)
class DemoJob:
    """One demo job: its number, client, name, source and schedule."""

    number: int
    client: str
    name: str
    source: str
    kind: str
    schedule_kind: str
    schedule_expr: str
    max_runtime_minutes: int
    grace_minutes: int
    escalate_minutes: int
    profile: Profile

    @property
    def pack_id(self) -> str | None:
        return None if self.source == "ping" else self.source


def _job_name(source: str, short: str, number: int) -> str:
    """Vendors whose mail names the client may reuse a name across clients;
    the others get the client's short name in front."""
    if source in NAMES_CLIENT:
        return {
            "acronis-cp-cloud": "SRV-DC-01",
            "nable-cove": "FS-02",
            "msp360": "Daily Files",
            "generic-keywords": "Nightly server backup",
        }[source]
    if source == "ping":
        return ("Certificate renewal script", "Database export script")[number % 2]
    if source == "acronis-cp-legacy":
        return f"{short.upper()}-FS01"
    return {
        "veeam-br": f"{short} VM backup",
        "synology-abb": f"{short} office PCs",
        "synology-hyperbackup": f"{short} offsite copy",
    }[source]


def _schedule(
    source: str, number: int, profile: Profile
) -> tuple[str, str, int, int, int]:
    """kind, expression, max runtime, grace and escalation minutes."""
    if profile == "overdue":
        return "cron", "0 * * * *", 30, 15, 120
    if source == "ping":
        if number % 2:
            return "cron", "15 */6 * * *", 60, 30, 30
        return "daily", "04:00", 60, 30, 30
    if number in WEEKLY:
        return "cron", "0 3 * * 6", 180, 60, 30
    return "daily", DAILY_TIMES[number % len(DAILY_TIMES)], 180, 60, 30


def demo_plan() -> list[DemoJob]:
    """The 60 demo jobs, three per client."""
    jobs: list[DemoJob] = []
    for index, (client, short) in enumerate(CLIENTS):
        for slot in range(JOBS_PER_CLIENT):
            number = index * JOBS_PER_CLIENT + slot
            source = SOURCES[number % len(SOURCES)]
            profile = PROFILES.get(number, "healthy")
            kind, expr, runtime, grace, escalate = _schedule(source, number, profile)
            jobs.append(
                DemoJob(
                    number=number,
                    client=client,
                    name=_job_name(source, short, number),
                    source=source,
                    kind="script" if source == "ping" else "backup",
                    schedule_kind=kind,
                    schedule_expr=expr,
                    max_runtime_minutes=runtime,
                    grace_minutes=grace,
                    escalate_minutes=escalate,
                    profile=profile,
                )
            )
    return jobs


@dataclass(frozen=True, slots=True)
class Event:
    """Something that arrives at a moment: a mail (raw) or a ping (status)."""

    at: datetime
    job_number: int | None
    raw: bytes | None = None
    status: Literal["success", "failed"] | None = None


def _runtime(job: DemoJob, rng: random.Random) -> timedelta:
    if job.profile == "overdue":
        return timedelta(minutes=rng.randint(1, 3), seconds=rng.randint(0, 59))
    if job.source == "ping":
        return timedelta(minutes=rng.randint(2, 10), seconds=rng.randint(0, 59))
    return timedelta(minutes=rng.randint(8, 75), seconds=rng.randint(0, 59))


def _outcomes(
    job: DemoJob, runs: Sequence[datetime], now: datetime
) -> list[Outcome | None]:
    """The outcome of each run (None: it never reported)."""
    found: list[Outcome | None] = []
    last = len(runs) - 1
    for index, moment in enumerate(runs):
        rng = random.Random(f"{job.number}-{moment.isoformat()}-outcome")
        outcome: Outcome | None = "success"
        if job.profile == "never":
            outcome = None
        elif job.profile == "stopped" and moment >= now - STOPPED_FOR:
            outcome = None
        elif job.profile == "overdue" and moment >= now - OVERDUE_FOR:
            outcome = None
        elif job.profile == "failing" and index >= last - 1:
            outcome = "failed"
        elif job.profile == "warning" and index == last:
            outcome = "warning"
        elif job.profile == "flaky" and index < last and rng.random() < 0.2:
            outcome = "failed"
        elif job.profile == "healthy" and rng.random() < 0.05:
            outcome = "warning"
        found.append(outcome)
    return found


def job_events(job: DemoJob, start: datetime, now: datetime) -> list[Event]:
    """The mails or pings of the job's runs due from start that reported
    before now."""
    spec = parse_spec(job.schedule_kind, job.schedule_expr, ZONE, start)
    reported: list[tuple[datetime, datetime]] = []
    for moment in occurrences(spec, start, now):
        rng = random.Random(f"{job.number}-{moment.isoformat()}-runtime")
        finished = moment + timedelta(minutes=1) + _runtime(job, rng)
        if finished <= now:
            reported.append((moment, finished))
    outcomes = _outcomes(job, [moment for moment, _ in reported], now)
    events: list[Event] = []
    pack_id = job.pack_id
    for (moment, finished), outcome in zip(reported, outcomes, strict=True):
        if outcome is None:
            continue
        if pack_id is None:
            status: Literal["success", "failed"] = (
                "failed" if outcome == "failed" else "success"
            )
            events.append(Event(at=finished, job_number=job.number, status=status))
            continue
        run = Run(
            job=job.name,
            client=job.client,
            outcome=outcome,
            started=moment + timedelta(minutes=1),
            finished=finished,
            message_id=f"<demo-{job.number:02d}-{moment:%Y%m%d%H%M}@{MESSAGE_DOMAIN}>",
        )
        raw = render_mail(pack_id, run)
        events.append(Event(at=finished, job_number=job.number, raw=raw))
    return events


def unmatched_events(now: datetime) -> list[Event]:
    """Mails for a job nobody created: their results wait in Unmatched."""
    events: list[Event] = []
    for days in UNMATCHED_DAYS:
        day = (now - timedelta(days=days)).replace(
            hour=5, minute=12, second=0, microsecond=0
        )
        run = Run(
            job=UNMATCHED_JOB,
            client=UNMATCHED_CLIENT,
            outcome="failed",
            started=day - timedelta(minutes=10),
            finished=day,
            message_id=f"<demo-unmatched-{day:%Y%m%d}@{MESSAGE_DOMAIN}>",
        )
        events.append(
            Event(at=day, job_number=None, raw=render_mail("generic-keywords", run))
        )
    return events


class SimulatedClock:
    """The seed's clock: now() walks the simulated days; monotonic() is
    real, so the parse hook and the evaluator keep their time budgets."""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass
class DemoReport:
    """What the seed did, for the log and the tests."""

    seeded: bool = False
    clients: int = 0
    jobs: int = 0
    mails: int = 0
    pings: int = 0
    ticks: int = 0
    reason: str = ""


async def _keep_alive(context: "WorkerContext") -> None:
    """Write the heartbeat again (real time): the seed runs inside one tick
    and /readyz wants a heartbeat younger than 3 minutes."""
    async with context.sessionmaker() as db:
        heartbeats = HeartbeatRepository(db, context.policy)
        row = await heartbeats.get(SYSTEM)
        if row is None:
            return
        await heartbeats.beat(
            SYSTEM,
            at=context.clock.now(),
            holder=row.holder,
            started_at=row.started_at,
        )
        await db.commit()


async def _create(
    context: "WorkerContext", plan: Sequence[DemoJob], created: datetime
) -> tuple[Inbox, dict[int, Job]] | None:
    """The clients, jobs and inbox, in one transaction; None when demo
    clients exist already (an interrupted earlier seed)."""
    async with context.sessionmaker() as db:
        clients = ClientRepository(db, context.policy)
        for name, _ in CLIENTS:
            if await clients.find_by_name(SYSTEM, name) is not None:
                return None
        by_name: dict[str, Client] = {}
        for name, _ in CLIENTS:
            by_name[name] = await clients.create(
                SYSTEM, name=name, notes=SEED_NOTE, aliases=[], now=created
            )
        jobs = JobRepository(db, context.policy)
        made: dict[int, Job] = {}
        for item in plan:
            made[item.number] = await jobs.create(
                SYSTEM,
                client_id=by_name[item.client].id,
                name=item.name,
                now=created,
                kind=item.kind,
                parser_pack_id=item.pack_id,
                schedule_kind=item.schedule_kind,
                schedule_expr=item.schedule_expr,
                timezone=ZONE,
                max_runtime_minutes=item.max_runtime_minutes,
                grace_minutes=item.grace_minutes,
                escalate_minutes=item.escalate_minutes,
            )
        inbox, _ = await InboxRepository(db, context.policy).create(
            SYSTEM, kind="smtp", label=INBOX_LABEL, now=created
        )
        await db.commit()
    return inbox, made


async def _deliver(
    context: "WorkerContext",
    inbox: Inbox,
    jobs: dict[int, Job],
    events: Sequence[Event],
    report: DemoReport,
) -> None:
    """Store the mails and record the pings, in one transaction."""
    if not events:
        return
    async with context.sessionmaker() as db:
        for event in events:
            if event.raw is not None:
                await accept_message(
                    db,
                    context.policy,
                    SYSTEM,
                    inbox=inbox,
                    raw=event.raw,
                    received_at=event.at,
                )
                report.mails += 1
            elif event.status is not None and event.job_number is not None:
                await record_result(
                    db,
                    context.policy,
                    SYSTEM,
                    ParsedResult(status=event.status, details={"source": "ping"}),
                    received_at=event.at,
                    job_id=jobs[event.job_number].id,
                )
                report.pings += 1
        await db.commit()


async def _replay(
    context: "WorkerContext",
    inbox: Inbox,
    jobs: dict[int, Job],
    events: Sequence[Event],
    start: datetime,
    now: datetime,
    report: DemoReport,
) -> None:
    """Walk the simulated time: deliver what arrived, parse, evaluate."""
    clock = SimulatedClock(start)
    simulated = dataclasses.replace(context, clock=clock)
    evaluator = Evaluator(simulated, only=frozenset(job.id for job in jobs.values()))
    parse = ParseHook()
    pending = sorted(events, key=lambda event: event.at)
    position = 0
    moment = start
    while True:
        moment = min(moment + STEP, now)
        arrived: list[Event] = []
        while position < len(pending) and pending[position].at <= moment:
            arrived.append(pending[position])
            position += 1
        await _deliver(context, inbox, jobs, arrived, report)
        clock.current = moment
        await parse(simulated, moment)
        await evaluator.run(moment)
        report.ticks += 1
        await _keep_alive(context)
        if moment >= now:
            break
    # Whatever the parse budget left behind, then the final evaluation.
    for _ in range(10):
        async with context.sessionmaker() as db:
            left = await RawMessageRepository(db, context.policy).pending_count(SYSTEM)
        if not left:
            break
        await parse(simulated, now)
    await evaluator.run(now)


def check_demo_host(base_url: str) -> None:
    """The host rule of the seed accounts: ce-dev-*, ce-stg-* or localhost."""
    try:
        check_seed_host(base_url)
    except SeedError:
        raise SeedError(
            "DEV_DEMO_DATA=1 is refused: the BASE_URL host must start with "
            "ce-dev- or ce-stg- or be localhost"
        ) from None


async def seed_demo(context: "WorkerContext", now: datetime) -> DemoReport:
    """Seed the demo data once (see the module text). SeedError when the
    host is not a seed host."""
    check_demo_host(context.settings.base_url)
    report = DemoReport()
    async with context.sessionmaker() as db:
        settings = SettingsRepository(db, context.policy, context.secret_box)
        if (await settings.get(SYSTEM)).demo_seeded:
            report.reason = "already seeded"
            return report
    now = now.astimezone(UTC)
    start = now - timedelta(days=DAYS)
    created = start - timedelta(hours=1)
    plan = demo_plan()
    made = await _create(context, plan, created)
    if made is None:
        report.reason = "demo clients exist already"
        logger.warning("demo seed: demo clients exist already; not seeded again")
    else:
        inbox, jobs = made
        report.clients = len(CLIENTS)
        report.jobs = len(jobs)
        events = [event for job in plan for event in job_events(job, start, now)]
        events += unmatched_events(now)
        await _replay(context, inbox, jobs, events, start, now, report)
        async with context.sessionmaker() as db:
            repository = JobRepository(db, context.policy)
            for number in sorted(PAUSED):
                job = await repository.get(SYSTEM, jobs[number].id, for_update=True)
                if job is not None:
                    await repository.update(SYSTEM, job, enabled=False, updated_at=now)
            await db.commit()
        report.seeded = True
    async with context.sessionmaker() as db:
        settings = SettingsRepository(db, context.policy, context.secret_box)
        await settings.mark_demo_seeded(SYSTEM)
        await DatabaseAuditSink().record(
            db,
            AuditRecord(
                at=context.clock.now(),
                actor="system",
                action="seed.demo",
                details={
                    "clients": report.clients,
                    "jobs": report.jobs,
                    "mails": report.mails,
                    "pings": report.pings,
                },
            ),
        )
        await db.commit()
    return report


class DemoSeedHook:
    """The first tick hook: with DEV_DEMO_DATA=1, seed once per process
    (settings.demo_seeded keeps it to once per database). A refused host or
    a failure is logged; the worker goes on."""

    def __init__(self) -> None:
        self.done = False

    async def __call__(self, context: "WorkerContext", now: datetime) -> None:
        if not context.settings.dev_demo_data or self.done:
            return
        self.done = True
        try:
            report = await seed_demo(context, now)
        except SeedError as error:
            logger.error("demo seed refused: %s", error)
            return
        if report.seeded:
            logger.info(
                "demo seed: %d clients, %d jobs, %d mails, %d pings in %d steps",
                report.clients,
                report.jobs,
                report.mails,
                report.pings,
                report.ticks,
            )


seed_demo_data = DemoSeedHook()
