"""Deleting a client removes every row that belongs to it (legal D-3).

The map in app/repos/client_delete.py must name every table that references a
client, directly or through another table; this test reads the foreign keys
of the models, so a table added in a later phase fails here until it joins the
map.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import Table, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.base import Base
from app.db.models import (
    AppUser,
    AuditEvent,
    Channel,
    ChannelRule,
    Client,
    Flip,
    Job,
    JobResult,
    JobStateRecord,
    Notification,
    Occurrence,
    RawMessage,
)
from app.ingest.results import ParsedResult
from app.ingest.store import record_result, store_raw
from app.repos.client_delete import CLIENT_DELETE_MAP, SCOPED_TABLES
from app.repos.inboxes import InboxRepository
from app.repos.notifications import (
    ChannelRepository,
    ChannelRuleRepository,
    NotificationRepository,
)
from app.security.crypto import SecretBox
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    TEST_FERNET_KEY,
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
    """Every table whose foreign keys lead to a client, and the tables that
    name a client or job without one (channel_rule.scope_id)."""
    assert set(map_tables()) == tables_holding_client_rows() | SCOPED_TABLES
    assert len(map_tables()) == len(set(map_tables()))
    assert {"notification", "channel_rule"} <= set(map_tables())
    assert "channel" not in map_tables()


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


async def add_evaluation(
    engine: AsyncEngine,
    client_id: uuid.UUID,
    job_id: uuid.UUID,
    other_client: uuid.UUID,
    other_job: uuid.UUID,
) -> uuid.UUID:
    """Evaluator rows around one client; returns the flip that must stay.

    An occurrence of the client's job decided by one of its results, the
    job's job_state row, a flip of the job, and a flip made while the other
    client's job still belonged to this client (a moved job).
    """
    night = datetime(2027, 1, 3, 23, tzinfo=UTC)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        query = select(JobResult.id).where(JobResult.job_id == job_id).limit(1)
        result_id = (await db.execute(query)).scalar_one()
        db.add(
            Occurrence(
                job_id=job_id,
                scheduled_for=night,
                deadline=night + timedelta(hours=8),
                state="verified",
                result_id=result_id,
                evaluated_at=RECEIVED,
            )
        )
        db.add(
            JobStateRecord(
                job_id=job_id,
                state="ok",
                since=RECEIVED,
                evaluated_at=RECEIVED,
                job_updated_at=RECEIVED,
            )
        )
        flips = [
            Flip(
                job_id=job,
                client_id=client,
                from_state="unknown",
                to_state="ok",
                reason="The run due 2027-01-03T23:00:00Z was verified",
                at=RECEIVED,
            )
            for job, client in (
                (job_id, client_id),
                (other_job, client_id),
                (other_job, other_client),
            )
        ]
        db.add_all(flips)
        await db.commit()
    return flips[-1].id


async def add_notifications(
    engine: AsyncEngine,
    client_id: uuid.UUID,
    job_id: uuid.UUID,
    other_client: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Notification rows around one client; returns both channels.

    One e-mail channel with a rule for every job, one for the client, one for
    its job and one for the other client, and one webhook channel (C9-I) with
    a rule for the deleted client's job; a notification for every flip and a
    digest (it names no client) on each.
    """
    policy = AllowAllPolicy()
    box = SecretBox(TEST_FERNET_KEY)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        channel = await ChannelRepository(db, policy).create(
            SYSTEM, kind="email", label="Ops mail", now=RECEIVED, config={}
        )
        # A channel of an HTTP kind (C9-I), its URL the stored secret: its
        # rows follow the same map.
        hook = await ChannelRepository(db, policy).create(
            SYSTEM,
            kind="webhook",
            label="Ops hook",
            now=RECEIVED,
            config={"url_set": True, "url_host": "127.0.0.1"},
            secret_enc=box.encrypt("http://127.0.0.1:9/services/T000/B000/x"),
        )
        rules = ChannelRuleRepository(db, policy)
        for scope, scope_id in (
            ("all", None),
            ("client", client_id),
            ("job", job_id),
            ("client", other_client),
        ):
            await rules.create(
                SYSTEM,
                channel_id=channel.id,
                scope=scope,
                scope_id=scope_id,
                events=["missed"],
                now=RECEIVED,
            )
        flips = (await db.scalars(select(Flip.id))).all()
        rows: list[dict[str, Any]] = [
            {"flip_id": flip_id, "event": "missed"} for flip_id in flips
        ]
        rows.append({"digest_day": RECEIVED.date(), "event": "digest"})
        common = {"channel_id": channel.id, "created_at": RECEIVED}
        rows = [row | common | {"next_attempt_at": RECEIVED} for row in rows]
        assert await NotificationRepository(db, policy).queue(SYSTEM, rows) == 4
        # The webhook channel hears of the same flips and gets the digest,
        # and one rule scoped to the deleted client's job.
        await rules.create(
            SYSTEM,
            channel_id=hook.id,
            scope="job",
            scope_id=job_id,
            events=["missed"],
            now=RECEIVED,
        )
        for row in rows:
            row["channel_id"] = hook.id
        assert await NotificationRepository(db, policy).queue(SYSTEM, rows) == 4
        await db.commit()
    return channel.id, hook.id


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
    kept_flip = await add_evaluation(
        db_engine,
        dental_id,
        uuid.UUID(jobs[0]["id"]),
        uuid.UUID(freight["id"]),
        uuid.UUID(kept_job["id"]),
    )
    channel_id, hook_id = await add_notifications(
        db_engine, dental_id, uuid.UUID(jobs[0]["id"]), uuid.UUID(freight["id"])
    )
    before = await rows_of(db_engine, dental_id)
    assert before == {
        "notification": 4,
        "channel_rule": 3,
        "flip": 2,
        "occurrence": 1,
        "job_state": 1,
        "job_result": 3,
        "raw_message": 1,
        "job": 2,
        "client": 1,
    }

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
        "notification": 0,
        "channel_rule": 0,
        "flip": 0,
        "occurrence": 0,
        "job_state": 0,
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
        # The other client's own flip of its job stays; no evaluator row of the
        # deleted client is left.
        kept = (await connection.execute(select(Flip.id))).scalars().all()
        assert kept == [kept_flip]
        for table in (Occurrence, JobStateRecord):
            query = select(func.count()).select_from(table)
            assert (await connection.execute(query)).scalar_one() == 0
        # The other client's notification and the digest stay; so do the
        # channel, its rule for every job and its rule for the other client.
        query = select(Notification.flip_id, Notification.event)
        left = set((await connection.execute(query)).all())
        assert left == {(kept_flip, "missed"), (None, "digest")}
        query = select(ChannelRule.scope, ChannelRule.scope_id)
        rules = set((await connection.execute(query)).all())
        assert rules == {("all", None), ("client", uuid.UUID(freight["id"]))}
        query = select(Channel.id)
        assert set((await connection.execute(query)).scalars().all()) == {
            channel_id,
            hook_id,
        }
        # The webhook channel kept its stored secret and its answer form.
        query = select(Channel.config, Channel.secret_enc).where(Channel.id == hook_id)
        config, secret = (await connection.execute(query)).one()
        assert config == {"url_set": True, "url_host": "127.0.0.1"}
        assert secret is not None and "services" not in secret
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
