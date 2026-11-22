"""The notification dispatcher (phase C9-B) on PostgreSQL with the fake clock:
one notification per flip and channel, never two on a double tick; the retry
ladder of 1, 5 and 30 minutes, then failed; one recovery notice; the 24-hour
reminder; NotificationSent after the commit; the queue counts.

Deliveries go to a fake kind registered as email, so nothing leaves the test.
Clients and jobs are synthetic (legal R-11: fictional companies).
"""

import dataclasses
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM
from app.db.models import (
    AppSettings,
    Channel,
    Client,
    Flip,
    Job,
    Notification,
    name_key,
)
from app.evaluator.tick import Evaluator, evaluate_jobs
from app.ext.events import Event, FlipCreated, NotificationSent
from app.ext.notifications import DeliveryError, Message, Outbound
from app.ingest.results import ParsedResult
from app.ingest.store import record_result
from app.notify.dispatcher import (
    RETRY_DELAYS,
    Dispatcher,
    NotificationQueue,
    dispatch_notifications,
    event_of,
    retry_delay,
)
from app.notify.registry import KindRegistry
from app.repos.notifications import (
    ChannelRepository,
    ChannelRuleRepository,
    NotificationRepository,
)
from app.security.crypto import MASK
from app.security.tokens import new_ping_token
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import CLIENT_NAMES, FakeClock

DENTAL, FREIGHT, _ = CLIENT_NAMES
NIGHTLY = "Nightly server backup"
CREATED = datetime(2027, 1, 4, 12, tzinfo=UTC)
# Daily 23:00 Europe/Lisbon with the default rules: missed from 07:30Z.
MISSED_AT = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)
# A secret-looking relay password that must never be stored in clear.
SECRET = "Canary-relay-" + "s" * 16


class FakeKind:
    """Registered as email; fails the next `failures` sends, then delivers.
    Its errors repeat the secret, so the redaction is tested too."""

    name = "email"
    secret_label = "Relay password"
    secret_targets = frozenset({"host"})

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.tries = 0
        self.failures = 0

    def check_config(
        self, config: Mapping[str, Any], *, has_secret: bool
    ) -> dict[str, Any]:
        return dict(config)

    async def send(
        self,
        config: Mapping[str, Any],
        secret: str | None,
        message: Message,
        outbound: Outbound,
    ) -> None:
        self.tries += 1
        if self.failures:
            self.failures -= 1
            raise DeliveryError(f"The relay said no to {secret}.")
        self.sent.append(message)


class Recorder:
    """A subscriber that keeps the NotificationSent events and the status the
    database shows when each arrives."""

    name = "recorder"

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sent: list[tuple[NotificationSent, str]] = []

    async def handle(self, event: Event) -> None:
        if not isinstance(event, NotificationSent):
            return
        async with self.engine.connect() as connection:
            query = select(Notification.status).where(
                Notification.id == event.notification_id
            )
            stored = (await connection.execute(query)).scalar_one()
        self.sent.append((event, stored))


@pytest.fixture
def kind() -> FakeKind:
    return FakeKind()


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock, kind: FakeKind
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield dataclasses.replace(built, kinds=KindRegistry([kind]))
    await built.engine.dispose()


def at(clock: FakeClock, moment: datetime) -> None:
    clock.advance(seconds=(moment - clock.now()).total_seconds())


async def tick(context: WorkerContext) -> None:
    """The evaluator and the dispatcher, as one worker tick runs them."""
    now = context.clock.now()
    await evaluate_jobs(context, now)
    await dispatch_notifications(context, now)


async def add_client(context: WorkerContext, name: str = DENTAL) -> Client:
    client = Client(name=name, name_key=name_key(name), created_at=CREATED)
    async with context.sessionmaker() as db:
        db.add(client)
        await db.commit()
    return client


async def add_job(context: WorkerContext, client: Client, name: str = NIGHTLY) -> Job:
    """A daily 23:00 Europe/Lisbon job of the client."""
    job = Job(
        client_id=client.id,
        name=name,
        name_key=name_key(name),
        kind="backup",
        schedule_kind="daily",
        schedule_expr="23:00",
        timezone="Europe/Lisbon",
        ping_token=new_ping_token(),
        created_at=CREATED,
        updated_at=CREATED,
    )
    async with context.sessionmaker() as db:
        db.add(job)
        await db.commit()
    return job


