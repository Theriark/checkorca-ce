"""Development seed accounts (dev-work-plan C1-B item 5).

With DEV_SEED=1 the web process ensures one admin and one technician before the
HTTP port opens, so nobody can take over the first-run page of a fresh
Development or Stage site (it-input). DEV_SEED_ACCOUNTS lists the admin, then
the technician; their passwords come from DEV_SEED_PASSWORD_ADMIN and
DEV_SEED_PASSWORD_TECHNICIAN. "Ensure" means: create the account, or bring an
existing one back to the configured role and password, enabled and unlocked.

The seed refuses unless the BASE_URL host starts with ce-dev- or ce-stg- or is
localhost, and it logs only that the accounts are ensured: never an address or
a password.
"""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.access import SYSTEM, AccessPolicy, AllowAllPolicy, Role
from app.clock import Clock, SystemClock
from app.db.engine import make_engine
from app.ext.audit import AuditRecord, AuditSink, DatabaseAuditSink
from app.repos.sessions import SessionRepository
from app.repos.users import UserRepository, normalise_email
from app.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordService,
)
from app.settings import Settings

logger = logging.getLogger(__name__)

SEED_HOST_PREFIXES = ("ce-dev-", "ce-stg-")
LOCAL_HOST = "localhost"


class SeedError(RuntimeError):
    """The seed is switched on but must not or cannot run."""


@dataclass(frozen=True)
class SeedAccount:
    email: str
    role: Role
    password: str = field(repr=False)


def check_seed_host(base_url: str) -> None:
    """Refuse every host but ce-dev-*, ce-stg-* and localhost."""
    host = (urlsplit(base_url).hostname or "").lower()
    if host == LOCAL_HOST or host.startswith(SEED_HOST_PREFIXES):
        return
    raise SeedError(
        "DEV_SEED=1 is refused: the BASE_URL host must start with ce-dev- or "
        "ce-stg- or be localhost"
    )


def seed_accounts(settings: Settings) -> list[SeedAccount]:
    """The two accounts of the settings; SeedError when anything is missing."""
    emails = [part for part in settings.dev_seed_accounts.split(",") if part.strip()]
    if len(emails) != 2:
        raise SeedError(
            "DEV_SEED_ACCOUNTS must list two e-mail addresses: the admin, "
            "then the technician"
        )
    specs: list[tuple[str, Role, str, SecretStr | None]] = [
        (
            emails[0],
            "admin",
            "DEV_SEED_PASSWORD_ADMIN",
            settings.dev_seed_password_admin,
        ),
        (
            emails[1],
            "technician",
            "DEV_SEED_PASSWORD_TECHNICIAN",
            settings.dev_seed_password_technician,
        ),
    ]
    accounts: list[SeedAccount] = []
    for email, role, name, secret in specs:
        password = "" if secret is None else secret.get_secret_value()
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise SeedError(
                f"{name} must be set, {MIN_PASSWORD_LENGTH} to "
                f"{MAX_PASSWORD_LENGTH} characters"
            )
        try:
            address = normalise_email(email)
        except ValueError:
            raise SeedError(
                "DEV_SEED_ACCOUNTS holds a value that is not an e-mail address"
            ) from None
        accounts.append(SeedAccount(email=address, role=role, password=password))
    return accounts


async def ensure_accounts(
    db: AsyncSession,
    accounts: list[SeedAccount],
    passwords: PasswordService,
    clock: Clock,
    policy: AccessPolicy,
    audit: AuditSink,
) -> None:
    """Create or repair each account in one transaction."""
    users = UserRepository(db, policy)
    await users.lock_bootstrap(SYSTEM)
    for account in accounts:
        now = clock.now()
        user = await users.find_by_email(SYSTEM, account.email, for_update=True)
        if user is None:
            user = await users.create(
                SYSTEM,
                email=account.email,
                password_hash=await passwords.hash(account.password),
                role=account.role,
                now=now,
            )
            action = "seed.create"
        else:
            changes: dict[str, object] = {}
            if user.role != account.role:
                changes["role"] = account.role
            if user.disabled:
                changes["disabled"] = False
            if user.failed_logins or user.locked_until is not None:
                changes["failed_logins"] = 0
                changes["locked_until"] = None
            if not await passwords.verify(user.password_hash, account.password):
                changes["password_hash"] = await passwords.hash(account.password)
                sessions = SessionRepository(db, policy)
                await sessions.delete_for_user(SYSTEM, user.id)
            if not changes:
                continue
            await users.update(SYSTEM, user, **changes)
            action = "seed.update"
        await audit.record(
            db,
            AuditRecord(
                at=now,
                actor="system",
                action=action,
                target_kind="user",
                target_id=str(user.id),
                details={"role": account.role},
            ),
        )
    await db.commit()


async def ensure_seed_accounts(
    settings: Settings,
    clock: Clock | None = None,
    policy: AccessPolicy | None = None,
) -> None:
    """Check the host and the settings, then ensure the accounts."""
    check_seed_host(settings.base_url)
    accounts = seed_accounts(settings)
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            await ensure_accounts(
                db,
                accounts,
                PasswordService(),
                clock or SystemClock(),
                policy or AllowAllPolicy(),
                DatabaseAuditSink(),
            )
    finally:
        await engine.dispose()
    logger.info("seed: development accounts ensured", extra={"accounts": len(accounts)})
