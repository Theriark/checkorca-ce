"""tokens: list, create and revoke API tokens (admin only).

The token value is returned once, by the create call; the database keeps only
its SHA-256. DELETE revokes: the row stays for the audit trail.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Request

from app.api.deps import AdminDep, DbDep, ServicesDep, record_audit
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_cursor,
    encode_cursor,
)
from app.api.problems import ProblemError
from app.api.v1.schemas import CreatedToken, NewToken, TokenOut, TokenPage
from app.repos.tokens import TokenRepository
from app.security.tokens import new_api_token, sha256_hex

router = APIRouter(prefix="/tokens", tags=["tokens"])


def parse_token_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    values = decode_cursor(cursor, ("created_at", "id"))
    try:
        return datetime.fromisoformat(values["created_at"]), uuid.UUID(values["id"])
    except ValueError:
        raise ProblemError(
            400, "Invalid cursor", "Use next_cursor as returned."
        ) from None


@router.get("")
async def list_tokens(
    context: AdminDep,
    services: ServicesDep,
    db: DbDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> TokenPage:
    """Every token, revoked ones included, oldest first. Never the value."""
    after = None if cursor is None else parse_token_cursor(cursor)
    tokens = TokenRepository(db, services.policy)
    found = await tokens.page(context.principal, after=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_cursor(
            {"created_at": last.created_at.isoformat(), "id": str(last.id)}
        )
    return TokenPage(
        items=[TokenOut.model_validate(token) for token in items],
        next_cursor=next_cursor,
    )


@router.post("", status_code=201)
async def create_token(
    body: NewToken,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> CreatedToken:
    """Create a token. Its value is in this answer only."""
    value = new_api_token()
    tokens = TokenRepository(db, services.policy)
    token = await tokens.create(
        context.principal,
        label=body.label,
        scope=body.scope,
        token_sha256=sha256_hex(value),
        created_by=context.user.id,
        now=services.clock.now(),
    )
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "token.create",
        target_kind="api_token",
        target_id=token.id,
        scope=body.scope,
    )
    await db.commit()
    shown = TokenOut.model_validate(token)
    return CreatedToken(**shown.model_dump(), token=value)


@router.delete("/{token_id}", status_code=204)
async def revoke_token(
    token_id: uuid.UUID,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> None:
    """Revoke a token. Revoking it again changes nothing."""
    tokens = TokenRepository(db, services.policy)
    token = await tokens.get(context.principal, token_id)
    if token is None:
        raise ProblemError(404, "Token not found")
    if token.revoked_at is None:
        await tokens.revoke(context.principal, token, services.clock.now())
        await record_audit(
            services,
            db,
            request,
            context.principal.actor,
            "token.revoke",
            target_kind="api_token",
            target_id=token.id,
        )
        await db.commit()
