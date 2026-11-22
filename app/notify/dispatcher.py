"""The notification dispatcher (phase C9-B): queue on flips, send on ticks.

Both parts run in the worker; docs/notifications.md is the contract.

1. NotificationQueue is an EventSubscriber (app/ext/events.py). For each
   FlipCreated it turns the change into an event (event_of: failing, missed,
   warning or recovered; other changes notify nobody), reads the enabled
   channels whose rules cover the job for that event, lets the
   EscalationPolicy plan them and inserts one queued notification per
   channel. The notification table is unique per flip, channel and event, so
   a flip delivered twice, or a channel with two matching rules, gives one
   notification. The demo seed replays its history without subscribers, so it
   queues nothing.
2. dispatch_notifications is a tick hook (app/worker/loop.py TICK_HOOKS),
   after the evaluator. On every tick it
   0. catches up: a flip of the last 15 minutes (CATCH_UP_WINDOW) that
      notifies but has no notification yet is queued as the subscriber would
      have, for the channels and rules that existed at the flip. That covers
      a worker stopped between the evaluator's commit and the queue's, and a
      subscriber that failed or timed out. The flips the demo seed replayed
      (up to its audit event seed.demo) are left alone;
   a. queues the digest of the local day once its digest time has passed
      (settings.digest_time_local in settings.digest_timezone) for every
      enabled channel with a digest rule that has none of that day yet: once
      per channel and local day, also on the days the clocks change;
   b. with settings.reminder_24h, queues one reminder per channel for a flip
      to failing or missed whose job has not changed state and is not
      acknowledged 24 hours later;
   c. sends what is due, each notification in its own transaction, locked
      with its channel and SKIP LOCKED. A failed attempt is tried again after
      1, 5 and 30 minutes (RETRY_DELAYS, on the injected Clock); after the
      fourth attempt the notification is failed. An unexpected error counts
      as a failed attempt of that notification only; a channel with an
      attempt to retry gets no more attempts in this tick. After the commit,
      NotificationSent goes to the subscribers for a notification about a
      flip that was sent or failed for good.

A crash after the relay accepted a message and before the commit sends it
again on the next tick: delivery is at least once.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.access import SYSTEM, AccessPolicy
from app.clock import Clock
from app.db.models import Channel, Notification
from app.ext.events import Event, FlipCreated, NotificationSent, deliver
from app.ext.notifications import AllAtOnce, EscalationPolicy, FlipFacts, Message
from app.notify.delivery import outbound_of, send_message
from app.notify.digest import build_digest
from app.notify.messages import digest_message, flip_message
from app.notify.windows import local_date, local_moment
from app.repos.notifications import ChannelRepository, NotificationRepository
from app.repos.settings import SettingsRepository
from app.security.crypto import SecretBoxError

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

# Job states that are a problem; a flip into one is its own event.
PROBLEM_STATES: Final = frozenset({"failing", "missed", "warning"})
# The waits after the first, second and third failed attempt; the fourth
# failure is final.
RETRY_DELAYS: Final = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
)
REMINDER_AFTER: Final = timedelta(hours=24)
# Flips this much older than REMINDER_AFTER are not reminded any more, so
# turning the setting on does not remind of old outages.
REMINDER_WINDOW: Final = timedelta(hours=2)
# Notifications sent in one tick at most, and no new one after BUDGET_SECONDS
# of the tick (monotonic clock); the rest wait for the next tick.
MAX_SENDS_PER_TICK: Final = 200
MAX_REMINDERS_PER_TICK: Final = 500
BUDGET_SECONDS: Final = 30.0
# How far back every tick looks for flips the NotificationQueue missed, and
# how many of them it queues at most.
CATCH_UP_WINDOW: Final = timedelta(minutes=15)
MAX_CATCH_UP_PER_TICK: Final = 200

logger = logging.getLogger(__name__)


def event_of(from_state: str, to_state: str) -> str | None:
    """The notification event of a change of job state, or None."""
    if to_state in PROBLEM_STATES:
        return to_state
    if to_state == "ok" and from_state in PROBLEM_STATES:
        return "recovered"
    return None


def retry_delay(attempts: int) -> timedelta | None:
    """The wait after attempts failed attempts; None when that was the last."""
    if attempts <= len(RETRY_DELAYS):
        return RETRY_DELAYS[attempts - 1]
    return None


def due_digest_day(now: datetime, zone: ZoneInfo, digest_time: time) -> date | None:
    """The local day whose digest is due at now: today, once today's digest
    time has passed (a time the clocks skip counts with the offset before
    the change, a repeated one at its first occurrence)."""
    today = local_date(now, zone)
    if now >= local_moment(today, digest_time, zone):
        return today
    return None


class NotificationQueue:
    """The EventSubscriber that queues notifications for flips."""

    name = "notifications"

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        policy: AccessPolicy,
        clock: Clock,
        escalation: EscalationPolicy | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.policy = policy
        self.clock = clock
        self.escalation = escalation or AllAtOnce()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, FlipCreated):
            return
        kind = event_of(event.from_state, event.to_state)
        if kind is None:
            return
        await self.queue(event, kind)

    async def queue(
        self, flip: FlipCreated, kind: str, *, existing_at: datetime | None = None
    ) -> int:
        """Queue the flip's notifications; the number queued. With
        existing_at, only channels and rules that existed then count."""
        async with self.sessionmaker() as db:
            repository = NotificationRepository(db, self.policy)
            if not await repository.hold_job(SYSTEM, flip.job_id):
                return 0
            channels = await repository.matching_channels(
                SYSTEM,
                client_id=flip.client_id,
                job_id=flip.job_id,
                event=kind,
                existing_at=existing_at,
            )
            if not channels:
                return 0
            allowed = set(channels)
            now = self.clock.now()
            rows = [
                {
                    "channel_id": step.channel_id,
                    "flip_id": flip.flip_id,
                    "event": kind,
                    "created_at": now,
                    "next_attempt_at": now + max(step.delay, timedelta(0)),
                }
                for step in self.escalation.plan(flip, kind, channels)
                if step.channel_id in allowed
            ]
            try:
                queued = await repository.queue(SYSTEM, rows)
                await db.commit()
            except IntegrityError:
                # The flip went with its client (deleted meanwhile).
                logger.warning("flip %s is gone; nothing queued", flip.flip_id)
                return 0
        return queued


def queue_of(context: "WorkerContext") -> NotificationQueue | None:
    """The context's NotificationQueue; None without it (the demo replay)."""
    for subscriber in context.subscribers:
        if isinstance(subscriber, NotificationQueue):
            return subscriber
    return None


