"""Clients: the MSP's customers. Names are unique ignoring case and spacing."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, tuple_

from app.access import Principal
from app.db.models import Client, name_key
from app.matcher import names_client
from app.repos.base import Repository, guarded
from app.repos.client_delete import delete_client_rows

# The fields update() may change; id and created_at never change.
_UPDATABLE = frozenset({"name", "notes", "aliases", "archived"})


def contains_pattern(text: str) -> str:
    """An ILIKE pattern (escape character backslash) for text anywhere."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class ClientRepository(Repository):
    resource = "client"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        q: str | None,
        archived: bool,
        after: tuple[str, uuid.UUID] | None,
        limit: int,
    ) -> list[Client]:
        """Clients ordered by name, after the (name_key, id) cursor.

        q matches part of the name or of an alias, ignoring case.
        """
        query = (
            select(Client)
            .where(Client.archived.is_(archived))
            .order_by(Client.name_key, Client.id)
            .limit(limit)
        )
        if q:
            pattern = contains_pattern(q)
            aliases = func.array_to_string(Client.aliases, " ")
            query = query.where(
                or_(
                    Client.name.ilike(pattern, escape="\\"),
                    aliases.ilike(pattern, escape="\\"),
                )
            )
        if after is not None:
            query = query.where(tuple_(Client.name_key, Client.id) > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, client_id: uuid.UUID, *, for_update: bool = False
    ) -> Client | None:
        """The client; for_update locks its row until the transaction ends."""
        query = select(Client).where(Client.id == client_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def find_by_name(
        self, principal: Principal, name: str, *, for_update: bool = False
    ) -> Client | None:
        """The client whose name equals name, ignoring case and spacing;
        for_update locks its row until the transaction ends."""
        query = select(Client).where(Client.name_key == name_key(name))
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("list")
    async def named_elsewhere(
        self, principal: Principal, client_id: uuid.UUID, hint: str
    ) -> bool:
        """Whether a client other than client_id, archived or not, has the hint
        as its name or one of its aliases (compared as the matcher does)."""
        query = select(Client.name, Client.aliases).where(Client.id != client_id)
        query = self.policy.scope(principal, self.resource, query)
        rows = (await self.db.execute(query)).all()
        return any(names_client(row.name, row.aliases, hint) for row in rows)

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        notes: str,
        aliases: list[str],
        now: datetime,
    ) -> Client:
        client = Client(
            name=name,
            name_key=name_key(name),
            notes=notes,
            aliases=aliases,
            archived=False,
            created_at=now,
        )
        self.db.add(client)
        await self.db.flush()
        return client

    @guarded("update")
    async def update(
        self, principal: Principal, client: Client, **changes: Any
    ) -> None:
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for field, value in changes.items():
            setattr(client, field, value)
        if "name" in changes:
            client.name_key = name_key(changes["name"])
        await self.db.flush()

    @guarded("delete")
    async def delete(self, principal: Principal, client: Client) -> None:
        """Delete the client and every row of the delete map."""
        await delete_client_rows(self.db, client.id)
