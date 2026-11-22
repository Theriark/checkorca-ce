"""Services of the running app and the FastAPI dependencies of the routes.

Authentication: a browser session (cookie plus X-CSRF-Token on every state
change) for the SPA and the admin routes; an API token in the Authorization
header (Bearer) for scripts, with the scope ingest or read.
"""

import ipaddress
import math
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.access import SYSTEM, AccessPolicy, Principal, TokenScope, as_role, as_scope
from app.api.bench import BenchRunner
from app.api.problems import ProblemError
from app.clock import Clock
from app.db.models import AppSession, AppUser
from app.ext.audit import AuditRecord, AuditSink, DetailValue
from app.ext.parsers import ParserPackSource
from app.ext.reports import ReportRenderer
from app.repos.sessions import SessionRepository
from app.repos.tokens import TokenRepository
from app.security.crypto import SecretBox
from app.security.passwords import PasswordService
from app.security.ratelimit import RateLimiter
from app.security.sessions import (
    CSRF_HEADER,
    SESSION_COOKIE,
    TOUCH_INTERVAL,
    UNSAFE_METHODS,
    csrf_matches,
    set_session_cookie,
)
from app.security.tokens import sha256_hex
from app.settings import Settings


@dataclass(frozen=True)
class Services:
    """Everything the routes share, built once by create_app."""

    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    clock: Clock
    policy: AccessPolicy
    audit: AuditSink
    passwords: PasswordService
    secret_box: SecretBox
    # Sign-in and first run, per client address.
    login_limiter: RateLimiter
    # Requests with an API token, per token.
    token_limiter: RateLimiter
    # packs/test: the child processes that run it, and a limit per user.
    bench: BenchRunner
    bench_limiter: RateLimiter
    # The packs that parse mail (and that packs/test tries).
    pack_source: ParserPackSource
    # How the morning digest reads (digest/preview).
    report_renderer: ReportRenderer


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


async def get_db(services: ServicesDep) -> AsyncIterator[AsyncSession]:
    """One database session per request; routes commit what they change."""
    async with services.sessionmaker() as db:
        yield db


DbDep = Annotated[AsyncSession, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    """The client address, or None when it is not an IP address.

    Behind a proxy, uvicorn takes it from X-Forwarded-For only when
    FORWARDED_ALLOW_IPS names the proxy network (never *: the left-most entry is
    the client's to choose). The check keeps any other value out of the rate
    limit keys and the 45-character address columns: an IPv6 zone id (any
    length, the sender's to choose) is refused, and an IPv4-mapped IPv6 address
    becomes its IPv4 form so one client has one bucket.
    """
    if request.client is None:
        return None
    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.scope_id is not None:
            return None
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
    return str(address)


def enforce_rate_limit(limiter: RateLimiter, key: str) -> None:
    wait = limiter.hit(key)
    if wait > 0:
        raise ProblemError(
            429,
            "Too many requests",
            "Wait before trying again.",
            headers={"Retry-After": str(max(1, math.ceil(wait)))},
        )


async def record_audit(
    services: Services,
    db: AsyncSession,
    request: Request,
    actor: str,
    action: str,
    *,
    target_kind: str | None = None,
    target_id: object = None,
    **details: DetailValue,
) -> None:
    """Add an audit event to the request's transaction."""
    await services.audit.record(
        db,
        AuditRecord(
            at=services.clock.now(),
            actor=actor,
            action=action,
            target_kind=target_kind,
            target_id=None if target_id is None else str(target_id),
            ip=client_ip(request),
            details=details,
        ),
    )


@dataclass(frozen=True)
class SessionContext:
    """The signed-in user of a browser session."""

    principal: Principal
    user: AppUser
    session: AppSession


async def require_session(
    request: Request, response: Response, services: ServicesDep, db: DbDep
) -> SessionContext:
    """A live session; on a state change also the matching X-CSRF-Token."""
    secret = request.cookies.get(SESSION_COOKIE)
    if not secret:
        raise ProblemError(401, "Not signed in", "Sign in first.")
    now = services.clock.now()
    sessions = SessionRepository(db, services.policy)
    found = await sessions.resolve(SYSTEM, sha256_hex(secret), now)
    if found is None:
        raise ProblemError(401, "Not signed in", "The session has ended.")
    session, user = found
    csrf_ok = csrf_matches(session.csrf_token, request.headers.get(CSRF_HEADER))
    if request.method in UNSAFE_METHODS and not csrf_ok:
        raise ProblemError(
            403,
            "CSRF token missing or invalid",
            f"Send the session's csrf_token in the {CSRF_HEADER} header.",
        )
    if now - session.last_seen_at >= TOUCH_INTERVAL:
        await sessions.touch(SYSTEM, session, now)
        await db.commit()
        set_session_cookie(response, secret)
    principal = Principal.for_user(user.id, as_role(user.role))
    return SessionContext(principal=principal, user=user, session=session)


SessionDep = Annotated[SessionContext, Depends(require_session)]


async def require_admin(context: SessionDep) -> SessionContext:
    if not context.principal.is_admin:
        raise ProblemError(403, "Admin role required")
    return context


AdminDep = Annotated[SessionContext, Depends(require_admin)]


def require_token(
    *scopes: TokenScope,
) -> Callable[[Request, Services, AsyncSession], Awaitable[Principal]]:
    """A dependency that accepts an unrevoked API token of one of the scopes."""

    async def dependency(
        request: Request, services: ServicesDep, db: DbDep
    ) -> Principal:
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise ProblemError(
                401,
                "API token required",
                "Send the token as Authorization: Bearer <token>.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        tokens = TokenRepository(db, services.policy)
        token = await tokens.find_active(SYSTEM, sha256_hex(value.strip()))
        if token is None:
            raise ProblemError(
                401,
                "API token invalid",
                "The token is unknown or revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        enforce_rate_limit(services.token_limiter, str(token.id))
        scope = as_scope(token.scope)
        if scope not in scopes:
            raise ProblemError(403, "API token scope not allowed")
        now = services.clock.now()
        if token.last_used_at is None or now - token.last_used_at >= TOUCH_INTERVAL:
            await tokens.touch(SYSTEM, token, now)
            await db.commit()
        return Principal.for_token(token.id, scope)

    return dependency


_read_token = require_token("read")


async def require_reader(
    request: Request, response: Response, services: ServicesDep, db: DbDep
) -> Principal:
    """For read routes: an API token of scope read in the Authorization header,
    or else a signed-in session."""
    if "authorization" in request.headers:
        return await _read_token(request, services, db)
    context = await require_session(request, response, services, db)
    return context.principal


ReaderDep = Annotated[Principal, Depends(require_reader)]
