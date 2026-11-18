"""auth: setup-state, first-run, login, logout, me (Interfaces chapter).

First run creates the first admin and works only while no user exists; after
that it answers 404. Sign-in locks an account for five minutes after five
failed attempts and answers 423 while it is locked. Sign-in and first run are
rate limited per client address. Neither needs a CSRF token: there is no session
yet, and both accept only a JSON body, which a cross-site form cannot send.
"""

import math

from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import SYSTEM, as_role
from app.api.deps import (
    DbDep,
    Services,
    ServicesDep,
    SessionDep,
    client_ip,
    enforce_rate_limit,
    record_audit,
)
from app.api.problems import ProblemError
from app.api.v1.schemas import (
    Credentials,
    Me,
    NewAccount,
    SetupState,
    SignedIn,
    UserOut,
)
from app.db.models import AppUser
from app.repos.sessions import SessionRepository
from app.repos.users import UserRepository
from app.security.sessions import (
    LOCKOUT,
    MAX_FAILED_LOGINS,
    clear_session_cookie,
    set_session_cookie,
)
from app.security.tokens import CSRF_TOKEN_BYTES, new_secret, sha256_hex

router = APIRouter(prefix="/auth", tags=["auth"])


def sign_in_failed() -> ProblemError:
    """The same answer, after the same Argon2 work, for an unknown address, a
    disabled account and a wrong password. The lockout of the plan still tells
    them apart: only an existing account answers 423 after five failures."""
    return ProblemError(
        401, "Sign-in failed", "The e-mail address or the password is wrong."
    )


async def start_session(
    services: Services, db: AsyncSession, request: Request, user: AppUser
) -> tuple[str, str]:
    """A new session for the user: the cookie secret and the CSRF token."""
    now = services.clock.now()
    secret = new_secret()
    csrf_token = new_secret(CSRF_TOKEN_BYTES)
    sessions = SessionRepository(db, services.policy)
    await sessions.purge_expired(SYSTEM, now)
    await sessions.create(
        SYSTEM,
        id_hash=sha256_hex(secret),
        user_id=user.id,
        csrf_token=csrf_token,
        now=now,
        ip=client_ip(request),
    )
    return secret, csrf_token


def locked_problem(seconds: float) -> ProblemError:
    return ProblemError(
        423,
        "Account locked",
        "Too many failed sign-ins. Try again later.",
        headers={"Retry-After": str(max(1, math.ceil(seconds)))},
    )


@router.get("/setup-state")
async def setup_state(services: ServicesDep, db: DbDep) -> SetupState:
    """Whether the first-run page is open (no user exists yet)."""
    users = UserRepository(db, services.policy)
    return SetupState(needs_first_run=await users.count(SYSTEM) == 0)


@router.get("/first-run")
async def first_run_state(services: ServicesDep, db: DbDep) -> SetupState:
    """200 while no user exists, 404 once one does."""
    users = UserRepository(db, services.policy)
    if await users.count(SYSTEM) > 0:
        raise ProblemError(404, "Not Found")
    return SetupState(needs_first_run=True)


@router.post("/first-run", status_code=201)
async def first_run(
    body: NewAccount,
    request: Request,
    response: Response,
    services: ServicesDep,
    db: DbDep,
) -> SignedIn:
    """Create the first admin and sign in; 404 once any user exists."""
    enforce_rate_limit(services.login_limiter, client_ip(request) or "unknown")
    users = UserRepository(db, services.policy)
    await users.lock_bootstrap(SYSTEM)
    if await users.count(SYSTEM) > 0:
        raise ProblemError(404, "Not Found")
    user = await users.create(
        SYSTEM,
        email=body.email,
        password_hash=await services.passwords.hash(body.password),
        role="admin",
        now=services.clock.now(),
    )
    secret, csrf_token = await start_session(services, db, request, user)
    await record_audit(
        services,
        db,
        request,
        f"user:{user.id}",
        "auth.first_run",
        target_kind="user",
        target_id=user.id,
    )
    await db.commit()
    set_session_cookie(response, secret)
    return SignedIn(user=UserOut.model_validate(user), csrf_token=csrf_token)


@router.post("/login")
async def login(
    body: Credentials,
    request: Request,
    response: Response,
    services: ServicesDep,
    db: DbDep,
) -> SignedIn:
    """Sign in. 401 for a wrong address or password, 423 while locked."""
    enforce_rate_limit(services.login_limiter, client_ip(request) or "unknown")
    now = services.clock.now()
    users = UserRepository(db, services.policy)
    user = await users.find_by_email(SYSTEM, body.email, for_update=True)
    if user is None or user.disabled:
        await services.passwords.spend_verify_time(body.password)
        reason = "unknown" if user is None else "disabled"
        target = None if user is None else user.id
        await record_audit(
            services,
            db,
            request,
            "anonymous",
            "auth.login_failed",
            target_kind="user",
            target_id=target,
            reason=reason,
        )
        await db.commit()
        raise sign_in_failed()
    if user.locked_until is not None and user.locked_until > now:
        raise locked_problem((user.locked_until - now).total_seconds())
    if not await services.passwords.verify(user.password_hash, body.password):
        failed = user.failed_logins + 1
        if failed >= MAX_FAILED_LOGINS:
            await users.update(
                SYSTEM, user, failed_logins=0, locked_until=now + LOCKOUT
            )
            action = "auth.locked"
        else:
            await users.update(SYSTEM, user, failed_logins=failed)
            action = "auth.login_failed"
        await record_audit(
            services,
            db,
            request,
            "anonymous",
            action,
            target_kind="user",
            target_id=user.id,
            reason="password",
        )
        await db.commit()
        if failed >= MAX_FAILED_LOGINS:
            raise locked_problem(LOCKOUT.total_seconds())
        raise sign_in_failed()
    changes: dict[str, object] = {"failed_logins": 0, "locked_until": None}
    if services.passwords.needs_rehash(user.password_hash):
        changes["password_hash"] = await services.passwords.hash(body.password)
    await users.update(SYSTEM, user, **changes)
    secret, csrf_token = await start_session(services, db, request, user)
    await record_audit(
        services,
        db,
        request,
        f"user:{user.id}",
        "auth.login",
        target_kind="user",
        target_id=user.id,
    )
    await db.commit()
    set_session_cookie(response, secret)
    return SignedIn(user=UserOut.model_validate(user), csrf_token=csrf_token)


@router.post("/logout", status_code=204)
async def logout(
    context: SessionDep,
    request: Request,
    response: Response,
    services: ServicesDep,
    db: DbDep,
) -> None:
    """End this session."""
    sessions = SessionRepository(db, services.policy)
    await sessions.delete(context.principal, context.session.id_hash)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "auth.logout",
        target_kind="user",
        target_id=context.user.id,
    )
    await db.commit()
    clear_session_cookie(response)


@router.get("/me")
async def me(context: SessionDep) -> Me:
    """The signed-in user and the CSRF token of this session."""
    return Me(
        id=context.user.id,
        email=context.user.email,
        role=as_role(context.user.role),
        csrf_token=context.session.csrf_token,
    )
