"""store_raw and record_result: dedupe per inbox, the size cap, compression,
purge_after, result checks and the access policy. Mail is synthetic (R-11)."""

import asyncio
import hashlib
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.access import SYSTEM, AccessDenied, Action, AllowAllPolicy, Principal
from app.db.models import AppSettings, Inbox, JobResult, RawMessage
from app.ingest.results import ParsedResult
from app.ingest.store import (
    MAX_MESSAGE_BYTES,
    MessageTooLarge,
    ResultRejected,
    raw_bytes,
    record_result,
    store_raw,
)
from app.repos.inboxes import InboxRepository
from app.repos.messages import RawMessageRepository

POLICY = AllowAllPolicy()
RECEIVED = datetime(2027, 1, 4, 6, 30, tzinfo=UTC)


def mail(
    body: str = "Job Nightly server backup finished: Success\r\n",
    *,
    message_id: str | None = "<run-1@backup.example.com>",
    date: str = "Mon, 4 Jan 2027 06:29:00 +0000",
    subject: str = "[Success] Nightly server backup",
) -> bytes:
    """A synthetic vendor-style alert mail."""
    lines = [
        "From: Backup Server <backup@example.com>",
        "To: alerts@example.com",
        f"Subject: {subject}",
        f"Date: {date}",
    ]
    if message_id is not None:
        lines.append(f"Message-ID: {message_id}")
    return ("\r\n".join(lines) + "\r\n\r\n" + body).encode()


