"""API tokens: label, scope and the SHA-256 of the token; revoked, never deleted."""

import uuid
from datetime import datetime

from sqlalchemy import select, tuple_

from app.access import Principal, TokenScope
from app.db.models import ApiToken
from app.repos.base import Repository, guarded


class TokenRepository(Repository):
    resource = "api_token"

    @guarded("list")
    async def page(
        self,
        principal: Principal,
        *,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[ApiToken]:
        """Tokens, oldest first, after the (created_at, id) cursor."""
        query = select(ApiToken).order_by(ApiToken.created_at, ApiToken.id).limit(limit)
        if after is not None:
            query = query.where(tuple_(ApiToken.created_at, ApiToken.id) > after)
        query = self.policy.scope(principal, self.resource, query)
        return list((await self.db.scalars(query)).all())

    @guarded("read")
    async def get(self, principal: Principal, token_id: uuid.UUID) -> ApiToken | None:
        query = select(ApiToken).where(ApiToken.id == token_id)
        query = self.policy.scope(principal, self.resource, query)
        return (await self.db.scalars(query)).one_or_none()

    @guarded("read")
    async def find_active(
        self, principal: Principal, token_sha256: str
    ) -> ApiToken | None:
        """The token with this hash unless it was revoked."""
        query = select(ApiToken).where(
            ApiToken.token_sha256 == token_sha256, ApiToken.revoked_at.is_(None)
        )
        return (await self.db.scalars(query)).one_or_none()

    @guarded("create")
    async def create(
        self,
        principal: Principal,
        *,
        label: str,
        scope: TokenScope,
        token_sha256: str,
        created_by: uuid.UUID | None,
        now: datetime,
    ) -> ApiToken:
        token = ApiToken(
            label=label,
            scope=scope,
            token_sha256=token_sha256,
            created_by=created_by,
            created_at=now,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    @guarded("revoke")
    async def revoke(
        self, principal: Principal, token: ApiToken, now: datetime
    ) -> None:
        """Revoke once; a second revoke keeps the first time."""
        if token.revoked_at is None:
            token.revoked_at = now
            await self.db.flush()

    @guarded("update")
    async def touch(self, principal: Principal, token: ApiToken, now: datetime) -> None:
        token.last_used_at = now
        await self.db.flush()
