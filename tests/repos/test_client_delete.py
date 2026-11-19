"""Deleting a client removes every row that belongs to it (legal D-3).

The map in app/repos/client_delete.py must name every table that references a
client, directly or through another table; this test reads the foreign keys
of the models, so a table added in a later phase fails here until it joins the
map.
"""

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.models import AppUser, AuditEvent, Client, Job
from app.repos.client_delete import CLIENT_DELETE_MAP
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


async def rows_of(engine: AsyncEngine, client_id: uuid.UUID) -> dict[str, int]:
    """For each table of the map, the rows that belong to the client."""
    counts: dict[str, int] = {}
    async with engine.connect() as connection:
        for step in CLIENT_DELETE_MAP:
            query = (
                select(func.count())
                .select_from(step.model)
                .where(step.rows(client_id))
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
    for name in ("Nightly server backup", "Weekly image backup"):
        await make_job(client, csrf, dental["id"], name)
    kept_job = await make_job(client, csrf, freight["id"], "Nightly server backup")
    dental_id = uuid.UUID(dental["id"])
    before = await rows_of(db_engine, dental_id)
    assert before == {"job": 2, "client": 1}

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
    assert await rows_of(db_engine, dental_id) == {"job": 0, "client": 0}
    assert (await client.get(f"/api/v1/clients/{dental['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{kept_job['id']}")).status_code == 200

    async with db_engine.connect() as connection:
        remaining = (await connection.execute(select(Job.client_id))).scalars()
        assert set(remaining) == {uuid.UUID(freight["id"])}
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