async def add_channel(
    context: WorkerContext,
    label: str = "Ops mail",
    *,
    enabled: bool = True,
    secret: str | None = None,
) -> Channel:
    async with context.sessionmaker() as db:
        channel = await ChannelRepository(db, context.policy).create(
            SYSTEM,
            kind="email",
            label=label,
            now=context.clock.now(),
            enabled=enabled,
            config={"host": "relay.example.com"},
            secret_enc=None if secret is None else context.secret_box.encrypt(secret),
        )
        await db.commit()
    return channel


async def add_rule(
    context: WorkerContext,
    channel: Channel,
    events: list[str],
    scope: str = "all",
    scope_id: uuid.UUID | None = None,
) -> None:
    async with context.sessionmaker() as db:
        await ChannelRuleRepository(db, context.policy).create(
            SYSTEM,
            channel_id=channel.id,
            scope=scope,
            scope_id=scope_id,
            events=events,
            now=context.clock.now(),
        )
        await db.commit()


async def report(
    context: WorkerContext, job: Job, status: str, finished: datetime
) -> None:
    async with context.sessionmaker() as db:
        await record_result(
            db,
            context.policy,
            SYSTEM,
            ParsedResult(status=status, finished_at=finished),
            received_at=finished + timedelta(minutes=1),
            job_id=job.id,
        )
        await db.commit()


async def notifications(engine: AsyncEngine) -> list[Notification]:
    query = select(Notification).order_by(Notification.created_at, Notification.id)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        return list((await db.scalars(query)).all())


async def stored_channel(engine: AsyncEngine, channel: Channel) -> Any:
    async with engine.connect() as connection:
        query = select(Channel).where(Channel.id == channel.id)
        return (await connection.execute(query)).one()


def test_flips_map_to_events() -> None:
    assert event_of("unknown", "missed") == "missed"
    assert event_of("ok", "failing") == "failing"
    assert event_of("ok", "warning") == "warning"
    assert event_of("warning", "failing") == "failing"
    for problem in ("failing", "missed", "warning"):
        assert event_of(problem, "ok") == "recovered"
    for quiet in (("unknown", "ok"), ("ok", "paused"), ("missed", "maintenance")):
        assert event_of(*quiet) is None
    assert [retry_delay(n) for n in range(1, 5)] == [*RETRY_DELAYS, None]
    assert RETRY_DELAYS == (
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=30),
    )


