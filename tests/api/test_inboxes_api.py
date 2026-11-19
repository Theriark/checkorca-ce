"""inboxes: create every kind, write-only secrets (D-6), the webhook token
shown once, changes, deletion and roles."""

import logging
import re
import uuid
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.api.v1.inboxes import secret_hint
from app.db.models import AppUser, AuditEvent, Inbox, RawMessage
from app.ingest.store import store_raw
from app.repos.inboxes import InboxRepository
from app.security.crypto import MASK, SecretBox
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    TEST_FERNET_KEY,
    FakeClock,
    sign_in,
)

# A password nobody would type: if it shows up anywhere, a secret leaked.
CANARY = "Canary-" + "i" * 16
CANARY_HINT = "****iiii"
IMAP = {
    "host": "imap.example.com",
    "username": "alerts@example.com",
    "password": CANARY,
}


@pytest.fixture(autouse=True)
def mail_domain(settings_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_DOMAIN", "Alerts.Example.com")


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def create(client: httpx.AsyncClient, csrf: str, **body: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/inboxes", json=body, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_an_smtp_inbox_has_an_address_and_an_ingest_url(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    inbox = await create(client, csrf, kind="smtp", label="  Veeam   alerts ")
    code = inbox["address"].split("@")[0]
    assert re.fullmatch(r"[a-z0-9]{24}", code)
    assert inbox["address"] == f"{code}@alerts.example.com"
    assert inbox["ingest_url"] == f"http://localhost:8080/api/v1/ingest/email/{code}"
    assert inbox["label"] == "Veeam alerts"
    assert inbox["kind"] == "smtp"
    assert inbox["imap"] is None
    assert inbox["webhook_token"] is None
    assert inbox["webhook_token_set"] is False
    assert inbox["sender_allowlist"] == []
    assert inbox["require_auth_results"] is False
    assert inbox["last_message_at"] is None
    assert inbox["created_at"] == "2027-01-04T09:00:00Z"
    found = await client.get(f"/api/v1/inboxes/{inbox['id']}")
    assert found.status_code == 200
    assert "webhook_token" not in found.json()


async def test_the_webhook_token_is_shown_once_and_rotates(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    inbox = await create(client, csrf, kind="webhook", label="Script webhook")
    token = inbox["webhook_token"]
    assert token.startswith("chki_") and len(token) > 30
    assert inbox["address"] is None
    code = inbox["ingest_url"].rsplit("/", 1)[1]
    assert re.fullmatch(r"[a-z0-9]{24}", code)
    assert inbox["webhook_token_set"] is True
    for response in (
        await client.get(f"/api/v1/inboxes/{inbox['id']}"),
        await client.get("/api/v1/inboxes"),
    ):
        assert token not in response.text
    async with db_engine.connect() as connection:
        stored = await connection.scalar(text("SELECT token_sha256 FROM inbox"))
    assert stored is not None and token not in stored

    rotated = await client.post(
        f"/api/v1/inboxes/{inbox['id']}/token", headers={CSRF_HEADER: csrf}
    )
    assert rotated.status_code == 200
    new_token = rotated.json()["webhook_token"]
    assert new_token != token
    async with async_sessionmaker(db_engine)() as db:
        inboxes = InboxRepository(db, AllowAllPolicy())
        assert await inboxes.find_by_token(SYSTEM, token) is None
        found = await inboxes.find_by_token(SYSTEM, new_token)
        assert found is not None and str(found.id) == inbox["id"]
        by_code = await inboxes.find_by_code(SYSTEM, code.upper(), kinds=("webhook",))
        assert by_code is not None and by_code.id == found.id
        assert await inboxes.find_by_code(SYSTEM, by_code.code, kinds=("smtp",)) is None

    smtp = await create(client, csrf, kind="smtp", label="Mail")
    refused = await client.post(
        f"/api/v1/inboxes/{smtp['id']}/token", headers={CSRF_HEADER: csrf}
    )
    assert refused.status_code == 409


async def test_imap_secrets_never_come_back(
    client: httpx.AsyncClient,
    csrf: str,
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    created = await client.post(
        "/api/v1/inboxes",
        json={"kind": "imap", "label": "Shared alert mailbox", "imap": IMAP},
        headers={CSRF_HEADER: csrf},
    )
    assert created.status_code == 201
    inbox = created.json()
    assert inbox["imap"] == {
        "host": "imap.example.com",
        "port": 993,
        "username": "alerts@example.com",
        "folder": "INBOX",
        "poll_seconds": 300,
        "tls": True,
        "secret_set": True,
        "secret_hint": CANARY_HINT,
    }
    assert inbox["address"] is None and inbox["ingest_url"] is None
    path = f"/api/v1/inboxes/{inbox['id']}"
    changed = await client.patch(
        path,
        json={"imap": {"password": "Other-" + CANARY, "poll_seconds": 120}},
        headers={CSRF_HEADER: csrf},
    )
    assert changed.status_code == 200
    assert changed.json()["imap"]["poll_seconds"] == 120
    reads = [
        await client.get(path),
        await client.get("/api/v1/inboxes"),
        await client.get("/api/v1/system/status"),
    ]
    assert [read.status_code for read in reads] == [200, 200, 200]
    for answer in [created, changed, *reads]:
        assert CANARY not in answer.text
    async with db_engine.connect() as connection:
        query = text("SELECT imap_password_enc FROM inbox")
        ciphertext = await connection.scalar(query)
        query = select(AuditEvent.action, AuditEvent.details)
        audit = (await connection.execute(query)).all()
    assert ciphertext is not None and CANARY not in ciphertext
    # One fake clock time for every event: compared in action order.
    inbox_events = sorted((action, details) for action, details in audit)
    inbox_events = [event for event in inbox_events if event[0].startswith("inbox.")]
    assert inbox_events == [
        ("inbox.create", {"kind": "imap"}),
        ("inbox.update", {"fields": "imap_password_enc,imap_poll_seconds"}),
    ]
    assert CANARY not in str(audit)
    assert CANARY not in caplog.text


async def test_a_new_imap_server_needs_the_password_again(
    client: httpx.AsyncClient,
    csrf: str,
    technician: AppUser,
    db_engine: AsyncEngine,
) -> None:
    """The stored password is never sent to a server it was not given for."""
    inbox = await create(client, csrf, kind="imap", label="Mailbox", imap=IMAP)
    path = f"/api/v1/inboxes/{inbox['id']}"
    query = text("SELECT imap_password_enc, imap_host FROM inbox")
    async with db_engine.connect() as connection:
        before = tuple((await connection.execute(query)).one())
    tech_csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    headers = {CSRF_HEADER: tech_csrf}
    for target in (
        {"host": "imap.attacker.test"},
        {"port": 143},
        {"tls": False},
        {"username": "other@example.com"},
    ):
        refused = await client.patch(path, json={"imap": target}, headers=headers)
        assert refused.status_code == 422, target
        assert refused.json()["title"] == "IMAP password required"
    async with db_engine.connect() as connection:
        assert tuple((await connection.execute(query)).one()) == before
    # Other settings keep the stored password; a new server with it is fine.
    kept = await client.patch(
        path, json={"imap": {"poll_seconds": 600}}, headers=headers
    )
    assert kept.status_code == 200
    assert kept.json()["imap"]["secret_hint"] == CANARY_HINT
    moved = await client.patch(
        path,
        json={"imap": {"host": "mail.example.net", "password": "New-" + CANARY}},
        headers=headers,
    )
    assert moved.status_code == 200
    assert moved.json()["imap"]["host"] == "mail.example.net"


async def test_a_refused_imap_form_does_not_echo_the_password(
    client: httpx.AsyncClient, csrf: str
) -> None:
    bad = {**IMAP, "password": CANARY + "\n", "port": 0}
    response = await client.post(
        "/api/v1/inboxes",
        json={"kind": "imap", "label": "Broken", "imap": bad},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 422
    assert CANARY not in response.text
    fields = {error["field"] for error in response.json()["errors"]}
    assert fields == {"body.imap.password", "body.imap.port"}


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "imap", "label": "No settings"},
        {"kind": "smtp", "label": "Stray settings", "imap": IMAP},
        {"kind": "pop3", "label": "Unknown kind"},
        {"kind": "smtp", "label": " "},
        {"kind": "smtp", "label": "Bad sender", "sender_allowlist": ["not an address"]},
        {"kind": "smtp", "label": "Extra", "code": "chosen"},
        {"kind": "imap", "label": "Bad host", "imap": {**IMAP, "host": "a b"}},
    ],
)
async def test_invalid_inboxes_are_refused(
    client: httpx.AsyncClient, csrf: str, body: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/v1/inboxes", json=body, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 422, response.text


async def test_changes_and_the_sender_allowlist(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    inbox = await create(
        client,
        csrf,
        kind="smtp",
        label="Mail",
        sender_allowlist=[" Backup@Example.com ", "@example.com", "@EXAMPLE.COM"],
    )
    assert inbox["sender_allowlist"] == ["backup@example.com", "@example.com"]
    path = f"/api/v1/inboxes/{inbox['id']}"
    changed = await client.patch(
        path,
        json={"label": "Vendor mail", "require_auth_results": True},
        headers={CSRF_HEADER: csrf},
    )
    assert changed.status_code == 200
    assert changed.json()["label"] == "Vendor mail"
    assert changed.json()["require_auth_results"] is True
    same = await client.patch(
        path, json={"label": "Vendor mail"}, headers={CSRF_HEADER: csrf}
    )
    assert same.status_code == 200
    imap = await client.patch(
        path, json={"imap": {"port": 143}}, headers={CSRF_HEADER: csrf}
    )
    assert imap.status_code == 409
    missing = await client.patch(
        f"/api/v1/inboxes/{uuid.uuid4()}", json={}, headers={CSRF_HEADER: csrf}
    )
    assert missing.status_code == 404
    async with db_engine.connect() as connection:
        query = select(AuditEvent.action, AuditEvent.details).where(
            AuditEvent.action.like("inbox.%")
        )
        audit = sorted((await connection.execute(query)).all())
    # The unchanged label wrote no second event.
    assert [action for action, _ in audit] == ["inbox.create", "inbox.update"]
    assert audit[1][1] == {"fields": "label,require_auth_results"}


async def test_deleting_an_inbox_keeps_its_messages(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    inbox = await create(client, csrf, kind="smtp", label="To delete")
    async with async_sessionmaker(db_engine)() as db:
        stored = await store_raw(
            db,
            AllowAllPolicy(),
            SYSTEM,
            inbox_id=uuid.UUID(inbox["id"]),
            raw=b"Subject: kept\r\n\r\nbody",
            received_at=clock.now(),
        )
        await db.commit()
    path = f"/api/v1/inboxes/{inbox['id']}"
    deleted = await client.delete(path, headers={CSRF_HEADER: csrf})
    assert deleted.status_code == 204
    assert (await client.get(path)).status_code == 404
    again = await client.delete(path, headers={CSRF_HEADER: csrf})
    assert again.status_code == 404
    async with db_engine.connect() as connection:
        assert await connection.scalar(select(Inbox.id)) is None
        query = select(RawMessage.inbox_id).where(RawMessage.id == stored.id)
        assert (await connection.execute(query)).one() == (None,)


async def test_technicians_manage_inboxes_too(
    client: httpx.AsyncClient, technician: AppUser
) -> None:
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    inbox = await create(client, csrf, kind="webhook", label="Technician webhook")
    listed = await client.get("/api/v1/inboxes", params={"kind": "webhook"})
    assert [item["id"] for item in listed.json()["items"]] == [inbox["id"]]
    deleted = await client.delete(
        f"/api/v1/inboxes/{inbox['id']}", headers={CSRF_HEADER: csrf}
    )
    assert deleted.status_code == 204


async def test_the_list_pages_oldest_first(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    made = []
    for number in range(3):
        made.append(await create(client, csrf, kind="smtp", label=f"Inbox {number}"))
        clock.advance(minutes=1)
    first = await client.get("/api/v1/inboxes", params={"limit": 2})
    page = first.json()
    assert [item["id"] for item in page["items"]] == [made[0]["id"], made[1]["id"]]
    second = await client.get(
        "/api/v1/inboxes", params={"limit": 2, "cursor": page["next_cursor"]}
    )
    assert [item["id"] for item in second.json()["items"]] == [made[2]["id"]]
    assert second.json()["next_cursor"] is None
    bad = await client.get("/api/v1/inboxes", params={"cursor": "not-a-cursor"})
    assert bad.status_code == 400


async def test_a_session_is_needed_to_change_inboxes(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/v1/inboxes", json={"kind": "smtp"})
    assert response.status_code == 401
    assert (await client.get("/api/v1/inboxes")).status_code == 401


def test_the_imap_password_hint_survives_a_key_change() -> None:
    other = SecretBox(Fernet.generate_key().decode())
    sealed = other.encrypt(CANARY)
    assert secret_hint(SecretBox(TEST_FERNET_KEY), sealed) == MASK
    assert secret_hint(other, sealed) == CANARY_HINT
    assert secret_hint(other, None) is None
