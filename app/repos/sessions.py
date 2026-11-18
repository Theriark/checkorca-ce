"""Browser sessions: the hash of the cookie secret, the CSRF token, the expiry."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select

from app.access import Principal
from app.db.models import AppSession, AppUser
from app.repos.base import Repository, guarded
from app.security.sessions import SESSION_MAX_AGE, SESSION_TTL


class SessionRepository(Repository):
    resource = "session"

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        id_hash: str,
        user_id: uuid.UUID,
        csrf_token: str,
        now: datetime,
        ip: str | None,
    ) -> AppSession:
        session = AppSession(
            id_hash=id_hash,
            user_id=user_id,
            csrf_token=csrf_token,
            created_at=now,
            expires_at=now + SESSION_TTL,
            last_seen_at=now,
            ip=ip,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    @guarded("read")
    async def resolve(
        self, principal: Principal, id_hash: str, now: datetime
    ) -> tuple[AppSession, AppUser] | None:
        """The live session and its enabled user, or None.

        Live: used within the last 12 hours and signed in less than 7 days ago.
        """
        query = (
            select(AppSession, AppUser)
            .join(AppUser, AppUser.id == AppSession.user_id)
            .where(
                AppSession.id_hash == id_hash,
                AppSession.expires_at > now,
                AppSession.created_at > now - SESSION_MAX_AGE,
                AppUser.disabled.is_(False),
            )
        )
        row = (await self.db.execute(query)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    @guarded("update")
    async def touch(
        self, principal: Principal, session: AppSession, now: datetime
    ) -> None:
        """Record use and move the expiry 12 hours past now."""
        session.last_seen_at = now
        session.expires_at = now + SESSION_TTL
        await self.db.flush()

    @guarded("delete")
    async def delete(self, principal: Principal, id_hash: str) -> None:
        await self.db.execute(delete(AppSession).where(AppSession.id_hash == id_hash))

    @guarded("delete")
    async def delete_for_user(
        self, principal: Principal, user_id: uuid.UUID, *, keep: str | None = None
    ) -> None:
        """End every session of a user, except the one whose hash is keep."""
        query = delete(AppSession).where(AppSession.user_id == user_id)
        if keep is not None:
            query = query.where(AppSession.id_hash != keep)
        await self.db.execute(query)

    @guarded("delete")
    async def purge_expired(self, principal: Principal, now: datetime) -> None:
        await self.db.execute(delete(AppSession).where(AppSession.expires_at <= now))
