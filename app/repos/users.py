"""Users: local accounts with the role admin or technician."""

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.access import Principal, Role
from app.db.locks import USER_BOOTSTRAP_LOCK
from app.db.models import AppUser
from app.repos.base import Repository, guarded

MAX_EMAIL_LENGTH = 254
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# The fields update() may change; id, email and created_at never change.
_UPDATABLE = frozenset(
    {"password_hash", "role", "failed_logins", "locked_until", "disabled"}
)


def normalise_email(value: str) -> str:
    """Trim and lower-case an e-mail address; ValueError when it is not one."""
    email = value.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL.fullmatch(email):
        raise ValueError("must be an e-mail address")
    return email


class UserRepository(Repository):
    resource = "user"

    @guarded("list")
    async def page(
        self, principal: Principal, *, after_email: str | None, limit: int
    ) -> list[AppUser]:
        """Users ordered by e-mail address, after the cursor."""
        query = select(AppUser).order_by(AppUser.email).limit(limit)
        if after_email is not None:
            query = query.where(AppUser.email > after_email)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(self, principal: Principal, user_id: uuid.UUID) -> AppUser | None:
        query = select(AppUser).where(AppUser.id == user_id)
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def find_by_email(
        self, principal: Principal, email: str, *, for_update: bool = False
    ) -> AppUser | None:
        """The user with this (normalised) address; for_update locks the row."""
        query = select(AppUser).where(AppUser.email == email)
        if for_update:
            query = query.with_for_update()
        return (await self.db.scalars(query)).one_or_none()

    @guarded("count")
    async def count(self, principal: Principal) -> int:
        query = select(func.count()).select_from(AppUser)
        return int((await self.db.execute(query)).scalar_one())

    @guarded("count")
    async def lock_active_admins(self, principal: Principal) -> list[uuid.UUID]:
        """Lock and return the enabled admins, so a concurrent demotion waits.

        Two admins demoting each other at once would otherwise both see a second
        admin and leave none.
        """
        query = (
            select(AppUser.id)
            .where(AppUser.role == "admin", AppUser.disabled.is_(False))
            .with_for_update()
        )
        return list((await self.db.scalars(query)).all())

    @guarded("bootstrap")
    async def lock_bootstrap(self, principal: Principal) -> None:
        """Serialise the first run and the seed until the transaction ends."""
        await self.db.execute(select(func.pg_advisory_xact_lock(USER_BOOTSTRAP_LOCK)))

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        email: str,
        password_hash: str,
        role: Role,
        now: datetime,
    ) -> AppUser:
        user = AppUser(
            email=normalise_email(email),
            password_hash=password_hash,
            role=role,
            failed_logins=0,
            disabled=False,
            created_at=now,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    @guarded("update")
    async def update(self, principal: Principal, user: AppUser, **changes: Any) -> None:
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        for name, value in changes.items():
            setattr(user, name, value)
        await self.db.flush()

    @guarded("delete")
    async def delete(self, principal: Principal, user: AppUser) -> None:
        await self.db.delete(user)
        await self.db.flush()
