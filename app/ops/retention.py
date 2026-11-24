"""The retention purge (phase C10): what the settings no longer keep.

The RetentionPurge tick hook (app/worker/loop.py TICK_HOOKS) runs the purge
once a UTC day, after the dispatcher, in one transaction. The RetentionPolicy
seam (app/ext/retention.py) gives the cutoffs from the settings row; a worker
that restarts mid-day simply runs it again (the steps are idempotent).

What goes, in this order (a child before the row it references, like the
client delete map, app/repos/client_delete.py):

1. Notifications: the terminal ones (sent, failed) older than the results
   cutoff, and then every notification of a flip that is about to go, queued
   ones included (a queued notification older than the cutoff means the
   ladder ended without a record; its flip is gone either way).
2. Flips older than the results cutoff. Notifications, flips and occurrences
   follow the results cutoff: they keep no history of their own.
3. Closed occurrences older than the results cutoff, except what the
   evaluator still reads (docs/evaluator.md): every open occurrence stays,
   and per job the newest closed occurrence and the newest
   consecutive_failures_to_alert closed ones that are not maintenance. A row
   the evaluator reads beyond those is always dominated by a newer kept one.
4. Results older than the results cutoff, and the results of the messages
   about to go (their raw_message_id cannot outlive the message).
   occurrence.result_id becomes NULL where a kept occurrence named a purged
   result; the next evaluation decides again.
5. Raw messages whose purge_after has passed (received_at plus the
   retention_raw_days of the day they arrived, docs/ingest.md).
6. Audit events older than the audit cutoff.

The purge never touches jobs, clients or inboxes, and never the backups or
the job results of the MSP's own clients (legal D-5): those live outside this
database. What a backup or a restore brings back is simply purged again by the
next run.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import Select, and_, delete, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import SYSTEM
from app.db.models import (
    AuditEvent,
    Flip,
    Job,
    JobResult,
    Notification,
    Occurrence,
    RawMessage,
)
from app.evaluator.model import CLOSED_STATES
from app.ext.retention import Retention, RetainBySettings, RetentionPolicy
from app.repos.settings import SettingsRepository

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

# Notifications that no longer wait for a delivery.
FINAL_NOTIFICATIONS: Final = ("sent", "failed")

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PurgeReport:
    """The rows one purge deleted, for the log and the tests (purge adds to
    it step by step)."""

    notifications: int = 0
    flips: int = 0
    occurrences: int = 0
    results: int = 0
    raw_messages: int = 0
    audit_events: int = 0

    @property
    def total(self) -> int:
        return (
            self.notifications
            + self.flips
            + self.occurrences
            + self.results
            + self.raw_messages
            + self.audit_events
        )


def _kept_occurrences() -> Select[tuple[uuid.UUID, datetime]]:
    """The (job_id, scheduled_for) of the closed occurrences the job state
    still reads: per job the newest closed one, and the newest
    consecutive_failures_to_alert closed ones that are not maintenance
    (machine.earlier_view). Ranked over every closed occurrence of the job:
    a row this drops is always older than a kept one the evaluator reads
    instead."""
    newest = func.row_number().over(
        partition_by=Occurrence.job_id,
        order_by=Occurrence.scheduled_for.desc(),
    ).label("newest")
    counted = func.row_number().over(
        partition_by=(Occurrence.job_id, Occurrence.state != "maintenance"),
        order_by=Occurrence.scheduled_for.desc(),
    ).label("counted")
    ranked = (
        select(
            Occurrence.job_id,
            Occurrence.scheduled_for,
            Occurrence.state,
            newest,
            counted,
        )
        .where(Occurrence.state.in_(CLOSED_STATES))
        .cte("ranked_occurrences")
    )
    return (
        select(ranked.c.job_id, ranked.c.scheduled_for)
        .join(Job, Job.id == ranked.c.job_id)
        .where(
            or_(
                ranked.c.newest == 1,
                and_(
                    ranked.c.state != "maintenance",
                    ranked.c.counted <= Job.consecutive_failures_to_alert,
                ),
            )
        )
    )


async def purge(db: AsyncSession, plan: Retention) -> PurgeReport:
    """Run every step in the caller's transaction (the caller commits)."""
    report = PurgeReport()
    raw_before = plan.raw_before
    results_before = plan.results_before
    audit_before = plan.audit_before
    if raw_before is None and results_before is None and audit_before is None:
        return report
    if results_before is not None:
        gone = await db.execute(
            delete(Notification).where(
                Notification.status.in_(FINAL_NOTIFICATIONS),
                Notification.created_at < results_before,
            )
        )
        report.notifications += gone.rowcount or 0
        old_flips = select(Flip.id).where(Flip.at < results_before)
        gone = await db.execute(
            delete(Notification).where(Notification.flip_id.in_(old_flips))
        )
        report.notifications += gone.rowcount or 0
        gone = await db.execute(delete(Flip).where(Flip.at < results_before))
        report.flips += gone.rowcount or 0
        gone = await db.execute(
            delete(Occurrence)
            .where(
                Occurrence.state.in_(CLOSED_STATES),
                Occurrence.scheduled_for < results_before,
                ~tuple_(Occurrence.job_id, Occurrence.scheduled_for).in_(
                    _kept_occurrences()
                ),
            )
        )
        report.occurrences += gone.rowcount or 0
    conditions = []
    if results_before is not None:
        conditions.append(JobResult.received_at < results_before)
    if raw_before is not None:
        conditions.append(
            JobResult.raw_message_id.in_(
                select(RawMessage.id).where(RawMessage.purge_after < raw_before)
            )
        )
    if conditions:
        gone = await db.execute(delete(JobResult).where(or_(*conditions)))
        report.results += gone.rowcount or 0
    if raw_before is not None:
        gone = await db.execute(
            delete(RawMessage).where(RawMessage.purge_after < raw_before)
        )
        report.raw_messages += gone.rowcount or 0
    if audit_before is not None:
        gone = await db.execute(delete(AuditEvent).where(AuditEvent.at < audit_before))
        report.audit_events += gone.rowcount or 0
    return report


class RetentionPurge:
    """The tick hook: purge once per UTC day, on the retention policy."""

    def __init__(self, policy: RetentionPolicy | None = None) -> None:
        self.policy = policy or RetainBySettings()
        self.last_day: date | None = None

    async def __call__(self, context: "WorkerContext", now: datetime) -> None:
        day = now.date()
        if self.last_day == day:
            return
        async with context.sessionmaker() as db:
            settings = SettingsRepository(db, context.policy, context.secret_box)
            row = await settings.get(SYSTEM)
            report = await purge(db, self.policy.plan(row, now))
            await db.commit()
        # Only a run that committed leaves its mark: a failed purge tries
        # again on the next tick, not tomorrow.
        self.last_day = day
        if report.total:
            logger.info(
                "retention purge: %d notifications, %d flips, %d occurrences, "
                "%d results, %d messages, %d audit events",
                report.notifications,
                report.flips,
                report.occurrences,
                report.results,
                report.raw_messages,
                report.audit_events,
            )
