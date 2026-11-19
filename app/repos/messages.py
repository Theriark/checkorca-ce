"""Raw messages: every received message, compressed, until purge_after.

Lists never load body_zlib (up to 5 MB each); only get() does. Duplicates
(same inbox and Message-ID, or same inbox and content hash) are refused by two
unique constraints, so two deliveries at the same moment still store one row.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import defer

from app.access import Principal
from app.db.models import AppSettings, RawMessage
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
