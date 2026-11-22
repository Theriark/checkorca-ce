"""Notification channels, their rules and the notifications (phase C9).

The repositories store what they are given: the API encrypts a channel's
secret with the SecretBox before it is stored, and only the dispatcher of the
worker decrypts it to send. Queueing is idempotent: an insert that meets one
of the notification table's unique keys (flip, channel and event; channel and
digest day) adds nothing.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final

from sqlalchemy import and_, delete, exists, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from app.access import Principal
from app.db.models import (
    Channel,
    ChannelRule,
    Client,
    Flip,
    Job,
    Notification,
)
from app.repos.base import Repository, guarded

# The fields update() may change; id, kind and created_at never change.
_CHANNEL_UPDATABLE: Final = frozenset({"label", "enabled", "config", "secret_enc"})
_RULE_UPDATABLE: Final = frozenset({"scope", "scope_id", "events"})
OPEN_STATUSES: Final = ("queued", "retrying")
# The columns a queued notification starts with.
_QUEUED: Final[dict[str, Any]] = {
    "status": "queued",
    "attempts": 0,
    "flip_id": None,
    "digest_day": None,
}
# Events whose notification can get a 24-hour reminder.
REMINDED_EVENTS: Final = ("failing", "missed")


class ChannelRepository(Repository):
    resource = "channel"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[Channel]:
        """Channels, oldest first, after the (created_at, id) cursor."""
        query = select(Channel).order_by(Channel.created_at, Channel.id).limit(limit)
        if after is not None:
            query = query.where(tuple_(Channel.created_at, Channel.id) > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, channel_id: uuid.UUID, *, for_update: bool = False
    ) -> Channel | None:
        query = select(Channel).where(Channel.id == channel_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        kind: str,
        label: str,
        now: datetime,
        **fields: Any,
    ) -> Channel:
        unknown = set(fields) - _CHANNEL_UPDATABLE
        if unknown:
            raise ValueError(f"cannot set {sorted(unknown)}")
        channel = Channel(
            kind=kind, label=label, created_at=now, updated_at=now, **fields
        )
        self.db.add(channel)
        await self.db.flush()
        return channel

    @guarded("update")
    async def update(
        self, principal: Principal, channel: Channel, *, now: datetime, **changes: Any
    ) -> None:
        unknown = set(changes) - _CHANNEL_UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for field, value in changes.items():
            setattr(channel, field, value)
        channel.updated_at = now
        await self.db.flush()

    @guarded("delete")
    async def delete(self, principal: Principal, channel: Channel) -> None:
        """Delete the channel with its rules and notifications."""
        await self.db.execute(delete(Channel).where(Channel.id == channel.id))

    @guarded("update")
    async def record_delivery(
        self,
        principal: Principal,
        channel_id: uuid.UUID,
        *,
        status: str,
        at: datetime,
        error: str | None,
    ) -> None:
        """The outcome of the newest delivery (sent or failed)."""
        await self.db.execute(
            update(Channel)
            .where(Channel.id == channel_id)
            .values(last_status=status, last_status_at=at, last_error=error)
        )


class ChannelRuleRepository(Repository):
    resource = "channel_rule"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        channel_id: uuid.UUID | None,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[ChannelRule]:
        """Rules, oldest first, after the (created_at, id) cursor."""
        query = (
            select(ChannelRule)
            .order_by(ChannelRule.created_at, ChannelRule.id)
            .limit(limit)
        )
        if channel_id is not None:
            query = query.where(ChannelRule.channel_id == channel_id)
        if after is not None:
            query = query.where(tuple_(ChannelRule.created_at, ChannelRule.id) > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, rule_id: uuid.UUID, *, for_update: bool = False
    ) -> ChannelRule | None:
        query = select(ChannelRule).where(ChannelRule.id == rule_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def scope_names(
        self, principal: Principal, rules: Sequence[ChannelRule]
    ) -> dict[uuid.UUID, str]:
        """Client and job names of the rules' scopes: "Client" for a client,
        "Client / Job" for a job (two queries at most)."""
        names: dict[uuid.UUID, str] = {}
        clients = {rule.scope_id for rule in rules if rule.scope == "client"}
        jobs = {rule.scope_id for rule in rules if rule.scope == "job"}
        if clients:
            query = select(Client.id, Client.name).where(Client.id.in_(clients))
            query = self.policy.scope(principal, self.resource, query)
            for client_id, name in await self.db.execute(query):
                names[client_id] = name
        if jobs:
            job_query = (
                select(Job.id, Client.name, Job.name)
                .join(Client, Client.id == Job.client_id)
                .where(Job.id.in_(jobs))
            )
            job_query = self.policy.scope(principal, self.resource, job_query)
            for job_id, client_name, job_name in await self.db.execute(job_query):
                names[job_id] = f"{client_name} / {job_name}"
        return names

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        channel_id: uuid.UUID,
        scope: str,
        scope_id: uuid.UUID | None,
        events: list[str],
        now: datetime,
    ) -> ChannelRule:
        rule = ChannelRule(
            channel_id=channel_id,
            scope=scope,
            scope_id=scope_id,
            events=events,
            created_at=now,
        )
        self.db.add(rule)
        await self.db.flush()
        return rule

    @guarded("update")
    async def update(
        self, principal: Principal, rule: ChannelRule, **changes: Any
    ) -> None:
        unknown = set(changes) - _RULE_UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for field, value in changes.items():
            setattr(rule, field, value)
        await self.db.flush()

    @guarded("delete")
    async def delete(self, principal: Principal, rule: ChannelRule) -> None:
        await self.db.execute(delete(ChannelRule).where(ChannelRule.id == rule.id))


@dataclass(frozen=True, slots=True)
class NotificationRow:
    """A notification with its channel and, for a flip, the job and client."""

    notification: Notification
    channel_label: str
    channel_kind: str
    job_id: uuid.UUID | None
    job_name: str | None
    client_id: uuid.UUID | None
    client_name: str | None


@dataclass(frozen=True, slots=True)
class FlipRow:
    """A flip with the names of its job and client."""

    flip: Flip
    job_name: str
    client_name: str


@dataclass(frozen=True, slots=True)
class Reminder:
    """A flip still in force after a day, and a channel told about it."""

    flip_id: uuid.UUID
    channel_id: uuid.UUID


class NotificationRepository(Repository):
    resource = "notification"

    @guarded("read")
    async def hold_job(self, principal: Principal, job_id: uuid.UUID) -> bool:
        """Lock the job FOR KEY SHARE until the transaction ends; False when
        it is gone. A client delete locks the client's jobs FOR UPDATE first
        (app/repos/client_delete.py), so it either waits for the
        notifications queued here and deletes them too, or runs first and
        leaves nothing to queue."""
        query = select(Job.id).where(Job.id == job_id).with_for_update(key_share=True)
        return (await self.db.scalars(query)).one_or_none() is not None

    @guarded("read")
    async def matching_channels(
        self,
        principal: Principal,
        *,
        client_id: uuid.UUID,
        job_id: uuid.UUID,
        event: str,
    ) -> list[uuid.UUID]:
        """Enabled channels with a rule for the event that covers the job:
        scope all, the job's client or the job itself. A channel with several
        such rules is listed once."""
        covers = or_(
            ChannelRule.scope == "all",
            and_(ChannelRule.scope == "client", ChannelRule.scope_id == client_id),
            and_(ChannelRule.scope == "job", ChannelRule.scope_id == job_id),
        )
        query = (
            select(Channel.id)
            .join(ChannelRule, ChannelRule.channel_id == Channel.id)
            .where(
                Channel.enabled.is_(True),
                ChannelRule.events.contains([event]),
                covers,
            )
            .distinct()
            .order_by(Channel.id)
        )
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("create")
    async def queue(self, principal: Principal, rows: Sequence[dict[str, Any]]) -> int:
        """Insert queued notifications (channel_id, event, flip_id or
        digest_day, created_at, next_attempt_at); one that exists already is
        left alone. The number inserted."""
        if not rows:
            return 0
        # Every row with every column: one multi-row INSERT needs that.
        values = [{"id": uuid.uuid4(), **_QUEUED, **row} for row in rows]
        statement = (
            insert(Notification)
            .values(values)
            .on_conflict_do_nothing()
            .returning(Notification.id)
        )
        return len((await self.db.execute(statement)).all())

    @guarded("list")
    async def due(
        self, principal: Principal, *, now: datetime, limit: int
    ) -> list[uuid.UUID]:
        """Queued and retrying notifications whose time has come, oldest due
        first."""
        query = (
            select(Notification.id)
            .where(
                Notification.status.in_(OPEN_STATUSES),
                Notification.next_attempt_at <= now,
            )
            .order_by(Notification.next_attempt_at, Notification.id)
            .limit(limit)
        )
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("update")
    async def claim(
        self, principal: Principal, notification_id: uuid.UUID, *, now: datetime
    ) -> tuple[Notification, Channel] | None:
        """Lock a due notification and read its channel; None when it is not
        due any more or another transaction holds it."""
        query = (
            select(Notification, Channel)
            .join(Channel, Channel.id == Notification.channel_id)
            .where(
                Notification.id == notification_id,
                Notification.status.in_(OPEN_STATUSES),
                Notification.next_attempt_at <= now,
            )
            .with_for_update(of=Notification, skip_locked=True)
        )
        query = self.policy.scope(principal, self.resource, query)
        row = (await self.db.execute(query)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    @guarded("update")
    async def finish(
        self,
        principal: Principal,
        notification: Notification,
        **changes: Any,
    ) -> None:
        """Write the outcome of one attempt (status, attempts, error,
        last_attempt_at, next_attempt_at, sent_at)."""
        for field, value in changes.items():
            setattr(notification, field, value)
        await self.db.flush()

    @guarded("read")
    async def flip(self, principal: Principal, flip_id: uuid.UUID) -> FlipRow | None:
        """The flip with the names of its job and client."""
        query = (
            select(Flip, Job.name, Client.name)
            .join(Job, Job.id == Flip.job_id)
            .join(Client, Client.id == Flip.client_id)
            .where(Flip.id == flip_id)
        )
        query = self.policy.scope(principal, self.resource, query)
        row = (await self.db.execute(query)).one_or_none()
        if row is None:
            return None
        return FlipRow(flip=row[0], job_name=row[1], client_name=row[2])

    @guarded("list")
    async def digest_channels(
        self, principal: Principal, *, day: date
    ) -> list[uuid.UUID]:
        """Enabled channels with a digest rule that have no digest of day."""
        sent = exists().where(
            Notification.channel_id == Channel.id, Notification.digest_day == day
        )
        query = (
            select(Channel.id)
            .join(ChannelRule, ChannelRule.channel_id == Channel.id)
            .where(
                Channel.enabled.is_(True),
                ChannelRule.events.contains(["digest"]),
                ~sent,
            )
            .distinct()
            .order_by(Channel.id)
        )
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("list")
    async def reminders(
        self, principal: Principal, *, start: datetime, end: datetime, limit: int
    ) -> list[Reminder]:
        """Flips to failing or missed made in [start, end) whose job has not
        changed state since and is not acknowledged, with each enabled
        channel that was notified of them and has no reminder yet."""
        later = aliased(Flip)
        reminded = aliased(Notification)
        changed = exists().where(later.job_id == Flip.job_id, later.at > Flip.at)
        done = exists().where(
            reminded.flip_id == Flip.id,
            reminded.channel_id == Notification.channel_id,
            reminded.event == "reminder",
        )
        query = (
            select(Flip.id, Notification.channel_id)
            .join(Notification, Notification.flip_id == Flip.id)
            .join(Channel, Channel.id == Notification.channel_id)
            .join(Job, Job.id == Flip.job_id)
            .where(
                Flip.at >= start,
                Flip.at < end,
                Notification.event.in_(REMINDED_EVENTS),
                Channel.enabled.is_(True),
                Job.acknowledged_at.is_(None),
                ~changed,
                ~done,
            )
            .order_by(Flip.at, Flip.id, Notification.channel_id)
            .limit(limit)
        )
        query = self.policy.scope(principal, self.resource, query)
        return [
            Reminder(flip_id=row[0], channel_id=row[1])
            for row in await self.db.execute(query)
        ]

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        status: str | None,
        channel_id: uuid.UUID | None,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[NotificationRow]:
        """Notifications, newest first, before the (created_at, id) cursor."""
        query = (
            select(
                Notification,
                Channel.label,
                Channel.kind,
                Flip.job_id,
                Job.name,
                Flip.client_id,
                Client.name,
            )
            .join(Channel, Channel.id == Notification.channel_id)
            .outerjoin(Flip, Flip.id == Notification.flip_id)
            .outerjoin(Job, Job.id == Flip.job_id)
            .outerjoin(Client, Client.id == Flip.client_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
        if status is not None:
            query = query.where(Notification.status == status)
        if channel_id is not None:
            query = query.where(Notification.channel_id == channel_id)
        if after is not None:
            query = query.where(
                tuple_(Notification.created_at, Notification.id) < after
            )
        query = self.policy.scope(principal, self.resource, query)
        return [
            NotificationRow(
                notification=row[0],
                channel_label=row[1],
                channel_kind=row[2],
                job_id=row[3],
                job_name=row[4],
                client_id=row[5],
                client_name=row[6],
            )
            for row in await self.db.execute(query)
        ]

    @guarded("count")
    async def queue_counts(
        self, principal: Principal, *, failed_since: datetime
    ) -> tuple[int, int]:
        """Notifications waiting (queued or retrying), and those that failed
        for good since failed_since (their last attempt)."""
        pending = func.count().filter(Notification.status.in_(OPEN_STATUSES))
        failed = func.count().filter(
            Notification.status == "failed",
            Notification.last_attempt_at >= failed_since,
        )
        query = select(pending, failed).select_from(Notification)
        query = self.policy.scope(principal, self.resource, query)
        row = (await self.db.execute(query)).one()
        return int(row[0]), int(row[1])
