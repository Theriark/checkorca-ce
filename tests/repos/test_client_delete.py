"""Deleting a client removes every row that belongs to it (legal D-3).

The map in app/repos/client_delete.py must name every table that references a
client, directly or through another table; this test reads the foreign keys
of the models, so a table added in a later phase fails here until it joins the
map.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import Table, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.base import Base
from app.db.models import AppUser, AuditEvent, Client, Job, JobResult, RawMessage
from app.ingest.results import ParsedResult
from app.ingest.store import record_result, store_raw
from app.repos.client_delete import CLIENT_DELETE_MAP
from app.repos.inboxes import InboxRepository
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    make_client,
    make_job,
    sign_in,
)

DENTAL, FREIGHT, _ = CLIENT_NAMES
RECEIVED = datetime(2027, 1, 4, 6, 30, tzinfo=UTC)


def tables_holding_client_rows() -> set[str]:
    """client and every table whose foreign keys lead to it."""
    found = {"client"}
    changed = True
    while changed:
        changed = False
        for table in Base.metadata.sorted_tables:
            if table.name in found:
                continue
            if any(key.column.table.name in found for key in table.foreign_keys):
                found.add(table.name)
                changed = True
    return found


def map_tables() -> list[str]:
    return [step.model.__table__.name for step in CLIENT_DELETE_MAP]


def test_the_map_covers_every_table_that_references_a_client() -> None:
    assert set(map_tables()) == tables_holding_client_rows()
    assert len(map_tables()) == len(set(map_tables()))


def test_a_table_is_deleted_before_the_tables_it_references() -> None:
    order = map_tables()
    for step in CLIENT_DELETE_MAP:
        table = step.model.__table__
        assert isinstance(table, Table)
        for key in table.foreign_keys:
            referenced = key.column.table.name
            if referenced in order and referenced != table.name:
                assert order.index(table.name) < order.index(referenced)


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def add_evidence(
    engine: AsyncEngine, client_id: uuid.UUID, job_id: uuid.UUID, other_job: uuid.UUID
) -> uuid.UUID:
    """Ingest rows around one client; returns the message that must stay.

    The client's own message (client_id set) with an unbound result; a shared
    message with one result for the client's job and one for another client's
    job; and a ping result of the client's job without any message.
    """
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    policy = AllowAllPolicy()
    success = ParsedResult(status="success")
    async with sessions() as db:
        inbox, _ = await InboxRepository(db, policy).create(
            SYSTEM, kind="smtp", label="Vendor mail", now=RECEIVED
        )
        own, shared = [
            await store_raw(
                db,
                policy,
                SYSTEM,
                inbox_id=inbox.id,
                raw=f"Subject: {subject}\r\n\r\n{subject}: Success".encode(),
                received_at=RECEIVED,
            )
            for subject in ("own", "shared")
        ]
        bind = update(RawMessage).where(RawMessage.id == own.id)
        await db.execute(bind.values(client_id=client_id))
        for job, message in ((None, own.id), (job_id, shared.id), (job_id, None)):
            await record_result(
                db,
                policy,
                SYSTEM,
                success,
                received_at=RECEIVED,
                job_id=job,
                raw_message_id=message,
            )
        await record_result(
            db,
            policy,
            SYSTEM,
            success,
            received_at=RECEIVED,
            job_id=other_job,
            raw_message_id=shared.id,
        )
        await db.commit()
    return shared.id


async def rows_of(engine: AsyncEngine, client_id: uuid.UUID) -> dict[str, int]:
    """For each table of the map, the rows that belong to the client."""
    counts: dict[str, int] = {}
    async with engine.connect() as connection:
        for step in CLIENT_DELETE_MAP:
            query = (
                select(func.count()).select_from(step.model).where(step.rows(client_id))
            )
            counts[step.model.__table__.name] = int(
                (await connection.execute(query)).scalar_one()
            )
    return counts


async def test_delete_removes_the_client_and_its_rows_only(
    client: httpx.AsyncClient,
    csrf: str,
    admin: AppUser,
    db_engine: AsyncEngine,
) -> None:
    dental: dict[str, Any] = await make_client(client, csrf, DENTAL, notes="Synthetic.")
    freight = await make_client(client, csrf, FREIGHT)
    jobs = [
        await make_job(client, csrf, dental["id"], name)
        for name in ("Nightly server backup", "Weekly image backup")
    ]
    kept_job = await make_job(client, csrf, freight["id"], "Nightly server backup")
    dental_id = uuid.UUID(dental["id"])
    kept_message = await add_evidence(
        db_engine, dental_id, uuid.UUID(jobs[0]["id"]), uuid.UUID(kept_job["id"])
    )
    before = await rows_of(db_engine, dental_id)
    assert before == {"job_result": 3, "raw_message": 1, "job": 2, "client": 1}

    wrong = await client.delete(
        f"/api/v1/clients/{dental['id']}",
        params={"confirm_name": "Fictional Dental"},
        headers={CSRF_HEADER: csrf},
    )
    assert wrong.status_code == 409
    assert await rows_of(db_engine, dental_id) == before

    deleted = await client.delete(
        f"/api/v1/clients/{dental['id']}",
        params={"confirm_name": f"  {DENTAL} "},
        headers={CSRF_HEADER: csrf},
    )
    assert deleted.status_code == 204
    assert await rows_of(db_engine, dental_id) == {
        "job_result": 0,
        "raw_message": 0,
        "job": 0,
        "client": 0,
    }
    assert (await client.get(f"/api/v1/clients/{dental['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{kept_job['id']}")).status_code == 200

    async with db_engine.connect() as connection:
        remaining = (await connection.execute(select(Job.client_id))).scalars()
        assert set(remaining) == {uuid.UUID(freight["id"])}
        # The other client's message and result stay.
        query = select(RawMessage.id, RawMessage.client_id)
        assert (await connection.execute(query)).all() == [(kept_message, None)]
        query = select(JobResult.job_id)
        results = (await connection.execute(query)).scalars().all()
        assert results == [uuid.UUID(kept_job["id"])]
        clients = (await connection.execute(select(Client.name))).scalars()
        assert list(clients) == [FREIGHT]
        query = select(AuditEvent).where(AuditEvent.action == "client.delete")
        audit = (await connection.execute(query)).one()
    # Only the id and the user: no name, notes or counts of the client.
    assert audit.target_kind == "client"
    assert audit.target_id == dental["id"]
    assert audit.actor == f"user:{admin.id}"
    assert audit.details == {}

    again = await client.delete(
        f"/api/v1/clients/{dental['id']}",
        params={"confirm_name": DENTAL},
        headers={CSRF_HEADER: csrf},
    )
    assert again.status_code == 404
