"""inboxes: list, create, get, change and delete inboxes; rotate a webhook
inbox's token.

Admins and technicians alike; the list and get routes also take an API token
of scope read. Secrets are write-only (legal D-6): the IMAP password is
encrypted with FERNET_KEY before it is stored and only secret_set and a masked
hint come back; a webhook inbox's token is shown once, by create and by
rotation, and stored as SHA-256. Audit events name the changed fields, never
their values.
"""

import uuid
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request

from app.api.deps import (
    DbDep,
    ReaderDep,
    Services,
    ServicesDep,
    SessionDep,
    record_audit,
)
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import ProblemError
from app.api.v1.ingest_schemas import (
    ImapOut,
    InboxCreated,
    InboxKind,
    InboxOut,
    InboxPage,
    InboxPatch,
    InboxToken,
    NewInbox,
)
from app.db.models import Inbox
from app.repos.inboxes import InboxRepository
from app.security.crypto import MASK, SecretBox, SecretBoxError, mask_hint

router = APIRouter(prefix="/inboxes", tags=["inboxes"])

KindQuery = Annotated[InboxKind | None, Query()]
# Where the poller sends the stored password. Changing one of them without
# sending the password again would deliver the stored one to a new server.
PASSWORD_TARGET = frozenset({"imap_host", "imap_port", "imap_username", "imap_tls"})


def inbox_not_found() -> ProblemError:
    return ProblemError(404, "Inbox not found")


def secret_hint(box: SecretBox, ciphertext: str | None) -> str | None:
    """The masked hint of a stored password; never the password."""
    if ciphertext is None:
        return None
    try:
        return mask_hint(box.decrypt(ciphertext))
    except SecretBoxError:
        # Encrypted with another key: set, but no hint can be shown.
        return MASK


def inbox_out(services: Services, inbox: Inbox) -> InboxOut:
    settings = services.settings
    address = None
    if inbox.kind == "smtp":
        address = f"{inbox.code}@{settings.inbox_domain}"
    ingest_url = None
    if inbox.kind in ("smtp", "webhook"):
        ingest_url = f"{settings.base_url}/api/v1/ingest/email/{inbox.code}"
    imap = None
    if inbox.kind == "imap":
        imap = ImapOut(
            host=inbox.imap_host,
            port=inbox.imap_port,
            username=inbox.imap_username,
            folder=inbox.imap_folder,
            poll_seconds=inbox.imap_poll_seconds,
            tls=inbox.imap_tls,
            secret_set=inbox.imap_password_enc is not None,
            secret_hint=secret_hint(services.secret_box, inbox.imap_password_enc),
        )
    return InboxOut(
        id=inbox.id,
        kind=cast(InboxKind, inbox.kind),
        label=inbox.label,
        address=address,
        ingest_url=ingest_url,
        imap=imap,
        webhook_token_set=inbox.token_sha256 is not None,
        sender_allowlist=list(inbox.sender_allowlist),
        require_auth_results=inbox.require_auth_results,
        created_at=inbox.created_at,
        updated_at=inbox.updated_at,
        last_message_at=inbox.last_message_at,
    )


