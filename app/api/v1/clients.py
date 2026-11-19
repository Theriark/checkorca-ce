"""clients: list, create, get, change, archive and delete clients.

Admins and technicians alike (only users, tokens and settings are admin only);
the list and get routes also take an API token of scope read. DELETE needs the
client's name typed again (confirm_name), removes every row of the client in
one transaction (app/repos/client_delete.py) and audits only the client's id
and the user (legal D-3).
"""

import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import Principal
from app.api.deps import (
    DbDep,
    ReaderDep,
    Services,
    ServicesDep,
    SessionContext,
    SessionDep,
    record_audit,
)
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_cursor,
    encode_cursor,
)
from app.api.problems import ProblemError
from app.api.v1.job_schemas import ClientOut, ClientPage, ClientPatch, NewClient
from app.db.models import NAME_LENGTH, Client
from app.repos.clients import ClientRepository
from app.repos.jobs import JobRepository, JobState, job_state, worst_state

router = APIRouter(prefix="/clients", tags=["clients"])

SearchQuery = Annotated[str | None, Query(max_length=NAME_LENGTH)]


def client_not_found() -> ProblemError:
    return ProblemError(404, "Client not found")


def name_taken() -> ProblemError:
    return ProblemError(409, "Client name taken", "Another client has this name.")


def parse_name_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    values = decode_cursor(cursor, ("name_key", "id"))
    try:
        return values["name_key"], uuid.UUID(values["id"])
    except ValueError:
        raise ProblemError(
            400, "Invalid cursor", "Use next_cursor as returned."
        ) from None


async def describe(
    services: Services,
    db: AsyncSession,
    principal: Principal,
    clients: list[Client],
    now: datetime,
) -> list[ClientOut]:
    """The clients with the counts of their jobs by state (one query)."""
    jobs = JobRepository(db, services.policy)
    found = await jobs.for_clients(principal, [client.id for client in clients])
    states: dict[uuid.UUID, list[JobState]] = defaultdict(list)
    for job in found:
        states[job.client_id].append(job_state(job, now))
    return [
        ClientOut(
            id=client.id,
            name=client.name,
            notes=client.notes,
            aliases=list(client.aliases),
            archived=client.archived,
            created_at=client.created_at,
            job_count=len(states[client.id]),
            status_counts=dict(Counter(states[client.id])),
            worst_state=worst_state(states[client.id]),
        )
        for client in clients
    ]


@router.get("")
async def list_clients(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    q: SearchQuery = None,
    archived: bool = False,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> ClientPage:
    """Clients ordered by name; archived true lists the archived ones."""
    after = None if cursor is None else parse_name_cursor(cursor)
    clients = ClientRepository(db, services.policy)
    found = await clients.page(
        principal, q=q, archived=archived, after=after, limit=limit + 1
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_cursor({"name_key": last.name_key, "id": str(last.id)})
    return ClientPage(
        items=await describe(services, db, principal, items, services.clock.now()),
        next_cursor=next_cursor,
    )


@router.post("", status_code=201)
async def create_client(
    body: NewClient,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> ClientOut:
    """Create a client; 409 when another client has the name."""
    clients = ClientRepository(db, services.policy)
    if await clients.find_by_name(context.principal, body.name) is not None:
        raise name_taken()
    now = services.clock.now()
    try:
        client = await clients.create(
            context.principal,
            name=body.name,
            notes=body.notes,
            aliases=body.aliases,
            now=now,
        )
    except IntegrityError:
        # A concurrent request took the name after the check.
        await db.rollback()
        raise name_taken() from None
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "client.create",
        target_kind="client",
        target_id=client.id,
    )
    await db.commit()
    return (await describe(services, db, context.principal, [client], now))[0]


@router.get("/{client_id}")
async def get_client(
    client_id: uuid.UUID, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> ClientOut:
    client = await ClientRepository(db, services.policy).get(principal, client_id)
    if client is None:
        raise client_not_found()
    now = services.clock.now()
    return (await describe(services, db, principal, [client], now))[0]


async def change_client(
    client_id: uuid.UUID,
    changes: dict[str, object],
    action: str,
    context: SessionContext,
    request: Request,
    services: Services,
    db: AsyncSession,
) -> ClientOut:
    """Apply the changes and audit the names of the changed fields."""
    clients = ClientRepository(db, services.policy)
    client = await clients.get(context.principal, client_id, for_update=True)
    if client is None:
        raise client_not_found()
    changes = {
        field: value
        for field, value in changes.items()
        if getattr(client, field) != value
    }
    now = services.clock.now()
    if not changes:
        # Ends the transaction and its row lock; nothing was written.
        await db.commit()
        return (await describe(services, db, context.principal, [client], now))[0]
    name = changes.get("name")
    if isinstance(name, str):
        other = await clients.find_by_name(context.principal, name)
        if other is not None and other.id != client.id:
            raise name_taken()
    try:
        await clients.update(context.principal, client, **changes)
    except IntegrityError:
        await db.rollback()
        raise name_taken() from None
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        action,
        target_kind="client",
        target_id=client.id,
        fields=",".join(sorted(changes)),
    )
    await db.commit()
    return (await describe(services, db, context.principal, [client], now))[0]


@router.patch("/{client_id}")
async def update_client(
    client_id: uuid.UUID,
    body: ClientPatch,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> ClientOut:
    """Change the name, notes, aliases, or archive and restore."""
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    return await change_client(
        client_id, changes, "client.update", context, request, services, db
    )


@router.post("/{client_id}/archive")
async def archive_client(
    client_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> ClientOut:
    """Archive a client: hidden from the default list, its jobs not counted.
    PATCH archived false restores it."""
    return await change_client(
        client_id,
        {"archived": True},
        "client.archive",
        context,
        request,
        services,
        db,
    )


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: uuid.UUID,
    confirm_name: Annotated[str, Query(min_length=1, max_length=NAME_LENGTH)],
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> None:
    """Delete a client and everything recorded for it, for good.

    confirm_name must equal the client's name; 409 otherwise.
    """
    clients = ClientRepository(db, services.policy)
    client = await clients.get(context.principal, client_id, for_update=True)
    if client is None:
        raise client_not_found()
    if " ".join(confirm_name.split()) != client.name:
        raise ProblemError(
            409,
            "Name does not match",
            "Type the client's name exactly as shown to delete it.",
        )
    await clients.delete(context.principal, client)
    # Only the id and the user: the deleted client's name is not kept (D-3).
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "client.delete",
        target_kind="client",
        target_id=client_id,
    )
    await db.commit()
