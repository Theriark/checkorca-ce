"""channels: list, create, get, change, delete and test notification channels;
channels/check-url tries the SSRF guard on a URL (phase C9-B).

Admins create, change, delete and test channels (signed in, X-CSRF-Token);
admins and technicians, or an API token of scope read, list and read them.
The secret is write-only (legal D-6): it is encrypted with FERNET_KEY before
it is stored, and answers carry secret_set and a masked hint only. A kind
whose credential is a URL (slack, teams and webhook, phase C9-I) takes the
URL in config.url: it is stored as the secret, answered as url_set and
url_host only, and its target is checked (app/security/ssrf.py) before the
channel is created or changed and on every send and test. Audit events name
the changed fields, never their values. A channel whose kind is not
registered (a plugin kind of a later edition) can be listed and deleted only.
"""

import uuid
from typing import Any, cast

from fastapi import APIRouter, Request

from app.api.deps import AdminDep, DbDep, ReaderDep, Services, ServicesDep, record_audit
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import FieldProblem, ProblemError
from app.api.v1.notify_schemas import (
    ChannelKindName,
    ChannelOut,
    ChannelPage,
    ChannelPatch,
    ChannelStatus,
    ChannelTestResult,
    NewChannel,
    TargetAllowedBy,
    TargetCheck,
    TargetCheckResult,
)
from app.db.models import Channel
from app.ext.notifications import ChannelConfigError, ChannelKind
from app.notify.delivery import outbound_of, send_message
from app.notify.messages import channel_test_message
from app.repos.notifications import ChannelRepository
from app.security.crypto import MASK, SecretBoxError
from app.security.ssrf import TargetRefused, check_target

router = APIRouter(prefix="/channels", tags=["notifications"])


def channel_not_found() -> ProblemError:
    return ProblemError(404, "Channel not found")


def kind_unavailable(kind: str) -> ProblemError:
    message = f"The channel kind {kind} is not available on this server yet."
    return ProblemError(
        422,
        "Channel kind not available",
        message,
        errors=[FieldProblem(field="body.kind", message=message)],
    )


def channel_locked(channel: Channel) -> ProblemError:
    return ProblemError(
        409,
        "Channel kind not available",
        f"The channel kind {channel.kind} is not available on this server; "
        "the channel can only be deleted.",
    )


def secret_conflict(kind: ChannelKind) -> ProblemError:
    """422: a kind whose credential is a URL takes it in config.url, so it
    has no separate secret to send."""
    message = (
        f"The channel kind {kind.name} takes its URL in config.{kind.url_key}; "
        "send no secret."
    )
    return ProblemError(
        422,
        "Invalid channel settings",
        message,
        errors=[FieldProblem(field="body.secret", message=message)],
    )


async def refuse_target(url: str, services: Services, field: str) -> None:
    """422 with the guard's sentence when url may not be called: creating or
    changing a channel of a URL kind checks the target before it is stored
    (the send and the test check it again, on every request)."""
    settings = services.settings
    try:
        await check_target(
            url,
            allow_private=settings.allow_private_targets,
            allowed_hosts=settings.allowed_hosts,
        )
    except TargetRefused as error:
        raise ProblemError(
            422,
            "Target refused",
            str(error),
            errors=[FieldProblem(field=field, message=str(error))],
        ) from None


def config_problem(error: ChannelConfigError) -> ProblemError:
    """A ChannelConfigError as a 422 that names the field."""
    if error.field == "secret":
        field = "body.secret"
    elif error.field:
        field = f"body.config.{error.field}"
    else:
        field = "body.config"
    return ProblemError(
        422,
        "Invalid channel settings",
        error.message,
        errors=[FieldProblem(field=field, message=error.message)],
    )


