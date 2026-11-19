"""system/status: the worker heartbeat and lock holder, inbox activity and the
parse queue. Phase C8-B adds the notification queues and the evaluator lag.

Admins and technicians, or an API token of scope read.
"""

from typing import cast

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
from app.repos.heartbeat import HeartbeatRepository
from app.repos.inboxes import InboxRepository
from app.repos.messages import RawMessageRepository
from app.worker.heartbeat import heartbeat_view

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(
    principal: ReaderDep, services: ServicesDep, db: DbDep
) -> SystemStatus:
    """A heartbeat older than 3 minutes (or none) is stale: the web app shows a
    red banner and /readyz answers 503."""
    row = await HeartbeatRepository(db, services.policy).get(principal)
    heartbeat = heartbeat_view(row, services.clock.now())
    inboxes = await InboxRepository(db, services.policy).activity(
        principal, limit=MAX_LIMIT
    )
    pending = await RawMessageRepository(db, services.policy).pending_count(principal)
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
        queue=QueueStatus(pending_messages=pending),
        version=__version__,
        revision=services.settings.revision or None,
    )
