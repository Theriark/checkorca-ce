"""The worker loop: one worker ticks, every other one waits.

A worker first takes the advisory lock (app/worker/lock.py). While it holds
it, the worker starts the receivers, then ticks every 60 seconds on the
injected Clock: it writes the heartbeat and runs each tick hook. A second
worker waits for the lock without ticking and takes over when the first one
stops or dies.

Later phases register here, so the loop itself does not change:
- TICK_HOOKS: work done on every tick (C5 parse pending messages, C7 evaluate,
  C9 notify, C10 retention and the outbound heartbeat). A hook gets the
  WorkerContext and the tick's time; its error is logged and never stops the
  tick or the hooks after it.
- RECEIVERS: long-running channels started while the lock is held and stopped
  when it is given up (C4-I: the SMTP listener on 2525 and the IMAP poller).
"""

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.access import SYSTEM, AccessPolicy, AllowAllPolicy
from app.clock import Clock, SystemClock
from app.db.engine import make_engine
from app.db.locks import WORKER_LOCK
from app.evaluator.tick import evaluate_jobs
from app.ext.events import EventSubscriber
from app.ext.parsers import ParserPackSource, TablePackSource
from app.ext.suppression import NoSuppression, SuppressionProvider
from app.ingest.imap import ImapPoller
from app.ingest.smtp import SmtpReceiver
from app.repos.heartbeat import HeartbeatRepository
from app.security.crypto import SecretBox
from app.settings import Settings
from app.worker.lock import WorkerLock, wait_for_stop
from app.worker.parse import parse_messages

TICK_SECONDS: Final = 60.0
# How often a waiting worker tries the lock again.
LOCK_RETRY_SECONDS: Final = 15.0
HOLDER_LENGTH: Final = 200

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerContext:
    """What hooks and receivers share: settings, database, clock, policy, the
    parser packs, the maintenance windows and the event subscribers."""

    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    clock: Clock
    policy: AccessPolicy
    secret_box: SecretBox
    pack_source: ParserPackSource = field(default_factory=TablePackSource)
    suppression: SuppressionProvider = field(default_factory=NoSuppression)
    # Get FlipCreated and OccurrenceChanged after each evaluator commit.
    subscribers: tuple[EventSubscriber, ...] = ()


type TickHook = Callable[[WorkerContext, datetime], Awaitable[None]]


class Receiver(Protocol):
    """A channel that runs while the worker holds the lock (SMTP, IMAP)."""

    name: str

    async def start(self, context: WorkerContext) -> None:
        """Start serving and return; errors here are logged, the worker goes on."""
        ...

    async def stop(self) -> None:
        """Stop serving and release every resource."""
        ...


type ReceiverFactory = Callable[[WorkerContext], Receiver]

# Phases append their hooks and receivers here. C5-B: parse pending messages;
# C7-B: evaluate the jobs (after the parse, so new results count at once).
TICK_HOOKS: tuple[TickHook, ...] = (parse_messages, evaluate_jobs)
# C4-I: the SMTP listener on SMTP_PORT and the IMAP poller.
RECEIVERS: tuple[ReceiverFactory, ...] = (SmtpReceiver, ImapPoller)


def default_holder() -> str:
    """Host name and process id: which container ticks (System status)."""
    return f"{socket.gethostname()} pid {os.getpid()}"[:HOLDER_LENGTH]


def build_context(settings: Settings, clock: Clock | None = None) -> WorkerContext:
    engine = make_engine(settings.database_url.get_secret_value())
    return WorkerContext(
        settings=settings,
        engine=engine,
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
        clock=clock or SystemClock(),
        policy=AllowAllPolicy(),
        secret_box=SecretBox(settings.fernet_key.get_secret_value()),
    )


