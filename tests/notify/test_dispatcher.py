"""The notification dispatcher (phase C9-B) on PostgreSQL with the fake clock:
one notification per flip and channel, never two on a double tick; the retry
ladder of 1, 5 and 30 minutes, then failed; one recovery notice; the 24-hour
reminder; NotificationSent after the commit; the queue counts.

Deliveries go to a fake kind registered as email, so nothing leaves the test.
Clients and jobs are synthetic (legal R-11: fictional companies).
"""

import dataclasses
import logging
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
from helpers import (
    CLIENT_NAMES,
    URL_CANARY,
    FakeClock,
    HttpCapture,
    http_answer,
    validate_webhook_payload,
)

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
        # Raise an unexpected error whose text holds the secret.
        self.crash = False

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
        if self.crash:
            raise RuntimeError(f"the socket library printed {secret}")
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
    context: WorkerContext,
    kind: FakeKind,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.ops.metrics import registry

    before = registry.get_sample_value("checkorca_notification_failures_total")
    caplog.set_level(logging.DEBUG, logger="app")
    recorder = Recorder(db_engine)
    context = dataclasses.replace(context, subscribers=(*context.subscribers, recorder))
    await add_job(context, await add_client(context))
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
    # The worker's log never holds the relay password either (D-6).
    assert "failed after 4 attempts" in caplog.text
    assert SECRET not in caplog.text
    # The failure counter moved by exactly this one final failure (C10-B).
    after = registry.get_sample_value("checkorca_notification_failures_total")
    assert after == (before or 0.0) + 1.0


async def test_an_unexpected_kind_error_is_stored_and_logged_without_the_secret(
    context: WorkerContext,
    kind: FakeKind,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="app")
    await add_job(context, await add_client(context))
    channel = await add_channel(context, secret=SECRET)
    await add_rule(context, channel, ["missed"])
    kind.crash = True
    at(clock, MISSED_AT)
    await tick(context)
    (row,) = await notifications(db_engine)
    assert (row.status, row.attempts) == ("retrying", 1)
    assert row.error == "The email delivery failed (RuntimeError)."
    assert "channel kind email failed (RuntimeError)" in caplog.text
    assert SECRET not in caplog.text
    assert SECRET not in (await stored_channel(db_engine, channel)).last_error