@pytest.fixture
def sessions(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def make_inbox(
    sessions: async_sessionmaker[AsyncSession], kind: str = "smtp"
) -> Inbox:
    async with sessions() as db:
        inbox, _ = await InboxRepository(db, POLICY).create(
            SYSTEM, kind=kind, label=f"Test {kind}", now=RECEIVED
        )
        await db.commit()
    return inbox


@pytest.fixture
async def inbox(sessions: async_sessionmaker[AsyncSession]) -> Inbox:
    return await make_inbox(sessions)


async def store(
    sessions: async_sessionmaker[AsyncSession],
    inbox: Inbox,
    raw: bytes,
    received_at: datetime = RECEIVED,
) -> Any:
    async with sessions() as db:
        stored = await store_raw(
            db, POLICY, SYSTEM, inbox_id=inbox.id, raw=raw, received_at=received_at
        )
        await db.commit()
    return stored


async def count(engine: AsyncEngine, model: Any = RawMessage) -> int:
    async with engine.connect() as connection:
        query = select(func.count()).select_from(model)
        return int((await connection.execute(query)).scalar_one())


async def test_a_message_is_stored_compressed_with_its_headers(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    raw = mail(subject="=?utf-8?q?Sauvegarde_r=C3=A9ussie?=")
    stored = await store(sessions, inbox, raw)
    assert not stored.duplicate
    async with sessions() as db:
        row = await db.get(RawMessage, stored.id)
        found = await db.get(Inbox, inbox.id)
    assert row is not None and found is not None
    assert row.inbox_id == inbox.id
    assert row.size == len(raw)
    assert row.sha256 == hashlib.sha256(raw).hexdigest()
    assert zlib.decompress(row.body_zlib) == raw
    assert raw_bytes(row.body_zlib) == raw
    assert row.message_id == "<run-1@backup.example.com>"
    assert ["Subject", "Sauvegarde réussie"] in row.headers
    assert row.parse_state == "pending"
    assert row.client_id is None
    # settings.retention_raw_days, 30 by default.
    assert row.purge_after == RECEIVED + timedelta(days=30)
    assert found.last_message_at == RECEIVED


async def test_purge_after_follows_the_retention_setting(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox
) -> None:
    async with sessions() as db:
        await db.execute(update(AppSettings).values(retention_raw_days=7))
        await db.commit()
    try:
        stored = await store(sessions, inbox, mail())
        async with sessions() as db:
            row = await db.get(RawMessage, stored.id)
        assert row is not None
        assert row.purge_after == RECEIVED + timedelta(days=7)
    finally:
        async with sessions() as db:
            await db.execute(update(AppSettings).values(retention_raw_days=30))
            await db.commit()


async def test_the_same_message_id_is_stored_once_per_inbox(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    first = await store(sessions, inbox, mail("first body\r\n"))
    # Same Message-ID, other body (a vendor re-send): one row, counted once.
    again = await store(
        sessions, inbox, mail("second body\r\n"), RECEIVED + timedelta(minutes=5)
    )
    assert again.duplicate and again.id == first.id
    assert await count(db_engine) == 1
    # Another inbox keeps its own copy.
    other = await make_inbox(sessions, "webhook")
    elsewhere = await store(sessions, other, mail("first body\r\n"))
    assert not elsewhere.duplicate
    assert await count(db_engine) == 2


async def test_the_same_date_and_body_is_stored_once_per_inbox(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    first = await store(sessions, inbox, mail(message_id=None))
    # A forwarder gave it a new Message-ID and LF line endings: same content.
    forwarded = mail(message_id="<fwd-9@relay.example.com>").replace(b"\r\n", b"\n")
    again = await store(sessions, inbox, forwarded)
    assert again.duplicate and again.id == first.id
    assert await count(db_engine) == 1


async def test_the_same_text_on_another_day_is_a_new_message(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    # A script that mails the same words every night is not a duplicate.
    await store(sessions, inbox, mail("OK\r\n", message_id=None))
    next_day = mail("OK\r\n", message_id=None, date="Tue, 5 Jan 2027 06:29:00 +0000")
    stored = await store(sessions, inbox, next_day, RECEIVED + timedelta(days=1))
    assert not stored.duplicate
    assert await count(db_engine) == 2


async def test_alerts_that_differ_only_in_the_subject_are_two_messages(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    # A tool that puts the status in the Subject, same second, same empty body.
    ok = mail("", message_id="<a@backup.example.com>", subject="srv1: OK")
    failed = mail("", message_id="<b@backup.example.com>", subject="srv1: FAILED")
    assert not (await store(sessions, inbox, ok)).duplicate
    assert not (await store(sessions, inbox, failed)).duplicate
    assert await count(db_engine) == 2


async def test_mail_without_a_date_is_deduplicated_by_message_id_only(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    def undated(message_id: str | None) -> bytes:
        header = "" if message_id is None else f"Message-ID: {message_id}\r\n"
        return f"Subject: nightly\r\n{header}\r\ndone\r\n".encode()

    # A script without Date or Message-ID: every run is kept.
    for _ in range(2):
        assert not (await store(sessions, inbox, undated(None))).duplicate
    first = await store(sessions, inbox, undated("<run-7@script.example.com>"))
    again = await store(sessions, inbox, undated("<run-7@script.example.com>"))
    assert again.duplicate and again.id == first.id
    assert await count(db_engine) == 3


async def test_a_duplicate_purged_before_the_lookup_is_stored_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserts: list[uuid.UUID | None] = [None, uuid.uuid4()]

    async def insert(self: Any, principal: Any, **fields: Any) -> uuid.UUID | None:
        return inserts.pop(0)

    async def nothing(self: Any, principal: Any, *args: Any, **kwargs: Any) -> Any:
        return None

    async def keep_days(self: Any, principal: Any) -> int:
        return 30

    monkeypatch.setattr(RawMessageRepository, "insert", insert)
    monkeypatch.setattr(RawMessageRepository, "find_duplicate", nothing)
    monkeypatch.setattr(RawMessageRepository, "keep_days", keep_days)
    monkeypatch.setattr(InboxRepository, "mark_received", nothing)
    db: Any = None
    stored = await store_raw(
        db, POLICY, SYSTEM, inbox_id=uuid.uuid4(), raw=mail(), received_at=RECEIVED
    )
    assert not stored.duplicate and inserts == []

    # Neither stored nor found twice: an error, never a silent loss.
    inserts.extend([None, None])
    with pytest.raises(RuntimeError, match="neither stored nor found"):
        await store_raw(
            db, POLICY, SYSTEM, inbox_id=uuid.uuid4(), raw=mail(), received_at=RECEIVED
        )


async def test_two_deliveries_at_once_store_one_row(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    raw = mail()
    async with sessions() as first, sessions() as second:
        stored = await store_raw(
            first, POLICY, SYSTEM, inbox_id=inbox.id, raw=raw, received_at=RECEIVED
        )
        # The second insert waits on the first transaction's unique key.
        racing = asyncio.create_task(
            store_raw(
                second, POLICY, SYSTEM, inbox_id=inbox.id, raw=raw, received_at=RECEIVED
            )
        )
        await asyncio.sleep(0.2)
        assert not racing.done()
        await first.commit()
        late = await asyncio.wait_for(racing, timeout=5)
        await second.commit()
    assert late.duplicate and late.id == stored.id
    assert await count(db_engine) == 1


async def test_the_size_cap_is_5_mb(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, db_engine: AsyncEngine
) -> None:
    head = mail("", message_id="<big@backup.example.com>")
    largest = head + b"a" * (MAX_MESSAGE_BYTES - len(head))
    assert len(largest) == MAX_MESSAGE_BYTES
    stored = await store(sessions, inbox, largest)
    assert not stored.duplicate
    with pytest.raises(MessageTooLarge):
        await store(sessions, inbox, mail(message_id=None) + b"a" * MAX_MESSAGE_BYTES)
    assert await count(db_engine) == 1


def test_a_stored_body_that_inflates_past_the_cap_is_refused() -> None:
    bomb = zlib.compress(b"\0" * (MAX_MESSAGE_BYTES + 1))
    with pytest.raises(MessageTooLarge):
        raw_bytes(bomb)


async def test_record_result_keeps_a_run(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox
) -> None:
    stored = await store(sessions, inbox, mail())
    result = ParsedResult(
        status="success",
        job_name="  Nightly   server backup ",
        client_hint="Fictional Dental Clinic",
        started_at=RECEIVED - timedelta(hours=1),
        finished_at=RECEIVED - timedelta(minutes=1),
        run_id="run-1",
        details={"processed_gb": 12.5, "warnings": []},
    )
    async with sessions() as db:
        result_id = await record_result(
            db, POLICY, SYSTEM, result, received_at=RECEIVED, raw_message_id=stored.id
        )
        await db.commit()
        row = await db.get(JobResult, result_id)
    assert row is not None
    assert row.job_id is None
    assert row.job_name == "Nightly server backup"
    assert row.client_hint == "Fictional Dental Clinic"
    assert row.status == "success"
    assert row.raw_message_id == stored.id
    assert row.details == {"processed_gb": 12.5, "warnings": []}
    assert row.received_at == RECEIVED


@pytest.mark.parametrize(
    ("result", "field"),
    [
        (ParsedResult(status="ok"), "status"),  # type: ignore[arg-type]
        (ParsedResult(status="failed", job_name="x" * 201), "job_name"),
        (ParsedResult(status="failed", client_hint="x" * 201), "client_hint"),
        (ParsedResult(status="failed", run_id="x" * 201), "run_id"),
        (ParsedResult(status="failed", started_at=datetime(2027, 1, 4)), "started_at"),
        (
            ParsedResult(status="failed", finished_at=datetime(2027, 1, 4)),
            "finished_at",
        ),
        (ParsedResult(status="failed", details={"at": RECEIVED}), "JSON"),
        (ParsedResult(status="failed", details={"x": "a\0b"}), "NUL"),
        (ParsedResult(status="failed", details={"x": ["a", {"\0": 1}]}), "NUL"),
        # json.loads turns the escape \ud800 of a request body into this.
        (ParsedResult(status="failed", details={"x": "\ud800"}), "Unicode"),
        (ParsedResult(status="failed", details={"x": "a" * 17000}), "bytes"),
    ],
)
async def test_record_result_refuses_what_the_table_cannot_hold(
    sessions: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    result: ParsedResult,
    field: str,
) -> None:
    async with sessions() as db:
        with pytest.raises(ResultRejected, match=field):
            await record_result(db, POLICY, SYSTEM, result, received_at=RECEIVED)
    assert await count(db_engine, JobResult) == 0


async def test_a_backslash_u0000_text_is_not_a_nul(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    path = "C:\\backup\\u0000\\job.log"
    result = ParsedResult(status="success", details={"log": path})
    async with sessions() as db:
        result_id = await record_result(
            db, POLICY, SYSTEM, result, received_at=RECEIVED
        )
        await db.commit()
        row = await db.get(JobResult, result_id)
    assert row is not None and row.details == {"log": path}


class Refuses(AllowAllPolicy):
    def __init__(self) -> None:
        self.asked: list[str] = []

    def check(self, principal: Principal, action: Action) -> None:
        self.asked.append(f"{action.resource}.{action.verb}")
        raise AccessDenied(action.resource)


class NoDatabase:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the database was used ({name}) before the policy")


async def test_the_store_asks_the_access_policy_first() -> None:
    policy = Refuses()
    db: Any = NoDatabase()
    with pytest.raises(AccessDenied):
        await store_raw(
            db, policy, SYSTEM, inbox_id=uuid.uuid4(), raw=mail(), received_at=RECEIVED
        )
    with pytest.raises(AccessDenied):
        await record_result(
            db, policy, SYSTEM, ParsedResult(status="unknown"), received_at=RECEIVED
        )
    assert policy.asked == ["raw_message.read", "job_result.create"]
