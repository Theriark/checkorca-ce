"""messages, results and system/status: lists, detail, filters, pages and the
worker fields. Mail and names are synthetic (R-11)."""

import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.api.pagination import encode_cursor
from app.db.models import AppUser, Inbox
from app.ingest.results import ParsedResult, ResultStatus
from app.ingest.store import record_result, store_raw
from app.repos.heartbeat import HeartbeatRepository
from app.repos.inboxes import InboxRepository
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    make_client,
    make_job,
    sign_in,
)

POLICY = AllowAllPolicy()
DENTAL = CLIENT_NAMES[0]
HOSTILE = '<img src=x onerror="alert(1)">'


def mail(number: int, subject: str = "[Failed] Nightly server backup") -> bytes:
    return (
        f"From: Backup Server <backup@example.com>\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Mon, 4 Jan 2027 0{number}:00:00 +0000\r\n"
        f"Message-ID: <run-{number}@backup.example.com>\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"Job Nightly server backup: Failed ({number})\r\n{HOSTILE}\r\n"
    ).encode()


def iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


@pytest.fixture
def sessions(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def add_inbox(sessions: async_sessionmaker[AsyncSession], label: str) -> Inbox:
    async with sessions() as db:
        inbox, _ = await InboxRepository(db, POLICY).create(
            SYSTEM, kind="smtp", label=label, now=FakeClock().now()
        )
        await db.commit()
    return inbox


async def add_messages(
    sessions: async_sessionmaker[AsyncSession], inbox: Inbox, clock: FakeClock
) -> list[uuid.UUID]:
    """Three messages, one minute apart, oldest first."""
    ids = []
    for number in range(1, 4):
        async with sessions() as db:
            stored = await store_raw(
                db,
                POLICY,
                SYSTEM,
                inbox_id=inbox.id,
                raw=mail(number),
                received_at=clock.now(),
            )
            await db.commit()
        ids.append(stored.id)
        clock.advance(minutes=1)
    return ids


async def add_result(
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
    status: ResultStatus,
    **where: Any,
) -> uuid.UUID:
    async with sessions() as db:
        found = await record_result(
            db,
            POLICY,
            SYSTEM,
            ParsedResult(status=status, job_name="Nightly server backup"),
            received_at=clock.now(),
            **where,
        )
        await db.commit()
    clock.advance(seconds=30)
    return found


async def test_messages_list_newest_first_with_pages_and_filters(
    client: httpx.AsyncClient,
    csrf: str,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    inbox = await add_inbox(sessions, "Vendor mail")
    other = await add_inbox(sessions, "Other mail")
    ids = await add_messages(sessions, inbox, clock)
    first = await client.get("/api/v1/messages", params={"limit": 2})
    assert first.status_code == 200
    page = first.json()
    assert [item["id"] for item in page["items"]] == [str(ids[2]), str(ids[1])]
    item = page["items"][0]
    assert item["inbox_id"] == str(inbox.id)
    assert item["message_id"] == "<run-3@backup.example.com>"
    assert item["subject"] == "[Failed] Nightly server backup"
    assert item["sender"] == "Backup Server <backup@example.com>"
    assert item["parse_state"] == "pending"
    assert item["client_id"] is None
    assert item["size"] == len(mail(3))
    rest = await client.get(
        "/api/v1/messages", params={"limit": 2, "cursor": page["next_cursor"]}
    )
    assert [item["id"] for item in rest.json()["items"]] == [str(ids[0])]
    assert rest.json()["next_cursor"] is None

    elsewhere = await client.get("/api/v1/messages", params={"inbox_id": str(other.id)})
    assert elsewhere.json()["items"] == []
    parsed = await client.get("/api/v1/messages", params={"parse_state": "parsed"})
    assert parsed.json()["items"] == []
    bad = await client.get("/api/v1/messages", params={"parse_state": "done"})
    assert bad.status_code == 422
    for at in ("2027-01-04T09:00:00", "yesterday"):
        cursor = encode_cursor({"received_at": at, "id": str(ids[0])})
        refused = await client.get("/api/v1/messages", params={"cursor": cursor})
        assert refused.status_code == 400


async def test_a_message_detail_is_text_with_its_results(
    client: httpx.AsyncClient,
    csrf: str,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    inbox = await add_inbox(sessions, "Vendor mail")
    ids = await add_messages(sessions, inbox, clock)
    result_id = await add_result(sessions, clock, "failed", raw_message_id=ids[0])
    response = await client.get(f"/api/v1/messages/{ids[0]}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["subject"] == "[Failed] Nightly server backup"
    headers = detail["headers"]
    assert {"name": "Message-ID", "value": "<run-1@backup.example.com>"} in headers
    # Hostile content comes back as plain text for the web app to escape.
    assert detail["text"] == f"Job Nightly server backup: Failed (1)\r\n{HOSTILE}\r\n"
    assert detail["text_truncated"] is False
    assert [result["id"] for result in detail["results"]] == [str(result_id)]
    assert detail["results"][0]["status"] == "failed"
    missing = await client.get(f"/api/v1/messages/{uuid.uuid4()}")
    assert missing.status_code == 404


async def test_results_list_and_one_jobs_results(
    client: httpx.AsyncClient,
    csrf: str,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    job_id = uuid.UUID(job["id"])
    unmatched = await add_result(sessions, clock, "unknown")
    failed = await add_result(sessions, clock, "failed", job_id=job_id)
    success = await add_result(sessions, clock, "success", job_id=job_id)

    everything = await client.get("/api/v1/results")
    assert [item["id"] for item in everything.json()["items"]] == [
        str(success),
        str(failed),
        str(unmatched),
    ]
    item = everything.json()["items"][0]
    assert item["job_id"] == job["id"]
    assert item["job_name"] == "Nightly server backup"
    assert item["details"] == {}
    only_failed = await client.get("/api/v1/results", params={"status": "failed"})
    assert [item["id"] for item in only_failed.json()["items"]] == [str(failed)]
    first = await client.get(f"/api/v1/jobs/{job['id']}/results", params={"limit": 1})
    assert [item["id"] for item in first.json()["items"]] == [str(success)]
    rest = await client.get(
        f"/api/v1/jobs/{job['id']}/results",
        params={"limit": 1, "cursor": first.json()["next_cursor"]},
    )
    assert [item["id"] for item in rest.json()["items"]] == [str(failed)]
    assert rest.json()["next_cursor"] is None
    unknown_job = await client.get(f"/api/v1/jobs/{uuid.uuid4()}/results")
    assert unknown_job.status_code == 404
    by_job = await client.get("/api/v1/results", params={"job_id": job["id"]})
    assert len(by_job.json()["items"]) == 2


async def test_system_status_shows_the_worker_inboxes_and_queue(
    client: httpx.AsyncClient,
    csrf: str,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    before = (await client.get("/api/v1/system/status")).json()
    assert before["worker"] == {
        "heartbeat_at": None,
        "age_seconds": None,
        "stale": True,
        "holder": None,
        "started_at": None,
    }
    assert before["inboxes"] == []
    assert before["queue"] == {"pending_messages": 0}
    assert before["version"] == "27.0.0"

    inbox = await add_inbox(sessions, "Vendor mail")
    await add_messages(sessions, inbox, clock)
    started = clock.now()
    async with sessions() as db:
        await HeartbeatRepository(db, POLICY).beat(
            SYSTEM, at=clock.now(), holder="worker-1 pid 7", started_at=started
        )
        await db.commit()
    clock.advance(seconds=42)
    status = (await client.get("/api/v1/system/status")).json()
    assert status["worker"] == {
        "heartbeat_at": iso(started),
        "age_seconds": 42.0,
        "stale": False,
        "holder": "worker-1 pid 7",
        "started_at": iso(started),
    }
    last = iso(started - timedelta(minutes=1))
    assert status["inboxes"] == [
        {
            "id": str(inbox.id),
            "kind": "smtp",
            "label": "Vendor mail",
            "last_message_at": last,
        }
    ]
    assert status["queue"] == {"pending_messages": 3}
    clock.advance(minutes=3)
    late = (await client.get("/api/v1/system/status")).json()
    assert late["worker"]["stale"] is True


async def test_technicians_and_read_tokens_can_read(
    client: httpx.AsyncClient, csrf: str, technician: AppUser
) -> None:
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Monitoring", "scope": "read"},
        headers={"X-CSRF-Token": csrf},
    )
    token = created.json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    paths = ("/api/v1/messages", "/api/v1/results", "/api/v1/system/status")
    for path in (*paths, "/api/v1/inboxes"):
        assert (await client.get(path, headers=bearer)).status_code == 200
    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    for path in paths:
        assert (await client.get(path)).status_code == 200