async def test_one_broken_notification_does_not_stop_the_others(
    context: WorkerContext,
    kind: FakeKind,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A notification whose message cannot be made (a renderer, the
database) fails on its own retry ladder; the ones due after it are still
sent in the same tick."""
    caplog.set_level(logging.DEBUG, logger="app")
    await add_job(context, await add_client(context))
    first = await add_channel(context, "Ops mail")
    await add_rule(context, first, ["missed"])
    second = await add_channel(context, "Service desk")
    await add_rule(context, second, ["missed"])
    at(clock, MISSED_AT)
    await Evaluator(context).run(clock.now())
    # Both are due at the same moment; the lower id is sent first.
    broken_id = min(row.id for row in await notifications(db_engine))
    compose = Dispatcher.compose

    async def breaking(
        self: Dispatcher, db: Any, notification: Notification, *args: Any
    ) -> Message | None:
        if notification.id == broken_id:
            raise RuntimeError(f"the renderer printed {SECRET}")
        return await compose(self, db, notification, *args)

    monkeypatch.setattr(Dispatcher, "compose", breaking)
    outcome = await Dispatcher(context).run(clock.now())
    assert (outcome.sent, outcome.retrying, outcome.left) == (1, 1, 0)
    rows = {row.id: row for row in await notifications(db_engine)}
    broken = rows.pop(broken_id)
    assert (broken.status, broken.attempts) == ("retrying", 1)
    assert broken.error == "The notification could not be sent (RuntimeError)."
    assert [row.status for row in rows.values()] == ["sent"]
    assert len(kind.sent) == 1
    # Broken every time: the ladder ends in failed, the queue is not stuck.
    for wait in RETRY_DELAYS:
        clock.advance(seconds=wait.total_seconds())
        await dispatch_notifications(context, clock.now())
    rows = {row.id: row for row in await notifications(db_engine)}
    assert (rows[broken_id].status, rows[broken_id].attempts) == ("failed", 4)
    assert f"notification {broken_id} could not be sent (RuntimeError)" in caplog.text
    assert SECRET not in caplog.text


async def test_a_failing_channel_gets_one_attempt_per_tick(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    """A relay that fails (or hangs) does not take the tick's budget: the
channel's other notifications wait for the next tick."""
    dental = await add_client(context)
    await add_job(context, dental)
    await add_job(context, dental, "Database dump")
    await add_rule(context, await add_channel(context), ["missed"])
    kind.failures = 100
    at(clock, MISSED_AT)
    await Evaluator(context).run(clock.now())
    outcome = await Dispatcher(context).run(clock.now())
    assert (outcome.retrying, outcome.left, kind.tries) == (1, 1, 1)
    kind.failures = 0
    second = await Dispatcher(context).run(clock.now())
    assert (second.sent, kind.tries) == (1, 2)


async def test_a_flip_the_queue_missed_is_caught_up(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    """The worker stopped after the evaluator's commit and before the
NotificationQueue ran: the next dispatcher tick queues the flip once,
for the channels that existed at the flip."""
    await add_job(context, await add_client(context))
    channel = await add_channel(context)
    await add_rule(context, channel, ["missed"])
    at(clock, MISSED_AT)
    await Evaluator(dataclasses.replace(context, subscribers=())).run(clock.now())
    assert await notifications(db_engine) == []
    clock.advance(minutes=1)
    later = await add_channel(context, "Added after the flip")
    await add_rule(context, later, ["missed"])
    outcome = await Dispatcher(context).run(clock.now())
    assert (outcome.caught_up, outcome.sent) == (1, 1)
    (row,) = await notifications(db_engine)
    assert (row.channel_id, row.event, row.status) == (channel.id, "missed", "sent")
    await tick(context)
    clock.advance(minutes=20)
    await tick(context)
    assert [message.event for message in kind.sent] == ["missed"]
    assert len(await notifications(db_engine)) == 1


async def test_the_catch_up_leaves_old_flips_alone(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    await add_job(context, await add_client(context))
    await add_rule(context, await add_channel(context), ["missed"])
    at(clock, MISSED_AT)
    await Evaluator(dataclasses.replace(context, subscribers=())).run(clock.now())
    clock.advance(minutes=16)
    outcome = await Dispatcher(context).run(clock.now())
    assert outcome.caught_up == 0
    assert await notifications(db_engine) == []


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


async def test_turning_reminders_on_late_reminds_of_no_old_outage(
    context: WorkerContext, kind: FakeKind, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    """A flip older than 24 hours plus REMINDER_WINDOW gets no reminder when
the setting is turned on later."""
    await add_job(context, await add_client(context))
    await add_rule(context, await add_channel(context), ["missed"])
    at(clock, MISSED_AT)
    await tick(context)
    at(clock, MISSED_AT + timedelta(hours=27))
    await set_reminders(db_engine, True)
    await tick(context)
    clock.advance(minutes=30)
    await tick(context)
    assert [message.event for message in kind.sent] == ["missed"]
    assert [row.event for row in await notifications(db_engine)] == ["missed"]


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


@pytest.fixture
async def http_context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    """The worker with the real channel kinds (default_kinds), private
targets allowed so the kinds deliver to the capture server on 127.0.0.1
and to nothing beyond it."""
    built = build_context(load_settings(allow_private_targets=True), clock)
    yield built
    await built.engine.dispose()


async def add_http_channel(
    context: WorkerContext, kind_name: str, url: str, label: str = "Ops hook"
) -> Channel:
    """A channel of one of the HTTP kinds at url, the url its stored secret
and the stored config the API would keep (url_set and url_host only)."""
    async with context.sessionmaker() as db:
        channel = await ChannelRepository(db, context.policy).create(
            SYSTEM,
            kind=kind_name,
            label=label,
            now=context.clock.now(),
            config={"url_set": True, "url_host": "127.0.0.1"},
            secret_enc=context.secret_box.encrypt(url),
        )
        await db.commit()
    return channel


async def test_the_http_kinds_deliver_one_notification_each(
    http_context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The C9-B dispatcher works unchanged for slack, teams and webhook: one
notification per flip per channel, delivered through the SSRF guard, and
NotificationSent after the commit."""
    caplog.set_level(logging.DEBUG, logger="app")
    recorder = Recorder(db_engine)
    context = dataclasses.replace(
        http_context, subscribers=(*http_context.subscribers, recorder)
    )
    capture = HttpCapture([http_answer(200)])
    await capture.start()
    try:
        dental = await add_client(context)
        job = await add_job(context, dental)
        channels = [
            await add_http_channel(context, name, capture.url, f"Ops {name}")
            for name in ("webhook", "slack", "teams")
        ]
        for channel in channels:
            await add_rule(context, channel, ["missed"])
        at(clock, MISSED_AT)
        await tick(context)
        rows = await notifications(db_engine)
        assert {row.channel_id for row in rows} == {c.id for c in channels}
        assert {(row.status, row.attempts, row.event) for row in rows} == {
            ("sent", 1, "missed")
        }
        # A second tick queues and sends nothing new.
        await tick(context)
        assert len(await notifications(db_engine)) == 3
        # The wire: one request per kind, and the webhook payload is v1.
        assert len(capture.requests) == 3
        payloads = [request.body for request in capture.requests]
        (webhook,) = [body for body in payloads if "schema_version" in body]
        (slack,) = [body for body in payloads if "blocks" in body]
        (teams,) = [body for body in payloads if "@type" in body]
        assert webhook["event"] == "missed" and webhook["schema_version"] == 1
        validate_webhook_payload(webhook)
        assert webhook["product"] == "Checkorca-CE"
        assert webhook["state"] == "missed" and webhook["previous_state"] == "unknown"
        assert webhook["job"] == {
            "id": str(job.id),
            "name": NIGHTLY,
            "kind": "backup",
        }
        assert webhook["client"] == {"id": str(dental.id), "name": DENTAL}
        # The deadline of the occurrence that caused the flip (the new field).
        assert webhook["occurrence"]["scheduled_for"] is not None
        assert webhook["occurrence"]["deadline"] is not None
        assert webhook["url"] == f"http://localhost:8080/jobs/{job.id}"
        assert slack["blocks"][0]["type"] == "header"
        assert teams["@type"] == "MessageCard"
        # NotificationSent once per channel, after the commit.
        assert {event.status for event, _ in recorder.sent} == {"sent"}
        assert {event.channel_id for event, _ in recorder.sent} == {
            c.id for c in channels
        }
        async with context.sessionmaker() as db:
            pending, failed = await NotificationRepository(
                db, context.policy
            ).queue_counts(SYSTEM, failed_since=clock.now())
        assert (pending, failed) == (0, 0)
        stored = await stored_channel(db_engine, channels[0])
        assert stored.last_status == "sent" and stored.last_error is None
        # The stored secret is the ciphertext of the URL, and neither the
        worker's log nor a stored sentence carries its path (D-6).
        assert URL_CANARY not in (stored.secret_enc or "")
        assert URL_CANARY not in caplog.text
    finally:
        await capture.stop()


async def test_a_failing_webhook_retries_on_the_ladder(
    http_context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    """A webhook that answers 500 retries after 1, 5 and 30 minutes like any
channel, and delivers when the receiver mends."""
    context = http_context
    capture = HttpCapture([http_answer(500)])
    await capture.start()
    try:
        await add_job(context, await add_client(context))
        channel = await add_http_channel(context, "webhook", capture.url)
        await add_rule(context, channel, ["missed"])
        at(clock, MISSED_AT)
        await tick(context)
        (row,) = await notifications(db_engine)
        assert (row.status, row.attempts) == ("retrying", 1)
        assert row.error == "The target answered 500."
        assert row.next_attempt_at == MISSED_AT + timedelta(minutes=1)
        # One second early: nothing happens.
        clock.advance(seconds=59)
        await tick(context)
        assert len(capture.requests) == 1
        clock.advance(seconds=1)
        await tick(context)
        (row,) = await notifications(db_engine)
        assert (row.status, row.attempts) == ("retrying", 2)
        assert row.next_attempt_at == clock.now() + timedelta(minutes=5)
        # The receiver mends: the third attempt delivers.
        capture.responses = (http_answer(200),)
        clock.advance(minutes=5)
        await tick(context)
        (row,) = await notifications(db_engine)
        assert (row.status, row.attempts, row.sent_at) == ("sent", 3, clock.now())
        assert len(capture.requests) == 3
        assert (await stored_channel(db_engine, channel)).last_status == "sent"
    finally:
        await capture.stop()
