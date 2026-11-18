"""users: list, create, get, change and delete accounts (admin only).

There is always at least one enabled admin: demoting, disabling or deleting the
last one answers 409. An admin cannot delete their own account. A new password
or disabling an account ends the user's other sessions.
"""

import uuid

from fastapi import APIRouter, Request

from app.api.deps import AdminDep, DbDep, ServicesDep, SessionContext, record_audit
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_cursor,
    encode_cursor,
)
from app.api.problems import ProblemError
from app.api.v1.schemas import NewUser, UserOut, UserPage, UserPatch
from app.db.models import AppUser
from app.repos.sessions import SessionRepository
from app.repos.users import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


def user_not_found() -> ProblemError:
    return ProblemError(404, "User not found")


def last_admin() -> ProblemError:
    return ProblemError(
        409, "Last admin", "At least one enabled admin account must remain."
    )


@router.get("")
async def list_users(
    context: AdminDep,
    services: ServicesDep,
    db: DbDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> UserPage:
    """Users ordered by e-mail address."""
    after = None if cursor is None else decode_cursor(cursor, ("email",))["email"]
    users = UserRepository(db, services.policy)
    found = await users.page(context.principal, after_email=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        next_cursor = encode_cursor({"email": items[-1].email})
    return UserPage(
        items=[UserOut.model_validate(user) for user in items],
        next_cursor=next_cursor,
    )


@router.post("", status_code=201)
async def create_user(
    body: NewUser,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> UserOut:
    """Create an account; 409 when the address is taken."""
    users = UserRepository(db, services.policy)
    if await users.find_by_email(context.principal, body.email) is not None:
        raise ProblemError(409, "E-mail address taken")
    user = await users.create(
        context.principal,
        email=body.email,
        password_hash=await services.passwords.hash(body.password),
        role=body.role,
        now=services.clock.now(),
    )
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "user.create",
        target_kind="user",
        target_id=user.id,
        role=body.role,
    )
    await db.commit()
    return UserOut.model_validate(user)


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID, context: AdminDep, services: ServicesDep, db: DbDep
) -> UserOut:
    user = await UserRepository(db, services.policy).get(context.principal, user_id)
    if user is None:
        raise user_not_found()
    return UserOut.model_validate(user)


async def keeps_an_admin(
    users: UserRepository, context: SessionContext, user: AppUser
) -> bool:
    """False when user is the only enabled admin."""
    if user.role != "admin" or user.disabled:
        return True
    admins = await users.lock_active_admins(context.principal)
    return any(admin_id != user.id for admin_id in admins)


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> UserOut:
    """Change the role, disable or enable, or set a new password."""
    users = UserRepository(db, services.policy)
    user = await users.get(context.principal, user_id)
    if user is None:
        raise user_not_found()
    changes: dict[str, object] = {}
    if body.role is not None and body.role != user.role:
        changes["role"] = body.role
    if body.disabled is not None and body.disabled != user.disabled:
        changes["disabled"] = body.disabled
    demoted = changes.get("role") == "technician" or changes.get("disabled") is True
    if demoted and not await keeps_an_admin(users, context, user):
        raise last_admin()
    fields = sorted(changes)
    if body.password is not None:
        fields.append("password")
        changes["password_hash"] = await services.passwords.hash(body.password)
        changes["failed_logins"] = 0
        changes["locked_until"] = None
    if changes:
        await users.update(context.principal, user, **changes)
    if body.password is not None or changes.get("disabled") is True:
        # The admin's own session survives a change of their own password.
        keep = context.session.id_hash if user.id == context.user.id else None
        sessions = SessionRepository(db, services.policy)
        await sessions.delete_for_user(context.principal, user.id, keep=keep)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "user.update",
        target_kind="user",
        target_id=user.id,
        fields=",".join(fields),
    )
    await db.commit()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> None:
    """Delete an account and its sessions; its tokens stay, without a creator."""
    users = UserRepository(db, services.policy)
    user = await users.get(context.principal, user_id)
    if user is None:
        raise user_not_found()
    if user.id == context.user.id:
        raise ProblemError(409, "Own account", "An admin cannot delete themselves.")
    if not await keeps_an_admin(users, context, user):
        raise last_admin()
    await users.delete(context.principal, user)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "user.delete",
        target_kind="user",
        target_id=user_id,
    )
    await db.commit()