def channel_out(services: Services, channel: Channel) -> ChannelOut:
    kind = services.channel_kinds.get(channel.kind)
    return ChannelOut(
        id=channel.id,
        kind=cast(ChannelKindName, channel.kind),
        label=channel.label,
        enabled=channel.enabled,
        config=dict(channel.config),
        available=kind is not None,
        secret_label=None if kind is None else kind.secret_label,
        secret_set=channel.secret_enc is not None,
        # The mask only: a relay password is chosen by a person, so even its
        # last characters tell technicians and read tokens too much.
        secret_hint=None if channel.secret_enc is None else MASK,
        last_status=cast(ChannelStatus | None, channel.last_status),
        last_status_at=channel.last_status_at,
        last_error=channel.last_error,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def checked_config(
    kind: ChannelKind, config: dict[str, Any], *, has_secret: bool
) -> dict[str, Any]:
    try:
        return kind.check_config(config, has_secret=has_secret)
    except ChannelConfigError as error:
        raise config_problem(error) from None


async def load_channel(
    services: Services, db: DbDep, context: AdminDep, channel_id: uuid.UUID
) -> Channel:
    """The channel, locked for the change; 404 when there is none."""
    channels = ChannelRepository(db, services.policy)
    channel = await channels.get(context.principal, channel_id, for_update=True)
    if channel is None:
        raise channel_not_found()
    return channel


@router.get("")
async def list_channels(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> ChannelPage:
    """Channels, oldest first."""
    after = None if cursor is None else decode_time_cursor(cursor, "created_at")
    channels = ChannelRepository(db, services.policy)
    found = await channels.page(principal, after=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("created_at", last.created_at, last.id)
    return ChannelPage(
        items=[channel_out(services, channel) for channel in items],
        next_cursor=next_cursor,
    )


def url_credential(kind: ChannelKind, config: dict[str, Any]) -> str | None:
    """The URL a kind with a url_key is sent in its config (None when it sent
    none): it becomes the channel's secret. check_config has validated it by
    the time the caller stores it."""
    if kind.url_key is None:
        return None
    sent = config.get(kind.url_key)
    return sent if isinstance(sent, str) and sent.strip() else None


@router.post("", status_code=201)
async def create_channel(
    body: NewChannel,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> ChannelOut:
    """Create a channel; 422 names an unusable setting. A kind with a URL
    credential (slack, teams, webhook) takes the URL in config.url, stores it
    as its secret and checks the target before the channel exists."""
    kind = services.channel_kinds.get(body.kind)
    if kind is None:
        raise kind_unavailable(body.kind)
    if kind.url_key is not None and body.secret is not None:
        raise secret_conflict(kind)
    secret = body.secret or None or url_credential(kind, body.config)
    config = checked_config(kind, body.config, has_secret=secret is not None)
    if kind.url_key is not None and secret is not None:
        await refuse_target(secret, services, f"body.config.{kind.url_key}")
    channel = await ChannelRepository(db, services.policy).create(
        context.principal,
        kind=body.kind,
        label=body.label,
        now=services.clock.now(),
        enabled=body.enabled,
        config=config,
        secret_enc=None if secret is None else services.secret_box.encrypt(secret),
    )
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "channel.create",
        target_kind="channel",
        target_id=channel.id,
        kind=body.kind,
    )
    await db.commit()
    return channel_out(services, channel)


@router.post("/check-url")
async def check_url(
    body: TargetCheck, context: AdminDep, services: ServicesDep
) -> TargetCheckResult:
    """Whether the server may call the URL (the SSRF guard of the webhook
    kinds and the heartbeat): 422 with the reason when it may not. Only the
    host is resolved; nothing is sent to it."""
    settings = services.settings
    try:
        target = await check_target(
            body.url,
            allow_private=settings.allow_private_targets,
            allowed_hosts=settings.allowed_hosts,
        )
    except TargetRefused as error:
        raise ProblemError(
            422,
            "Target refused",
            str(error),
            errors=[FieldProblem(field="body.url", message=str(error))],
        ) from None
    return TargetCheckResult(
        ok=True,
        host=target.host,
        port=target.port,
        addresses=list(target.addresses),
        allowed_by=cast(TargetAllowedBy, target.allowed_by),
    )


@router.get("/{channel_id}")
async def get_channel(
    channel_id: uuid.UUID, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> ChannelOut:
    channel = await ChannelRepository(db, services.policy).get(principal, channel_id)
    if channel is None:
        raise channel_not_found()
    return channel_out(services, channel)


@router.patch("/{channel_id}")
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelPatch,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> ChannelOut:
    """Change the label, enabled, the settings or the secret (see
    ChannelPatch). A kind with a URL credential takes the new URL in
    config.url, checks its target and stores it as the secret; removing it is
    refused as an e-mail channel without its relay host."""
    channel = await load_channel(services, db, context, channel_id)
    changes: dict[str, Any] = {}
    if body.label is not None and body.label != channel.label:
        changes["label"] = body.label
    if body.enabled is not None and body.enabled != channel.enabled:
        changes["enabled"] = body.enabled
    if body.config is not None or body.secret is not None:
        kind = services.channel_kinds.get(channel.kind)
        if kind is None:
            raise channel_locked(channel)
        if kind.url_key is not None and body.secret is not None:
            raise secret_conflict(kind)
        stored = dict(channel.config)
        merged = dict(stored)
        for key, value in (body.config or {}).items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        sent = url_credential(kind, dict(body.config or {}))
        if kind.url_key is not None and kind.url_key in (body.config or {}):
            # The URL sent replaces the stored one; sending null or an empty
            # URL would remove the channel's target, which is refused.
            has_secret = sent is not None
        else:
            has_secret = (
                channel.secret_enc is not None
                if body.secret is None
                else body.secret != ""
            )
        config = checked_config(kind, merged, has_secret=has_secret)
        moved = sorted(
            key for key in kind.secret_targets if config.get(key) != stored.get(key)
        )
        if moved and channel.secret_enc is not None and body.secret is None:
            message = (
                f"Send the {kind.secret_label.lower()} again to change "
                f"{', '.join(moved)}."
            )
            raise ProblemError(
                422,
                "Secret required",
                message,
                errors=[FieldProblem(field="body.secret", message=message)],
            )
        if config != stored:
            changes["config"] = config
        if body.secret is not None:
            # A secret sent always counts as a change (ciphertext always differs).
            changes["secret_enc"] = (
                None if body.secret == "" else services.secret_box.encrypt(body.secret)
            )
        elif sent is not None:
            # A URL sent always counts as a change, like a secret.
            await refuse_target(sent, services, f"body.config.{kind.url_key}")
            changes["secret_enc"] = services.secret_box.encrypt(sent)
    if changes:
        await ChannelRepository(db, services.policy).update(
            context.principal, channel, now=services.clock.now(), **changes
        )
        fields = sorted("secret" if key == "secret_enc" else key for key in changes)
        await record_audit(
            services,
            db,
            request,
            context.principal.actor,
            "channel.update",
            target_kind="channel",
            target_id=channel.id,
            fields=",".join(fields),
        )
    await db.commit()
    return channel_out(services, channel)


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: uuid.UUID,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> None:
    """Delete a channel with its rules and its notification history."""
    channel = await load_channel(services, db, context, channel_id)
    await ChannelRepository(db, services.policy).delete(context.principal, channel)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "channel.delete",
        target_kind="channel",
        target_id=channel_id,
        kind=channel.kind,
    )
    await db.commit()


@router.post("/{channel_id}/test")
async def test_channel(
    channel_id: uuid.UUID,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> ChannelTestResult:
    """Send a test message now, from this request (up to 90 seconds); ok and
    a readable detail. A failed test is not retried and does not change the
    channel's last status."""
    channels = ChannelRepository(db, services.policy)
    channel = await channels.get(context.principal, channel_id)
    if channel is None:
        raise channel_not_found()
    kind = services.channel_kinds.get(channel.kind)
    if kind is None:
        raise channel_locked(channel)
    error: str | None
    secret = None
    try:
        if channel.secret_enc is not None:
            secret = services.secret_box.decrypt(channel.secret_enc)
    except SecretBoxError:
        error = "The stored secret cannot be decrypted with FERNET_KEY; set it again."
    else:
        message = channel_test_message(
            channel.label, f"{services.settings.base_url}/", services.clock.now()
        )
        outbound = outbound_of(services.settings)
        error = await send_message(kind, channel.config, secret, message, outbound)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "channel.test",
        target_kind="channel",
        target_id=channel.id,
        ok=error is None,
    )
    await db.commit()
    if error is None:
        return ChannelTestResult(ok=True, detail="The test message was delivered.")
    return ChannelTestResult(ok=False, detail=error)
