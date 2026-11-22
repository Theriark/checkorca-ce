"""settings: the digest settings of the Settings chapter (phase C9-B).

Admins only (signed in; X-CSRF-Token to change). digest_time_local (HH:MM)
and digest_timezone decide when the daily digest goes out and which local day
the dashboard and the exports count by; reminder_24h (off by default) sends a
reminder when a job is still failing or missed a day after its notification.
"""

from datetime import time

from fastapi import APIRouter, Request

from app.api.deps import AdminDep, DbDep, ServicesDep, record_audit
from app.api.v1.notify_schemas import DigestSettingsOut, DigestSettingsPatch
from app.db.models import AppSettings
from app.repos.settings import SettingsRepository

router = APIRouter(prefix="/settings", tags=["settings"])


def settings_out(row: AppSettings) -> DigestSettingsOut:
    return DigestSettingsOut(
        digest_time_local=row.digest_time_local.strftime("%H:%M"),
        digest_timezone=row.digest_timezone,
        reminder_24h=row.reminder_24h,
    )


@router.get("")
async def get_settings(
    context: AdminDep, services: ServicesDep, db: DbDep
) -> DigestSettingsOut:
    repository = SettingsRepository(db, services.policy, services.secret_box)
    return settings_out(await repository.get(context.principal))


@router.patch("")
async def update_settings(
    body: DigestSettingsPatch,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> DigestSettingsOut:
    """Change the fields sent (at least one). A new digest time or zone
    counts from the next digest: a day's digest is sent once."""
    repository = SettingsRepository(db, services.policy, services.secret_box)
    row = await repository.get(context.principal, for_update=True)
    changes: dict[str, object] = {}
    if body.digest_time_local is not None:
        hours, minutes = body.digest_time_local.split(":")
        changes["digest_time_local"] = time(int(hours), int(minutes))
    if body.digest_timezone is not None:
        changes["digest_timezone"] = body.digest_timezone
    if body.reminder_24h is not None:
        changes["reminder_24h"] = body.reminder_24h
    changes = {
        field: value for field, value in changes.items() if getattr(row, field) != value
    }
    if changes:
        await repository.update_digest(context.principal, row, **changes)
        await record_audit(
            services,
            db,
            request,
            context.principal.actor,
            "settings.update",
            target_kind="settings",
            fields=",".join(sorted(changes)),
        )
    await db.commit()
    return settings_out(row)
