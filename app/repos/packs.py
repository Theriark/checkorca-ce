"""Parser packs: the built-in packs, written at start, and custom packs.

A built-in row is written from app/parsers/packs by sync_builtin and never
changed through the API; a custom row belongs to the users. enabled is the
users' choice for both and the sync keeps it. A custom pack whose id a later
release ships as a built-in pack stays custom: the sync leaves it alone.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import defer

from app.access import Principal
from app.db.models import ParserPack
from app.parsers.model import Pack
from app.repos.base import Repository, guarded


class PackRepository(Repository):
    resource = "parser_pack"

    @guarded("list")
    async def page(
        self, principal: Principal, *, after: str | None, limit: int
    ) -> list[ParserPack]:
        """Packs ordered by id, after the cursor; without their YAML."""
        query = (
            select(ParserPack)
            .options(defer(ParserPack.yaml))
            .order_by(ParserPack.id)
            .limit(limit)
        )
        if after is not None:
            query = query.where(ParserPack.id > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("list")
    async def enabled(self, principal: Principal) -> list[ParserPack]:
        """The packs that parse mail, with their YAML, ordered by id."""
        query = (
            select(ParserPack)
            .where(ParserPack.enabled.is_(True))
            .order_by(ParserPack.id)
        )
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(
        self, principal: Principal, pack_id: str, *, for_update: bool = False
    ) -> ParserPack | None:
        """The pack with its YAML; for_update locks its row."""
        query = select(ParserPack).where(ParserPack.id == pack_id)
        if for_update:
            query = query.with_for_update()
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("create")
    async def save_custom(
        self, principal: Principal, pack: Pack, text: str, now: datetime
    ) -> ParserPack | None:
        """Create or replace a custom pack; None when a built-in pack has the id
        (nothing is written). A new pack is enabled; a replaced one keeps its
        choice."""
        values = {
            "version": pack.version,
            "vendor": pack.vendor,
            "status": pack.status,
            "yaml": text,
            "updated_at": now,
        }
        statement = (
            insert(ParserPack)
            .values(
                id=pack.id, source="custom", enabled=True, created_at=now, **values
            )
            .on_conflict_do_update(
                index_elements=[ParserPack.id],
                set_=values,
                where=ParserPack.source == "custom",
            )
            .returning(ParserPack)
            .execution_options(populate_existing=True)
        )
        saved: ParserPack | None = (await self.db.scalars(statement)).one_or_none()
        return saved

    @guarded("update")
    async def set_enabled(
        self, principal: Principal, pack: ParserPack, enabled: bool, now: datetime
    ) -> None:
        if pack.enabled != enabled:
            pack.enabled = enabled
            pack.updated_at = now
            await self.db.flush()

    @guarded("sync")
    async def sync_builtin(
        self,
        principal: Principal,
        packs: Sequence[tuple[Pack, str]],
        now: datetime,
    ) -> None:
        """Write the built-in packs: new ones enabled, changed ones updated in
        place, and built-in rows the release no longer ships removed. Rows
        that are already equal are not written."""
        for pack, text in packs:
            values = {
                "version": pack.version,
                "vendor": pack.vendor,
                "status": pack.status,
                "yaml": text,
                "updated_at": now,
            }
            changed = or_(
                ParserPack.version != pack.version,
                ParserPack.vendor != pack.vendor,
                ParserPack.status != pack.status,
                ParserPack.yaml != text,
            )
            await self.db.execute(
                insert(ParserPack)
                .values(
                    id=pack.id,
                    source="builtin",
                    enabled=True,
                    created_at=now,
                    **values,
                )
                .on_conflict_do_update(
                    index_elements=[ParserPack.id],
                    set_=values,
                    where=and_(ParserPack.source == "builtin", changed),
                )
            )
        shipped = [pack.id for pack, _ in packs]
        await self.db.execute(
            delete(ParserPack).where(
                ParserPack.source == "builtin", ParserPack.id.not_in(shipped)
            )
        )
