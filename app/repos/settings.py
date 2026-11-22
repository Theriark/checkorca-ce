"""The single settings row. Stored credentials go through the SecretBox."""

from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import AccessPolicy, Principal
from app.db.models import AppSettings
from app.repos.base import Repository, guarded
from app.security.crypto import SecretBox

# The fields of the digest settings (settings route, phase C9-B).
_DIGEST_FIELDS: Final = frozenset(
    {"digest_time_local", "digest_timezone", "reminder_24h"}
)


class SettingsRepository(Repository):
    resource = "settings"

    def __init__(self, db: AsyncSession, policy: AccessPolicy, box: SecretBox) -> None:
        super().__init__(db, policy)
        self._box = box

    @guarded("read")
    async def get(
        self, principal: Principal, *, for_update: bool = False
    ) -> AppSettings:
        query = select(AppSettings)
        if for_update:
            query = query.with_for_update()
        return (await self.db.scalars(query)).one()

    @guarded("update")
    async def update_digest(
        self, principal: Principal, row: AppSettings, **changes: Any
    ) -> None:
        """Change digest_time_local, digest_timezone or reminder_24h."""
        unknown = set(changes) - _DIGEST_FIELDS
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for field, value in changes.items():
            setattr(row, field, value)
        await self.db.flush()

    @guarded("read")
    async def external_heartbeat_url(self, principal: Principal) -> str | None:
        """The decrypted heartbeat URL, for the worker only (never the API)."""
        row = (await self.db.scalars(select(AppSettings))).one()
        if row.external_heartbeat_url_enc is None:
            return None
        return self._box.decrypt(row.external_heartbeat_url_enc)

    @guarded("update")
    async def mark_demo_seeded(self, principal: Principal) -> None:
        """The demo data is in (app/seed/demo.py); it is never seeded again."""
        row = (await self.db.scalars(select(AppSettings))).one()
        row.demo_seeded = True
        await self.db.flush()

    @guarded("update")
    async def set_external_heartbeat_url(
        self, principal: Principal, url: str | None
    ) -> None:
        row = (await self.db.scalars(select(AppSettings))).one()
        row.external_heartbeat_url_enc = None if url is None else self._box.encrypt(url)
        await self.db.flush()
