"""system/status: the worker heartbeat and lock holder, inbox activity, the
parse and notification queues, the evaluator lag, the version and the
extension API level.

Admins and technicians, or an API token of scope read. pending_notifications
counts the queued and retrying notifications, failed_notifications those that
failed for good in the last 24 hours (phase C9).
"""

from datetime import timedelta
from typing import Final, cast

from fastapi import APIRouter

from app import __version__
from app.api.deps import DbDep, ReaderDep, ServicesDep
from app.api.pagination import MAX_LIMIT
from app.api.v1.ingest_schemas import (
    InboxActivity,
    InboxKind,
    QueueStatus,
    SystemStatus,
    WorkerStatus,
)
from app.ext import EXTENSION_API_LEVEL
from app.repos.dashboard import DashboardRepository
from app.repos.heartbeat import HeartbeatRepository
from app.repos.inboxes import InboxRepository
from app.repos.messages import RawMessageRepository
from app.repos.notifications import NotificationRepository
from app.worker.heartbeat import heartbeat_view

router = APIRouter(prefix="/system", tags=["system"])

# failed_notifications counts the failures of this last stretch of time.
FAILED_SPAN: Final = timedelta(hours=24)


@router.get("/status")
async def system_status(
    principal: ReaderDep, services: ServicesDep, db: DbDep
) -> SystemStatus:
    """A heartbeat older than 3 minutes (or none) is stale: the web app shows a
    red banner and /readyz answers 503. evaluator_lag_seconds is how long the
    oldest evaluation the evaluator owes has waited (a deadline it has not
    looked at yet, or a job it never evaluated); 0 when it is up to date."""
    now = services.clock.now()
    row = await HeartbeatRepository(db, services.policy).get(principal)
    heartbeat = heartbeat_view(row, now)
    inboxes = await InboxRepository(db, services.policy).activity(
        principal, limit=MAX_LIMIT
    )
    pending = await RawMessageRepository(db, services.policy).pending_count(principal)
    oldest = await DashboardRepository(db, services.policy).oldest_due(
        principal, now=now
    )
    lag = timedelta(0) if oldest is None else max(now - oldest, timedelta(0))
    waiting, failed = await NotificationRepository(db, services.policy).queue_counts(
        principal, failed_since=now - FAILED_SPAN
    )
    return SystemStatus(
        worker=WorkerStatus(
            heartbeat_at=heartbeat.at,
            age_seconds=heartbeat.age_seconds,
            stale=heartbeat.stale,
            holder=heartbeat.holder,
            started_at=heartbeat.started_at,
        ),
        inboxes=[
            InboxActivity(
                id=inbox.id,
                kind=cast(InboxKind, inbox.kind),
                label=inbox.label,
                last_message_at=inbox.last_message_at,
            )
            for inbox in inboxes
        ],
        queue=QueueStatus(
            pending_messages=pending,
            pending_notifications=waiting,
            failed_notifications=failed,
        ),
        evaluator_lag_seconds=round(lag.total_seconds(), 3),
        version=__version__,
        revision=services.settings.revision or None,
        extension_api_level=EXTENSION_API_LEVEL,
    )