@router.get("")
async def list_inboxes(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    kind: KindQuery = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> InboxPage:
    """Inboxes, oldest first."""
    after = None if cursor is None else decode_time_cursor(cursor, "created_at")
    inboxes = InboxRepository(db, services.policy)
    found = await inboxes.page(principal, kind=kind, after=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("created_at", last.created_at, last.id)
    return InboxPage(
        items=[inbox_out(services, inbox) for inbox in items],
        next_cursor=next_cursor,
    )


def imap_columns(services: Services, imap: dict[str, Any]) -> dict[str, Any]:
    """IMAP settings as inbox columns; the password encrypted."""
    columns = {f"imap_{field}": value for field, value in imap.items()}
    password = columns.pop("imap_password", None)
    if password is not None:
        columns["imap_password_enc"] = services.secret_box.encrypt(password)
    return columns


@router.post("", status_code=201)
async def create_inbox(
    body: NewInbox,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> InboxCreated:
    """Create an inbox. A webhook inbox's token is in this answer only."""
    fields: dict[str, Any] = {
        "sender_allowlist": body.sender_allowlist,
        "require_auth_results": body.require_auth_results,
    }
    if body.imap is not None:
        fields |= imap_columns(services, body.imap.model_dump())
    inboxes = InboxRepository(db, services.policy)
    inbox, token = await inboxes.create(
        context.principal,
        kind=body.kind,
        label=body.label,
        now=services.clock.now(),
        **fields,
    )
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "inbox.create",
        target_kind="inbox",
        target_id=inbox.id,
        kind=body.kind,
    )
    await db.commit()
    shown = inbox_out(services, inbox)
    return InboxCreated(**shown.model_dump(), webhook_token=token)


@router.get("/{inbox_id}")
async def get_inbox(
    inbox_id: uuid.UUID, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> InboxOut:
    inbox = await InboxRepository(db, services.policy).get(principal, inbox_id)
    if inbox is None:
        raise inbox_not_found()
    return inbox_out(services, inbox)


@router.patch("/{inbox_id}")
async def update_inbox(
    inbox_id: uuid.UUID,
    body: InboxPatch,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> InboxOut:
    """Change the label, the sender allowlist, the Authentication-Results rule
    or (IMAP inboxes) the IMAP settings. A password sent replaces the stored
    one; none sent keeps it, except that a new host, port, TLS setting or user
    name needs the password again (422)."""
    inboxes = InboxRepository(db, services.policy)
    inbox = await inboxes.get(context.principal, inbox_id, for_update=True)
    if inbox is None:
        raise inbox_not_found()
    changes = body.model_dump(exclude_unset=True, exclude_none=True, exclude={"imap"})
    if body.imap is not None:
        if inbox.kind != "imap":
            raise ProblemError(
                409, "Not an IMAP inbox", "Only an IMAP inbox has IMAP settings."
            )
        imap = body.imap.model_dump(exclude_unset=True, exclude_none=True)
        changes |= imap_columns(services, imap)
    # The password is compared as ciphertext, which always differs: a password
    # sent always counts as a change.
    changes = {
        field: value
        for field, value in changes.items()
        if field == "imap_password_enc" or getattr(inbox, field) != value
    }
    retargeted = PASSWORD_TARGET & set(changes)
    if (
        retargeted
        and inbox.imap_password_enc is not None
        and "imap_password_enc" not in changes
    ):
        raise ProblemError(
            422,
            "IMAP password required",
            "Send the IMAP password again to change the host, port, TLS setting"
            " or user name.",
        )
    if changes:
        await inboxes.update(
            context.principal, inbox, now=services.clock.now(), **changes
        )
        await record_audit(
            services,
            db,
            request,
            context.principal.actor,
            "inbox.update",
            target_kind="inbox",
            target_id=inbox.id,
            fields=",".join(sorted(changes)),
        )
    await db.commit()
    return inbox_out(services, inbox)


@router.post("/{inbox_id}/token")
async def rotate_inbox_token(
    inbox_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> InboxToken:
    """A new token for a webhook inbox, shown once; the old one stops working."""
    inboxes = InboxRepository(db, services.policy)
    inbox = await inboxes.get(context.principal, inbox_id, for_update=True)
    if inbox is None:
        raise inbox_not_found()
    if inbox.kind != "webhook":
        raise ProblemError(
            409, "Not a webhook inbox", "Only a webhook inbox has a token."
        )
    token = await inboxes.rotate_token(
        context.principal, inbox, now=services.clock.now()
    )
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "inbox.token_rotate",
        target_kind="inbox",
        target_id=inbox.id,
    )
    await db.commit()
    return InboxToken(webhook_token=token)


@router.delete("/{inbox_id}", status_code=204)
async def delete_inbox(
    inbox_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> None:
    """Delete an inbox: its address, URL and token stop working at once. Its
    messages stay, without an inbox, until the retention purge."""
    inboxes = InboxRepository(db, services.policy)
    inbox = await inboxes.get(context.principal, inbox_id, for_update=True)
    if inbox is None:
        raise inbox_not_found()
    await inboxes.delete(context.principal, inbox)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "inbox.delete",
        target_kind="inbox",
        target_id=inbox_id,
        kind=inbox.kind,
    )
    await db.commit()