class Worker:
    """The loop of one worker process."""

    def __init__(
        self,
        context: WorkerContext,
        *,
        hooks: Sequence[TickHook] | None = None,
        receivers: Sequence[ReceiverFactory] | None = None,
        tick_seconds: float = TICK_SECONDS,
        lock_retry_seconds: float = LOCK_RETRY_SECONDS,
        lock_key: int = WORKER_LOCK,
        holder: str | None = None,
    ) -> None:
        self.context = context
        self.hooks = tuple(TICK_HOOKS if hooks is None else hooks)
        self.receivers = tuple(RECEIVERS if receivers is None else receivers)
        self.tick_seconds = tick_seconds
        self.lock_retry_seconds = lock_retry_seconds
        self.lock_key = lock_key
        self.holder = (holder or default_holder())[:HOLDER_LENGTH]
        self.ticks = 0
        self.holds_lock = False
        self.started_at: datetime | None = None

    async def run(self, stop: asyncio.Event) -> None:
        """Wait for the lock, tick while holding it, until stop is set."""
        logger.info("worker started")
        while not stop.is_set():
            lock = WorkerLock(self.context.engine, self.lock_key)
            try:
                if not await lock.acquire(stop, self.lock_retry_seconds):
                    break
                self.holds_lock = True
                self.started_at = self.context.clock.now()
                logger.info("worker holds the lock")
                await self._hold(stop, lock)
            finally:
                self.holds_lock = False
                await lock.release()
        logger.info("worker stopped")

    async def _hold(self, stop: asyncio.Event, lock: WorkerLock) -> None:
        """Run the receivers and tick until stop is set or the lock is lost."""
        running = await self._start_receivers()
        try:
            clock = self.context.clock
            next_at = clock.monotonic()
            while not stop.is_set():
                if not await lock.still_held():
                    return
                await self.tick()
                next_at += self.tick_seconds
                now = clock.monotonic()
                # After a slow tick the next one starts at once; no catching up.
                next_at = max(next_at, now)
                if not await self._wait_holding(stop, lock, next_at - now):
                    return
        finally:
            await self._stop_receivers(running)

    async def _wait_holding(
        self, stop: asyncio.Event, lock: WorkerLock, seconds: float
    ) -> bool:
        """Wait for the next tick, checking the lock every lock_retry_seconds;
        False when stop is set or the lock is lost.

        A waiting worker takes a freed lock within lock_retry_seconds; the
        holder notices the loss about as soon, so the receivers of two workers
        overlap for seconds, not for a whole tick.
        """
        remaining = seconds
        while True:
            step = min(remaining, self.lock_retry_seconds)
            if await wait_for_stop(stop, step):
                return False
            remaining -= step
            if not await lock.still_held():
                return False
            if remaining <= 0:
                return True

    async def tick(self) -> None:
        """Write the heartbeat, then run every hook once."""
        now = self.context.clock.now()
        try:
            async with self.context.sessionmaker() as db:
                await HeartbeatRepository(db, self.context.policy).beat(
                    SYSTEM,
                    at=now,
                    holder=self.holder,
                    started_at=self.started_at or now,
                )
                await db.commit()
        except Exception as error:
            logger.error("worker heartbeat failed", exc_info=error)
        for hook in self.hooks:
            try:
                await hook(self.context, now)
            except Exception as error:
                name = getattr(hook, "__qualname__", type(hook).__name__)
                logger.error("tick hook %s failed", name, exc_info=error)
        self.ticks += 1

    async def _start_receivers(self) -> list[Receiver]:
        running: list[Receiver] = []
        for factory in self.receivers:
            try:
                receiver = factory(self.context)
                await receiver.start(self.context)
            except Exception as error:
                logger.error("receiver failed to start", exc_info=error)
                continue
            logger.info("receiver %s started", receiver.name)
            running.append(receiver)
        return running

    async def _stop_receivers(self, running: list[Receiver]) -> None:
        for receiver in reversed(running):
            try:
                await receiver.stop()
            except Exception as error:
                logger.error(
                    "receiver %s failed to stop", receiver.name, exc_info=error
                )


async def run_worker(settings: Settings, stop: asyncio.Event) -> None:
    """The worker role: run until stop is set, then close the database pool."""
    context = build_context(settings)
    try:
        await Worker(context).run(stop)
    finally:
        await context.engine.dispose()