async def test_one_notification_per_flip_and_channel_never_two(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    dental = await add_client(context)
    freight = await add_client(context, FREIGHT)
    job = await add_job(context, dental)
    other = await add_job(context, freight, "Weekly image backup")
    # Two matching rules on one channel give one notification.
    ops = await add_channel(context, "Ops mail")
    await add_rule(context, ops, ["missed"])
    await add_rule(context, ops, ["missed", "failing"], "client", dental.id)
    # A rule for the job itself matches; the others do not.
    desk = await add_channel(context, "Service desk")
    await add_rule(context, desk, ["missed"], "job", job.id)
    quiet = await add_channel(context, "Warnings only")
    await add_rule(context, quiet, ["warning", "recovered"])
    elsewhere = await add_channel(context, "Other client")
    await add_rule(context, elsewhere, ["missed"], "job", other.id)
    off = await add_channel(context, "Disabled", enabled=False)
    await add_rule(context, off, ["missed"])

    at(clock, MISSED_AT)
    await evaluate_jobs(context, clock.now())
    # The freight job missed too: it has its own flip, for the other channel.
    queued = await notifications(db_engine)
    channels = {row.channel_id for row in queued}
    assert channels == {ops.id, desk.id, elsewhere.id}
    assert len(queued) == 4
    assert {row.status for row in queued} == {"queued"}

    await dispatch_notifications(context, clock.now())
    # A second tick at the same time, and the same flip delivered again.
    await tick(context)
    async with context.sessionmaker() as db:
        flip = (await db.scalars(select(Flip).where(Flip.job_id == job.id))).one()
    again = FlipCreated(
        flip_id=flip.id,
        job_id=job.id,
        client_id=dental.id,
        from_state=flip.from_state,
        to_state=flip.to_state,
        reason=flip.reason,
        at=flip.at,
    )
    queue = NotificationQueue(context.sessionmaker, context.policy, context.clock)
    await queue.handle(again)
    await tick(context)

    sent = await notifications(db_engine)
    assert len(sent) == 4
    outcomes = {(row.status, row.attempts, row.event) for row in sent}
    assert outcomes == {("sent", 1, "missed")}
    assert kind.tries == 4
    dental_mail = [m for m in kind.sent if m.flip and m.flip.job_id == job.id]
    assert len(dental_mail) == 2
    first = dental_mail[0]
    assert first.subject == f"Checkorca-CE: {DENTAL} / {NIGHTLY} missed its run"
    assert first.url == f"http://localhost:8080/jobs/{job.id}"
    assert "State: unknown to missed" in first.text
    assert "(Europe/Lisbon)" in first.text
    assert (await stored_channel(db_engine, ops)).last_status == "sent"


async def test_the_retry_ladder_then_failed(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    recorder = Recorder(db_engine)
    context = dataclasses.replace(context, subscribers=(*context.subscribers, recorder))
    job = await add_job(context, await add_client(context))
    channel = await add_channel(context, secret=SECRET)
    await add_rule(context, channel, ["missed"])
    kind.failures = 100

    at(clock, MISSED_AT)
    await tick(context)
    (row,) = await notifications(db_engine)
    assert (row.status, row.attempts) == ("retrying", 1)
    assert row.next_attempt_at == MISSED_AT + timedelta(minutes=1)
    # The error is stored without the secret.
    assert row.error == f"The relay said no to {MASK}."
    expected = [(1, "retrying"), (2, "retrying"), (3, "retrying"), (4, "failed")]
    waits = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30)]
    seen = [(row.attempts, row.status)]
    for wait in waits:
        # One second early: nothing happens.
        clock.advance(seconds=wait.total_seconds() - 1)
        await tick(context)
        assert kind.tries == len(seen)
        clock.advance(seconds=1)
        await tick(context)
        (row,) = await notifications(db_engine)
        seen.append((row.attempts, row.status))
    assert seen == expected
    assert row.next_attempt_at is None and row.sent_at is None
    assert row.last_attempt_at == clock.now()
    clock.advance(hours=3)
    await tick(context)
    assert kind.tries == 4 and kind.sent == []
    stored = await stored_channel(db_engine, channel)
    assert stored.last_status == "failed"
    assert stored.last_error == f"The relay said no to {MASK}."
    assert stored.secret_enc != SECRET and SECRET not in stored.secret_enc
    # NotificationSent once, for the final outcome, after the commit.
    ((event, status),) = recorder.sent
    assert (event.status, status, event.channel_id) == ("failed", "failed", channel.id)
    async with context.sessionmaker() as db:
        counts = await NotificationRepository(db, context.policy).queue_counts(
            SYSTEM, failed_since=clock.now() - timedelta(hours=24)
        )
    assert counts == (0, 1)


