"""Inboxes: where alert mail and webhooks arrive.

The repository stores what it is given: the API encrypts the IMAP password
with the SecretBox before an inbox is created or changed, and only the IMAP
connector of the worker (phase C4-I) decrypts it. A webhook inbox's token is
made here, returned once and kept as SHA-256.
"""

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import delete, func, select, tuple_, update

from app.access import Principal
from app.db.models import Inbox
from app.repos.base import Repository, guarded
from app.security.tokens import new_inbox_code, new_inbox_token, sha256_hex

# The fields update() may change; id, kind, code and created_at never change.
_UPDATABLE: Final = frozenset(
    {
        "label",
        "imap_host",
        "imap_port",
        "imap_username",
        "imap_password_enc",
        "imap_folder",
        "imap_poll_seconds",
        "imap_tls",
        "sender_allowlist",
        "require_auth_results",
    }
)


class InboxRepository(Repository):
    resource = "inbox"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        kind: str | None,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[Inbox]:
        """Inboxes, oldest first, after the (created_at, id) cursor."""
        query = select(Inbox).order_by(Inbox.created_at, Inbox.id).limit(limit)
        if kind is not None:
            query = query.where(Inbox.kind == kind)
        if after is not None:
            query = query.where(tuple_(Inbox.created_at, Inbox.id) > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("list")
    async def activity(self, principal: Principal, *, limit: int) -> list[Inbox]:
        """Inboxes by label, for System status."""
        query = select(Inbox).order_by(Inbox.label, Inbox.id).limit(limit)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, inbox_id: uuid.UUID, *, for_update: bool = False
    ) -> Inbox | None:
        query = select(Inbox).where(Inbox.id == inbox_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def find_by_code(
        self, principal: Principal, code: str, *, kinds: tuple[str, ...] = ()
    ) -> Inbox | None:
        """The inbox with this code (any case), optionally of one of the kinds.

        The SMTP listener asks with kinds=("smtp",) at RCPT time; the ingest
        URL with kinds=("webhook",).
        """
        query = select(Inbox).where(Inbox.code == code.strip().lower())
        if kinds:
            query = query.where(Inbox.kind.in_(kinds))
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def find_by_token(self, principal: Principal, token: str) -> Inbox | None:
        """The webhook inbox whose token this is (compared by SHA-256)."""
        query = select(Inbox).where(Inbox.token_sha256 == sha256_hex(token.strip()))
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
    ) -> tuple[Inbox, str | None]:
        """A new inbox with a fresh code; for a webhook inbox also its token,
        returned here and never again."""
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot set {sorted(unknown)}")
        token = new_inbox_token() if kind == "webhook" else None
        inbox = Inbox(
            kind=kind,
            label=label,
            code=new_inbox_code(),
            token_sha256=None if token is None else sha256_hex(token),
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.db.add(inbox)
        await self.db.flush()
        return inbox, token

    @guarded("update")
    async def update(
        self, principal: Principal, inbox: Inbox, *, now: datetime, **changes: Any
    ) -> None:
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for field, value in changes.items():
            setattr(inbox, field, value)
        inbox.updated_at = now
        await self.db.flush()

    @guarded("update")
    async def rotate_token(
        self, principal: Principal, inbox: Inbox, *, now: datetime
    ) -> str:
        """A new token for a webhook inbox; the old one stops working."""
        if inbox.kind != "webhook":
            raise ValueError("only a webhook inbox has a token")
        token = new_inbox_token()
        inbox.token_sha256 = sha256_hex(token)
        inbox.updated_at = now
        await self.db.flush()
        return token

    @guarded("update")
    async def mark_received(
        self, principal: Principal, inbox_id: uuid.UUID, at: datetime
    ) -> None:
        """last_message_at moves forward to at, never back."""
        latest = func.greatest(func.coalesce(Inbox.last_message_at, at), at)
        await self.db.execute(
            update(Inbox).where(Inbox.id == inbox_id).values(last_message_at=latest)
        )

    @guarded("delete")
    async def delete(self, principal: Principal, inbox: Inbox) -> None:
        """Delete the inbox. Its messages stay (inbox_id becomes NULL) as the
        evidence of their results until the retention purge."""
        await self.db.execute(delete(Inbox).where(Inbox.id == inbox.id))
