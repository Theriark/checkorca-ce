"""notifications: the notification history, newest first (phase C9-B).

Admins and technicians, or an API token of scope read. A notification is
about a flip (with its job and client) or is the daily digest of a day; its
status is queued, retrying, sent or failed, and error says why the last
attempt failed (docs/notifications.md).
"""

import uuid
from typing import cast

from fastapi import APIRouter

from app.api.deps import DbDep, ReaderDep, ServicesDep
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.v1.notify_schemas import (
    ChannelKindName,
    NotificationEvent,
    NotificationOut,
    NotificationPage,
    NotificationStatus,
)
from app.repos.notifications import NotificationRepository, NotificationRow

router = APIRouter(prefix="/notifications", tags=["notifications"])


def notification_out(row: NotificationRow) -> NotificationOut:
    item = row.notification
    return NotificationOut(
        id=item.id,
        channel_id=item.channel_id,
        channel_label=row.channel_label,
        channel_kind=cast(ChannelKindName, row.channel_kind),
        event=cast(NotificationEvent, item.event),
        status=cast(NotificationStatus, item.status),
        attempts=item.attempts,
        error=item.error,
        flip_id=item.flip_id,
        job_id=row.job_id,
        job_name=row.job_name,
        client_id=row.client_id,
        client_name=row.client_name,
        digest_day=item.digest_day,
        created_at=item.created_at,
        last_attempt_at=item.last_attempt_at,
        next_attempt_at=item.next_attempt_at,
        sent_at=item.sent_at,
    )


@router.get("")
async def list_notifications(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    status: NotificationStatus | None = None,
    channel_id: uuid.UUID | None = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> NotificationPage:
    """Notifications, newest first; status and channel_id narrow the list."""
    after = None if cursor is None else decode_time_cursor(cursor, "created_at")
    notifications = NotificationRepository(db, services.policy)
    found = await notifications.page(
        principal,
        status=status,
        channel_id=channel_id,
        after=after,
        limit=limit + 1,
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1].notification
        next_cursor = encode_time_cursor("created_at", last.created_at, last.id)
    return NotificationPage(
        items=[notification_out(row) for row in items], next_cursor=next_cursor
    )
