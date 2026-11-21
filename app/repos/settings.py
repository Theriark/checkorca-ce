"""The single settings row. Stored credentials go through the SecretBox."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import AccessPolicy, Principal
from app.db.models import AppSettings
from app.repos.base import Repository, guarded
from app.security.crypto import SecretBox


class SettingsRepository(Repository):
    resource = "settings"

    def __init__(self, db: AsyncSession, policy: AccessPolicy, box: SecretBox) -> None:
        super().__init__(db, policy)
        self._box = box

    @guarded("read")
    async def get(self, principal: Principal) -> AppSettings:
        return (await self.db.scalars(select(AppSettings))).one()

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