@dataclass(frozen=True, slots=True)
class DigestSettings:
    """The settings the dispatcher reads on every tick."""

    digest_time: time
    timezone: str
    reminder_24h: bool


@dataclass
class DispatchReport:
    """What one tick did, for the log and the tests."""

    caught_up: int = 0
    digests: int = 0
    reminders: int = 0
    sent: int = 0
    retrying: int = 0
    failed: int = 0
    left: int = 0


@dataclass(frozen=True, slots=True)
class Outcome:
    """The result of one attempt: error is None when it was delivered; final
    means no retry (sent, or a failure retrying cannot mend)."""

    error: str | None
    final: bool = False


class Dispatcher:
    """One tick of the dispatcher (see the module text)."""

    def __init__(
        self,
        context: "WorkerContext",
        *,
        max_sends: int = MAX_SENDS_PER_TICK,
        budget_seconds: float = BUDGET_SECONDS,
    ) -> None:
        self.context = context
        self.max_sends = max_sends
        self.budget_seconds = budget_seconds

    async def run(self, now: datetime) -> DispatchReport:
        report = DispatchReport()
        settings = await self._settings()
        report.caught_up = await self.catch_up(now)
        report.digests = await self.queue_digest(settings, now)
        if settings.reminder_24h:
            report.reminders = await self.queue_reminders(now)
        await self.send_due(settings, now, report)
        return report

    async def _settings(self) -> DigestSettings:
        context = self.context
        async with context.sessionmaker() as db:
            stored = SettingsRepository(db, context.policy, context.secret_box)
            row = await stored.get(SYSTEM)
        timezone = row.digest_timezone
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            # The settings route stores IANA names only; never stop sending.
            logger.warning("digest timezone is not known; using UTC")
            timezone = "UTC"
        return DigestSettings(
            digest_time=row.digest_time_local,
            timezone=timezone,
            reminder_24h=row.reminder_24h,
        )

    async def queue_digest(self, settings: DigestSettings, now: datetime) -> int:
        """Queue today's digest for the channels that have none yet, once the
        digest time has passed."""
        zone = ZoneInfo(settings.timezone)
        day = due_digest_day(now, zone, settings.digest_time)
        if day is None:
            return 0
        async with self.context.sessionmaker() as db:
            repository = NotificationRepository(db, self.context.policy)
            channels = await repository.digest_channels(SYSTEM, day=day)
            rows = [
                {
                    "channel_id": channel_id,
                    "event": "digest",
                    "digest_day": day,
                    "created_at": now,
                    "next_attempt_at": now,
                }
                for channel_id in channels
            ]
            queued = await repository.queue(SYSTEM, rows)
            await db.commit()
        return queued

    async def queue_reminders(self, now: datetime) -> int:
        """Queue the 24-hour reminders that are due."""
        end = now - REMINDER_AFTER
        async with self.context.sessionmaker() as db:
            repository = NotificationRepository(db, self.context.policy)
            found = await repository.reminders(
                SYSTEM,
                start=end - REMINDER_WINDOW,
                end=end,
                limit=MAX_REMINDERS_PER_TICK,
            )
            rows = [
                {
                    "channel_id": item.channel_id,
                    "flip_id": item.flip_id,
                    "event": "reminder",
                    "created_at": now,
                    "next_attempt_at": now,
                }
                for item in found
            ]
            queued = await repository.queue(SYSTEM, rows)
            await db.commit()
        return queued

    async def catch_up(self, now: datetime) -> int:
        """Queue what the NotificationQueue did not: the flips of the last
        CATCH_UP_WINDOW without their notifications, because the worker
        stopped between the evaluator's commit and the queue's, or the
        subscriber failed or timed out. The unique key keeps a flip that is
        queued meanwhile at one notification. Without the subscriber (the
        demo replay's context) nothing is queued, and the flips the demo seed
        replayed are left alone."""
        queue = queue_of(self.context)
        if queue is None:
            return 0
        after = now - CATCH_UP_WINDOW
        async with self.context.sessionmaker() as db:
            repository = NotificationRepository(db, self.context.policy)
            seeded = await repository.demo_seeded_at(SYSTEM, since=after)
            if seeded is not None:
                after = max(after, seeded)
            flips = await repository.unqueued_flips(
                SYSTEM,
                after=after,
                until=now,
                problem_states=PROBLEM_STATES,
                limit=MAX_CATCH_UP_PER_TICK,
            )
        queued = 0
        for flip in flips:
            kind = event_of(flip.from_state, flip.to_state)
            if kind is None:
                continue
            event = FlipCreated(
                flip_id=flip.id,
                job_id=flip.job_id,
                client_id=flip.client_id,
                from_state=flip.from_state,
                to_state=flip.to_state,
                reason=flip.reason,
                at=flip.at,
            )
            queued += await queue.queue(event, kind, existing_at=flip.at)
        if queued:
            logger.warning("notifications: %d caught up for earlier flips", queued)
        return queued

    async def send_due(
        self, settings: DigestSettings, now: datetime, report: DispatchReport
    ) -> None:
        clock = self.context.clock
        # The evaluator of this tick queued its flips a moment after now:
        # they are sent in this tick too.
        ready = max(now, clock.now())
        async with self.context.sessionmaker() as db:
            repository = NotificationRepository(db, self.context.policy)
            due = await repository.due(SYSTEM, now=ready, limit=self.max_sends)
        started = clock.monotonic()
        # A channel with an attempt to retry in this tick gets no more
        # attempts in it, so a hanging relay does not use up the budget of
        # the others.
        broken: set[uuid.UUID] = set()
        for index, (notification_id, channel_id) in enumerate(due):
            if index and clock.monotonic() - started >= self.budget_seconds:
                report.left += len(due) - index
                break
            if channel_id in broken:
                report.left += 1
                continue
            status = await self.send_one(notification_id, settings, ready)
            if status == "sent":
                report.sent += 1
            elif status == "retrying":
                report.retrying += 1
                broken.add(channel_id)
            elif status == "failed":
                report.failed += 1

    async def send_one(
        self, notification_id: uuid.UUID, settings: DigestSettings, now: datetime
    ) -> str | None:
        """One attempt at one notification; its new status, or None when it
        was not due any more or another worker holds it.

        An unexpected error (composing the message, the database) never
        stops the tick: it counts as a failed attempt of this notification
        only, written in a new transaction, so a notification that fails the
        same way every time ends failed on the retry ladder and the ones
        after it are still sent."""
        try:
            return await self._send_one(notification_id, settings, now, None)
        except Exception as error:
            name = type(error).__name__
            # The class only: the text may hold anything.
            logger.error(
                "notification %s could not be sent (%s)", notification_id, name
            )
            outcome = Outcome(f"The notification could not be sent ({name}).")
        try:
            return await self._send_one(notification_id, settings, now, outcome)
        except Exception as error:
            logger.error(
                "notification %s: the failed attempt was not stored (%s)",
                notification_id,
                type(error).__name__,
            )
            return None

    async def _send_one(
        self,
        notification_id: uuid.UUID,
        settings: DigestSettings,
        now: datetime,
        failure: Outcome | None,
    ) -> str | None:
        """send_one in one transaction; with failure, that outcome is stored
        without an attempt to send."""
        context = self.context
        events: list[Event] = []
        async with context.sessionmaker() as db:
            repository = NotificationRepository(db, context.policy)
            claimed = await repository.claim(SYSTEM, notification_id, now=now)
            if claimed is None:
                return None
            notification, channel = claimed
            if failure is None:
                outcome = await self.attempt(db, notification, channel, settings, now)
            else:
                outcome = failure
            at = context.clock.now()
            attempts = notification.attempts + 1
            wait = None if outcome.final else retry_delay(attempts)
            if outcome.error is None:
                status = "sent"
            else:
                status = "failed" if wait is None else "retrying"
            await repository.finish(
                SYSTEM,
                notification,
                status=status,
                attempts=attempts,
                error=outcome.error,
                last_attempt_at=at,
                next_attempt_at=None if wait is None else at + wait,
                sent_at=at if status == "sent" else None,
            )
            await ChannelRepository(db, context.policy).record_delivery(
                SYSTEM,
                channel.id,
                status="sent" if status == "sent" else "failed",
                at=at,
                error=outcome.error,
            )
            await db.commit()
            if status != "retrying" and notification.flip_id is not None:
                events.append(
                    NotificationSent(
                        notification_id=notification.id,
                        flip_id=notification.flip_id,
                        channel_id=channel.id,
                        status=status,
                    )
                )
        if status == "failed":
            logger.warning(
                "notification %s to channel %s failed after %d attempts",
                notification_id,
                channel.id,
                attempts,
            )
        await deliver(context.subscribers, events)
        return status

    async def attempt(
        self,
        db: AsyncSession,
        notification: Notification,
        channel: Channel,
        settings: DigestSettings,
        now: datetime,
    ) -> Outcome:
        """Send the notification through its channel's kind."""
        context = self.context
        if not channel.enabled:
            return Outcome("The channel is disabled.", final=True)
        kind = context.kinds.get(channel.kind)
        if kind is None:
            return Outcome(
                f"The channel kind {channel.kind} is not available.", final=True
            )
        secret = None
        if channel.secret_enc is not None:
            try:
                secret = context.secret_box.decrypt(channel.secret_enc)
            except SecretBoxError:
                return Outcome(
                    "The stored secret cannot be decrypted with FERNET_KEY; "
                    "set it again.",
                    final=True,
                )
        message = await self.compose(db, notification, settings, now)
        if message is None:
            return Outcome("The flip of this notification is gone.", final=True)
        outbound = outbound_of(context.settings)
        error = await send_message(kind, channel.config, secret, message, outbound)
        return Outcome(error, final=error is None)

    async def compose(
        self,
        db: AsyncSession,
        notification: Notification,
        settings: DigestSettings,
        now: datetime,
    ) -> Message | None:
        """The message of the notification; None when its flip is gone."""
        context = self.context
        zone = ZoneInfo(settings.timezone)
        base = context.settings.base_url
        if notification.digest_day is not None:
            digest = await build_digest(
                db,
                context.policy,
                SYSTEM,
                day=notification.digest_day,
                timezone=settings.timezone,
                digest_time=settings.digest_time,
                now=now,
                url=f"{base}/",
            )
            report = context.report_renderer.render(digest)
            return digest_message(
                report, f"{base}/", notification.digest_day, digest
            )
        if notification.flip_id is None:
            return None
        repository = NotificationRepository(db, context.policy)
        found = await repository.flip(SYSTEM, notification.flip_id)
        if found is None:
            return None
        flip = found.flip
        facts = FlipFacts(
            flip_id=flip.id,
            job_id=flip.job_id,
            job=found.job_name,
            job_kind=found.job_kind,
            client_id=flip.client_id,
            client=found.client_name,
            from_state=flip.from_state,
            to_state=flip.to_state,
            reason=flip.reason,
            at=flip.at,
            scheduled_for=flip.scheduled_for,
            deadline=found.deadline,
            url=f"{base}/jobs/{flip.job_id}",
        )
        return flip_message(notification.event, facts, zone)


async def dispatch_notifications(context: "WorkerContext", now: datetime) -> None:
    """The tick hook (app/worker/loop.py TICK_HOOKS)."""
    report = await Dispatcher(context).run(now)
    if any(vars(report).values()):
        logger.info(
            "notifications: %d digests and %d reminders queued; %d sent, "
            "%d to retry, %d failed, %d left for the next tick",
            report.digests,
            report.reminders,
            report.sent,
            report.retrying,
            report.failed,
            report.left,
        )
