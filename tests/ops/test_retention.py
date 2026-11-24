"""The retention purge (phase C10): only the rows the settings no longer keep.

purge() runs in one transaction on the tick hook's session; these tests drive
it directly with the real settings row and RetainBySettings, on the fake
clock's 2027-01-04 09:00Z. Raw messages go by their purge_after (received_at
plus the retention_raw_days of the day they arrived), results and audit
events by the settings cutoffs, and occurrences by the evaluator's invariant:
open occurrences and the per-job keeper rows stay (docs/evaluator.md).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.models import (
    AppSettings,
    AppUser,
    AuditEvent,
    Flip,
    JobResult,
    Notification,
    Occurrence,
    RawMessage,
)
from app.ext.retention import RetainBySettings, Retention
from app.ingest.results import ParsedResult
from app.ingest.store import record_result, store_raw
from app.ops.retention import PurgeReport, RetentionPurge, purge
from app.repos.inboxes import InboxRepository
from app.repos.notifications import ChannelRepository
from app.settings import load_settings
from app.worker.loop import build_context
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    FakeClock,
    make_client,
    make_job,
    sign_in,
)

NOW = datetime(2027, 1, 4, 9, tzinfo=UTC)
OLD = datetime(2026, 8, 1, 12, tzinfo=UTC)  # older than the raw and results cutoffs
ANCIENT = datetime(2025, 12, 1, 12, tzinfo=UTC)  # older than the audit cutoff too
RECENT = datetime(2027, 1, 3, 9, tzinfo=UTC)
DENTAL, FREIGHT, _ = CLIENT_NAMES
POLICY = AllowAllPolicy()


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
async def inbox(db_engine: AsyncEngine) -> AsyncIterator[uuid.UUID]:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        found, _ = await InboxRepository(db, POLICY).create(
            SYSTEM, kind="smtp", label="Vendor mail", now=RECENT
        )
        await db.commit()
    yield found.id


async def settings_of(db_engine: AsyncEngine) -> AppSettings:
    async with async_sessionmaker(db_engine)() as db:
        return (await db.scalars(select(AppSettings))).one()


async def run_purge(db_engine: AsyncEngine, plan: Retention) -> PurgeReport:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        report = await purge(db, plan)
        await db.commit()
    return report


async def counts(db_engine: AsyncEngine) -> dict[str, int]:
    """Rows per table, for the whole-database assertions."""
    async with db_engine.connect() as connection:
        found: dict[str, int] = {}
        for name, model in (
            ("raw_message", RawMessage),
            ("job_result", JobResult),
            ("occurrence", Occurrence),
            ("flip", Flip),
            ("notification", Notification),
            ("audit_event", AuditEvent),
        ):
            query = select(func.count()).select_from(model)
            found[name] = int((await connection.execute(query)).scalar_one())
        return found


async def add_message(
    db_engine: AsyncEngine, inbox_id: uuid.UUID, received_at: datetime
) -> RawMessage:
    """One stored message; its purge_after is received_at plus 30 days."""
    body = f"Subject: run at {received_at}\r\n\r\nJob: A\r\nResult: Success".encode()
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        found = await store_raw(
            db,
            POLICY,
            SYSTEM,
            inbox_id=inbox_id,
            raw=body,
            received_at=received_at,
        )
        await db.commit()
        row = await db.get(RawMessage, found.id)
        assert row is not None
        return row


async def add_result(
    db_engine: AsyncEngine,
    *,
    job_id: uuid.UUID | None,
    raw_message_id: uuid.UUID | None,
    received_at: datetime,
    status: str = "success",
) -> uuid.UUID:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        row = await record_result(
            db,
            POLICY,
            SYSTEM,
            ParsedResult(status=status),
            received_at=received_at,
            job_id=job_id,
            raw_message_id=raw_message_id,
        )
        await db.commit()
        return row


async def add_occurrences(
    db_engine: AsyncEngine,
    job_id: uuid.UUID,
    at: datetime,
    states: list[str],
) -> list[Occurrence]:
    """Occurrences due one hour apart, oldest first."""
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        rows = []
        for index, state in enumerate(states):
            due = at + timedelta(hours=index)
            row = Occurrence(
                job_id=job_id,
                scheduled_for=due,
                deadline=due + timedelta(hours=8),
                state=state,
                evaluated_at=at,
            )
            db.add(row)
            rows.append(row)
        await db.commit()
        return rows


async def add_history(
    db_engine: AsyncEngine,
    job_id: uuid.UUID,
    client_id: uuid.UUID,
    at: datetime,
) -> tuple[uuid.UUID, uuid.UUID]:
    """One flip at at with a sent and a queued notification about it; the
    ids of the flip and the sent notification."""
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        channel = await ChannelRepository(db, POLICY).create(
            SYSTEM, kind="email", label=f"Ops mail {at}", now=at, config={}
        )
        flip = Flip(
            job_id=job_id,
            client_id=client_id,
            from_state="ok",
            to_state="failing",
            reason="The run was failed",
            at=at,
        )
        db.add(flip)
        await db.flush()
        sent = Notification(
            channel_id=channel.id,
            flip_id=flip.id,
            event="failing",
            status="sent",
            attempts=1,
            created_at=at,
            last_attempt_at=at,
            sent_at=at,
        )
        queued = Notification(
            channel_id=channel.id,
            flip_id=flip.id,
            event="recovered",
            status="queued",
            created_at=at,
            next_attempt_at=at,
        )
        db.add_all([sent, queued])
        await db.commit()
        return flip.id, sent.id


async def add_audit(db_engine: AsyncEngine, at: datetime, action: str) -> None:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        db.add(AuditEvent(at=at, actor="system", action=action))
        await db.commit()


async def occurrences_of(db_engine: AsyncEngine, job_id: uuid.UUID) -> set[datetime]:
    query = select(Occurrence.scheduled_for).where(Occurrence.job_id == job_id)
    async with db_engine.connect() as connection:
        return set((await connection.execute(query)).scalars())


async def test_purge_removes_only_expired_rows(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, inbox: uuid.UUID
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    freight = await make_client(client, csrf, FREIGHT)
    strict = await make_job(
        client,
        csrf,
        dental["id"],
        "Nightly server backup",
        consecutive_failures_to_alert=2,
    )
    plain = await make_job(client, csrf, freight["id"], "Database dump")
    strict_id, plain_id = uuid.UUID(strict["id"]), uuid.UUID(plain["id"])
    dental_id, freight_id = uuid.UUID(dental["id"]), uuid.UUID(freight["id"])

    old_raw = await add_message(db_engine, inbox, OLD)
    new_raw = await add_message(db_engine, inbox, RECENT)
    assert old_raw.purge_after < NOW < new_raw.purge_after
    # The old message's result and a loose old result go; the young ones stay.
    await add_result(
        db_engine, job_id=plain_id, raw_message_id=old_raw.id, received_at=OLD
    )
    kept_result = await add_result(
        db_engine, job_id=strict_id, raw_message_id=new_raw.id, received_at=RECENT
    )
    await add_result(db_engine, job_id=plain_id, raw_message_id=None, received_at=OLD)
    loose_young = await add_result(
        db_engine, job_id=plain_id, raw_message_id=None, received_at=RECENT
    )
    # The strict job (threshold 2): three old failed runs, then maintenance,
    # then an open overdue one; the plain job (threshold 1): two old failed
    # runs and a young verified one.
    strict_old = await add_occurrences(
        db_engine, strict_id, OLD, ["failed", "failed", "failed", "maintenance"]
    )
    open_at = OLD + timedelta(hours=4)
    strict_open = (await add_occurrences(db_engine, strict_id, open_at, ["overdue"]))[0]
    await add_occurrences(db_engine, plain_id, OLD, ["failed", "failed"])
    await add_occurrences(db_engine, plain_id, RECENT, ["verified"])
    await add_history(db_engine, strict_id, dental_id, OLD)
    young_flip, young_sent = await add_history(
        db_engine, plain_id, freight_id, RECENT
    )
    await add_audit(db_engine, ANCIENT, "signin")
    await add_audit(db_engine, OLD, "password.change")

    plan = RetainBySettings().plan(await settings_of(db_engine), NOW)
    assert plan.raw_before == NOW
    assert plan.results_before == NOW - timedelta(days=90)
    assert plan.audit_before == NOW - timedelta(days=365)
    report = await run_purge(db_engine, plan)

    assert report == PurgeReport(
        notifications=2,
        flips=1,
        occurrences=3,
        results=2,
        raw_messages=1,
        audit_events=1,
    )
    found = await counts(db_engine)
    # The sign-in and the client and job creations above wrote audit events
    # of their own, at NOW: only the actions below are compared.
    found.pop("audit_event")
    assert found == {
        "raw_message": 1,
        "job_result": 2,
        "occurrence": 5,
        "flip": 1,
        "notification": 2,
    }
    async with db_engine.connect() as connection:
        actions = set((await connection.execute(select(AuditEvent.action))).scalars())
        # Older than the 365-day cutoff goes; older than 90 days only stays.
        assert "signin" not in actions
        assert "password.change" in actions
        assert set((await connection.execute(select(RawMessage.id))).scalars()) == {
            new_raw.id
        }
        kept = set((await connection.execute(select(JobResult.id))).scalars())
        assert kept == {kept_result, loose_young}
        # The old flip is gone with both its notifications; the young flip
        # keeps its sent and queued rows.
        flips = set((await connection.execute(select(Flip.id))).scalars())
        assert flips == {young_flip}
        query = select(Notification.status).where(Notification.id == young_sent)
        assert (await connection.execute(query)).scalar_one() == "sent"
    # The open overdue occurrence survives although it is old: open failures
    # are kept. The strict job keeps its newest closed occurrence (the
    # maintenance one) and its newest two non-maintenance closed ones.
    kept_strict = await occurrences_of(db_engine, strict_id)
    assert kept_strict == {
        strict_open.scheduled_for,
        strict_old[3].scheduled_for,
        strict_old[2].scheduled_for,
        strict_old[1].scheduled_for,
    }
    # The plain job (threshold 1) keeps only its young verified occurrence:
    # its old runs are dominated by a newer kept one.
    assert await occurrences_of(db_engine, plain_id) == {RECENT}


async def test_purge_without_cutoffs_touches_nothing(
    db_engine: AsyncEngine, inbox: uuid.UUID
) -> None:
    await add_message(db_engine, inbox, OLD)
    await add_result(db_engine, job_id=None, raw_message_id=None, received_at=OLD)
    await add_audit(db_engine, OLD, "signin")
    report = await run_purge(
        db_engine, Retention(raw_before=None, results_before=None, audit_before=None)
    )
    assert report == PurgeReport()
    assert (await counts(db_engine))["raw_message"] == 1


async def test_settings_of_zero_days_keep_everything(db_engine: AsyncEngine) -> None:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        row = (await db.scalars(select(AppSettings))).one()
        row.retention_raw_days = 0
        row.retention_results_days = 0
        row.retention_audit_days = 0
        await db.commit()
    plan = RetainBySettings().plan(await settings_of(db_engine), NOW)
    assert plan == Retention(raw_before=None, results_before=None, audit_before=None)


class CountingPolicy(RetainBySettings):
    """RetainBySettings that counts its plans (the daily gate test)."""

    def __init__(self) -> None:
        self.calls = 0

    def plan(self, row: AppSettings, now: datetime) -> Retention:
        self.calls += 1
        return Retention(None, None, None)


async def test_the_purge_hook_runs_once_a_day(
    db_engine: AsyncEngine, clock: FakeClock
) -> None:
    context = build_context(load_settings(), clock)
    try:
        policy = CountingPolicy()
        hook = RetentionPurge(policy)
        await hook(context, clock.now())
        await hook(context, clock.now())
        assert policy.calls == 1
        clock.advance(days=1)
        await hook(context, clock.now())
        assert policy.calls == 2
        # A restarted worker (a new hook) purges again on its first tick.
        await RetentionPurge(policy)(context, clock.now())
        assert policy.calls == 3
    finally:
        await context.engine.dispose()