async def test_a_retry_that_succeeds_is_sent(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    recorder = Recorder(db_engine)
    context = dataclasses.replace(context, subscribers=(*context.subscribers, recorder))
    await add_job(context, await add_client(context))
    await add_rule(context, await add_channel(context), ["missed"])
    kind.failures = 2
    at(clock, MISSED_AT)
    await tick(context)
    async with context.sessionmaker() as db:
        counts = await NotificationRepository(db, context.policy).queue_counts(
            SYSTEM, failed_since=CREATED
        )
    assert counts == (1, 0)
    clock.advance(minutes=1)
    await tick(context)
    clock.advance(minutes=5)
    await tick(context)
    (row,) = await notifications(db_engine)
    assert (row.status, row.attempts, row.error) == ("sent", 3, None)
    assert row.sent_at == clock.now()
    outcomes = [(event.status, status) for event, status in recorder.sent]
    assert outcomes == [("sent", "sent")]


async def test_a_recovery_gives_one_notice(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    job = await add_job(context, await add_client(context))
    await add_rule(context, await add_channel(context), ["missed", "recovered"])
    at(clock, MISSED_AT)
    await tick(context)
    # A late success: the missed run becomes verified, one recovery flip.
    await report(context, job, "success", MISSED_AT + timedelta(minutes=10))
    clock.advance(minutes=15)
    await tick(context)
    await tick(context)
    clock.advance(hours=2)
    await tick(context)
    assert [message.event for message in kind.sent] == ["missed", "recovered"]
    recovered = kind.sent[1]
    assert recovered.subject.endswith(f"{NIGHTLY} recovered")
    assert "State: missed to ok" in recovered.text
    rows = await notifications(db_engine)
    assert [(row.event, row.status) for row in rows] == [
        ("missed", "sent"),
        ("recovered", "sent"),
    ]


async def test_a_channel_disabled_before_the_send_fails_at_once(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    await add_job(context, await add_client(context))
    channel = await add_channel(context)
    await add_rule(context, channel, ["missed"])
    at(clock, MISSED_AT)
    await Evaluator(context).run(clock.now())
    async with context.sessionmaker() as db:
        await db.execute(
            update(Channel).where(Channel.id == channel.id).values(enabled=False)
        )
        await db.commit()
    outcome = await Dispatcher(context).run(clock.now())
    assert (outcome.sent, outcome.failed) == (0, 1)
    (row,) = await notifications(db_engine)
    assert (row.status, row.attempts) == ("failed", 1)
    assert row.error == "The channel is disabled."
    assert kind.tries == 0


async def set_reminders(engine: AsyncEngine, enabled: bool) -> None:
    async with engine.begin() as connection:
        await connection.execute(update(AppSettings).values(reminder_24h=enabled))


async def test_the_24_hour_reminder_is_off_by_default_and_sent_once(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    job = await add_job(context, await add_client(context))
    await add_rule(context, await add_channel(context), ["missed"])
    at(clock, MISSED_AT)
    await tick(context)
    at(clock, MISSED_AT + timedelta(hours=24, minutes=1))
    await tick(context)
    assert [message.event for message in kind.sent] == ["missed"]

    await set_reminders(db_engine, True)
    await tick(context)
    clock.advance(minutes=30)
    await tick(context)
    assert [message.event for message in kind.sent] == ["missed", "reminder"]
    reminder = kind.sent[1]
    assert reminder.subject.endswith("has still not reported after 24 hours")
    assert reminder.flip is not None and reminder.flip.job_id == job.id
    rows = await notifications(db_engine)
    assert [row.event for row in rows] == ["missed", "reminder"]
    # Out of the window, the setting reminds of nothing older.
    clock.advance(hours=3)
    await tick(context)
    assert len(kind.sent) == 2


async def test_no_reminder_for_an_acknowledged_or_recovered_job(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    await set_reminders(db_engine, True)
    dental = await add_client(context)
    acknowledged = await add_job(context, dental)
    recovered = await add_job(context, dental, "Database dump")
    await add_rule(context, await add_channel(context), ["missed", "recovered"])
    at(clock, MISSED_AT)
    await tick(context)
    async with context.sessionmaker() as db:
        await db.execute(
            update(Job)
            .where(Job.id == acknowledged.id)
            .values(acknowledged_at=clock.now())
        )
        await db.commit()
    await report(context, recovered, "success", MISSED_AT + timedelta(minutes=5))
    clock.advance(minutes=10)
    await tick(context)
    # The next night's run of the recovered job reports too: it stays ok.
    next_night = datetime(2027, 1, 5, 23, 10, tzinfo=UTC)
    await report(context, recovered, "success", next_night)
    at(clock, MISSED_AT + timedelta(hours=24, minutes=5))
    await tick(context)
    events = sorted(message.event for message in kind.sent)
    assert events == ["missed", "missed", "recovered"]
