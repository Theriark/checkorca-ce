"""Raw messages: every received message, compressed, until purge_after.

Lists never load body_zlib (up to 5 MB each); only get() does. Duplicates
(same inbox and Message-ID, or same inbox and content hash) are refused by two
unique constraints, so two deliveries at the same moment still store one row.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import defer

from app.access import Principal
from app.db.models import PACK_PATH_LENGTH, AppSettings, Job, JobResult, RawMessage
from app.repos.base import Repository, guarded

# Kept when the settings row says nothing (it always does after c1_auth).
DEFAULT_KEEP_DAYS = 30


class RawMessageRepository(Repository):
    resource = "raw_message"

    @guarded("create")
    async def insert(self, principal: Principal, **fields: Any) -> uuid.UUID | None:
        """Store a message; None when the inbox already has it (no new row)."""
        statement = (
            insert(RawMessage)
            .values(id=uuid.uuid4(), **fields)
            .on_conflict_do_nothing()
            .returning(RawMessage.id)
        )
        result = await self.db.execute(statement)
        found: uuid.UUID | None = result.scalar_one_or_none()
        return found

    @guarded("read")
    async def find_duplicate(
        self,
        principal: Principal,
        *,
        inbox_id: uuid.UUID,
        message_id: str | None,
        body_sha256: str,
    ) -> uuid.UUID | None:
        """The stored message of the inbox with this Message-ID or content hash."""
        same = RawMessage.body_sha256 == body_sha256
        if message_id is not None:
            same = or_(same, RawMessage.message_id == message_id)
        query = (
            select(RawMessage.id)
            .where(RawMessage.inbox_id == inbox_id, same)
            .order_by(RawMessage.received_at, RawMessage.id)
            .limit(1)
        )
        query = self.policy.scope(principal, self.resource, query)
        found: uuid.UUID | None = (await self.db.scalars(query)).first()
        return found

    @guarded("read")
    async def keep_days(self, principal: Principal) -> int:
        """How many days a raw message is kept (settings.retention_raw_days)."""
        query = select(AppSettings.retention_raw_days)
        days = (await self.db.scalars(query)).first()
        return DEFAULT_KEEP_DAYS if days is None else int(days)

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        inbox_id: uuid.UUID | None,
        parse_state: str | None,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[RawMessage]:
        """Messages, newest first, before the (received_at, id) cursor; without
        their bodies."""
        query = (
            select(RawMessage)
            .options(defer(RawMessage.body_zlib))
            .order_by(RawMessage.received_at.desc(), RawMessage.id.desc())
            .limit(limit)
        )
        if inbox_id is not None:
            query = query.where(RawMessage.inbox_id == inbox_id)
        if parse_state is not None:
            query = query.where(RawMessage.parse_state == parse_state)
        if after is not None:
            query = query.where(tuple_(RawMessage.received_at, RawMessage.id) < after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, message_id: uuid.UUID
    ) -> RawMessage | None:
        """The message with its compressed body."""
        query = select(RawMessage).where(RawMessage.id == message_id)
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("list")
    async def pending_count(self, principal: Principal) -> int:
        """Messages that wait for the parser (phase C5)."""
        query = select(func.count()).select_from(RawMessage)
        query = query.where(RawMessage.parse_state == "pending")
        query = self.policy.scope(principal, self.resource, query)
        return int((await self.db.execute(query)).scalar_one())

    @guarded("delete")
    async def delete_with_results(
        self, principal: Principal, message: RawMessage
    ) -> int:
        """Delete the message and the results it produced (admin DELETE,
        C10-B); the number of results gone. occurrence.result_id of any
        kept occurrence becomes NULL where it named one of them, and the
        next evaluation decides again (docs/evaluator.md)."""
        gone = await self.db.execute(
            delete(JobResult).where(JobResult.raw_message_id == message.id)
        )
        await self.db.delete(message)
        await self.db.flush()
        return gone.rowcount or 0

    @guarded("parse")
    async def next_pending(self, principal: Principal) -> RawMessage | None:
        """The oldest message that waits for the parser, locked until the
        transaction ends; a message another session holds is skipped."""
        query = (
            select(RawMessage)
            .where(RawMessage.parse_state == "pending")
            .order_by(RawMessage.received_at, RawMessage.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("parse")
    async def record_parse(
        self,
        principal: Principal,
        message: RawMessage,
        *,
        state: str,
        at: datetime,
        pack_id: str | None = None,
        reason: str | None = None,
        path: str | None = None,
    ) -> None:
        """What the parser made of the message (parse_state and its reason)."""
        message.parse_state = state
        message.parsed_at = at
        message.parse_pack_id = pack_id
        message.parse_reason = reason
        message.parse_path = None if path is None else path[:PACK_PATH_LENGTH]
        await self.db.flush()

    @guarded("parse")
    async def fail_pending(
        self, principal: Principal, message_id: uuid.UUID, reason: str, at: datetime
    ) -> None:
        """Mark a message the parser could not handle as error, if it still
        waits, so the next tick does not take it again."""
        await self.db.execute(
            update(RawMessage)
            .where(RawMessage.id == message_id, RawMessage.parse_state == "pending")
            .values(parse_state="error", parse_reason=reason, parsed_at=at)
        )

    @guarded("update")
    async def refresh_client(self, principal: Principal, message_id: uuid.UUID) -> None:
        """Set client_id when every result of the message is bound to a job of
        one client, else clear it (a client delete then removes the message
        only when all of it was that client's). The message row is locked
        first, so two transactions that bind results of one message refresh
        it one after the other and the second reads the first one's binding;
        callers refresh several messages in id order (one lock order)."""
        lock = select(RawMessage.id).where(RawMessage.id == message_id)
        await self.db.execute(lock.with_for_update())
        query = (
            select(JobResult.job_id, Job.client_id)
            .outerjoin(Job, Job.id == JobResult.job_id)
            .where(JobResult.raw_message_id == message_id)
        )
        clients = {client_id for _, client_id in (await self.db.execute(query)).all()}
        client_id = next(iter(clients)) if len(clients) == 1 else None
        await self.db.execute(
            update(RawMessage)
            .where(RawMessage.id == message_id)
            .values(client_id=client_id)
        )
