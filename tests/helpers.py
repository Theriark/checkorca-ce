"""Helpers shared by the tests. Every value here is synthetic."""

import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jsonschema
from aiosmtpd.smtp import SMTP, AuthResult, Envelope, LoginPassword, Session
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import Role
from app.db.models import AppUser
from app.security.passwords import PasswordService

TEST_SECRET_KEY = "s" * 40
# The all-zero Fernet key: valid in shape, protects nothing.
TEST_FERNET_KEY = base64.urlsafe_b64encode(bytes(32)).decode()
# Nothing listens on port 1: a database that is never reachable.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://checkorca:unused@127.0.0.1:1/x"
# CI points DATABASE_URL at the PostgreSQL 16 service (database checkorca_test).
DATABASE_URL = os.environ.get("DATABASE_URL", UNREACHABLE_DATABASE_URL)

# Synthetic accounts (legal R-11: example.com).
ADMIN_EMAIL = "admin.one@example.com"
TECHNICIAN_EMAIL = "technician.one@example.com"
# Passwords of the synthetic accounts: long enough, low entropy, obviously fake.
ADMIN_PASSWORD = "Synthetic-" + "a" * 12
TECHNICIAN_PASSWORD = "Synthetic-" + "t" * 12
CSRF_HEADER = "X-CSRF-Token"
# Synthetic clients (legal R-11: fictional companies).
CLIENT_NAMES = (
    "Fictional Dental Clinic",
    "Example Freight Ltd",
    "Sample Law Office",
)


class FakeClock:
    """A clock that moves only when a test says so."""

    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2027, 1, 4, 9, 0, tzinfo=UTC)
        self.seconds = 1_000.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.seconds

    def advance(self, **delta: float) -> None:
        step = timedelta(**delta)
        self.current += step
        self.seconds += step.total_seconds()


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A client for the app with its lifespan running (the engine is disposed).

    The base URL is https so the client sends the Secure session cookie back.
    """
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="https://test")
        async with client:
            yield client


def another_browser(app: FastAPI) -> httpx.AsyncClient:
    """A second client with its own cookies, for an app that is running."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="https://test")


async def add_user(
    engine: AsyncEngine,
    email: str,
    password: str,
    role: Role,
    created_at: datetime | None = None,
    **fields: Any,
) -> AppUser:
    """Insert a user directly, with an Argon2id hash of the password."""
    user = AppUser(
        email=email,
        password_hash=await PasswordService().hash(password),
        role=role,
        failed_logins=0,
        disabled=False,
        created_at=created_at or datetime(2027, 1, 1, tzinfo=UTC),
        **fields,
    )
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        db.add(user)
        await db.commit()
    return user


async def sign_in(client: httpx.AsyncClient, email: str, password: str) -> str:
    """Sign in through the API; returns the CSRF token of the new session."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]
    return token


async def make_client(
    client: httpx.AsyncClient, csrf: str, name: str, **fields: Any
) -> dict[str, Any]:
    """Create a client through the API."""
    response = await client.post(
        "/api/v1/clients",
        json={"name": name, **fields},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def make_job(
    client: httpx.AsyncClient, csrf: str, client_id: str, name: str, **fields: Any
) -> dict[str, Any]:
    """Create a job through the API: daily at 23:00 Lisbon unless fields say."""
    body = {
        "client_id": client_id,
        "name": name,
        "schedule_kind": "daily",
        "schedule_expr": "23:00",
        "timezone": "Europe/Lisbon",
        **fields,
    }
    response = await client.post("/api/v1/jobs", json=body, headers={CSRF_HEADER: csrf})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def move_to(
    client: httpx.AsyncClient, clock: FakeClock, moment: datetime
) -> None:
    """Move the clock to moment in steps of at most 11 hours, using the session
    after each step so the 12-hour idle limit never signs the test out (pings
    and API tokens do not keep the session alive, and short moves add up)."""
    step = timedelta(hours=11)
    while moment - clock.now() > step:
        clock.advance(seconds=step.total_seconds())
        assert (await client.get("/api/v1/auth/me")).status_code == 200
    clock.advance(seconds=(moment - clock.now()).total_seconds())
    assert (await client.get("/api/v1/auth/me")).status_code == 200


def ping_path(job: dict[str, Any]) -> str:
    return "/api/v1/ping/" + str(job["ping_url"]).rsplit("/", 1)[1]


# The dashboard scenario (phase C8-B), on the fake clock from 2027-01-04
# 09:00Z: three clients, five daily Europe/Lisbon jobs (UTC+0 in January) and
# two nights of runs. Night 1 (4 January): the archive at 20:00, the dump at
# 22:00 and the nightly backup at 23:00 report success; the offsite copy at
# 21:00 never reports. Night 2: the archive warns, the dump fails, the nightly
# backup succeeds, the offsite copy stays silent. The paused job never runs.
# One result for an unknown job waits in Unmatched. The evaluator runs at
# 09:00 on 5 and 6 January; the scenario ends on 6 January at 09:00.
SCENARIO_END = datetime(2027, 1, 6, 9, tzinfo=UTC)
SCENARIO_JOBS = (
    ("nightly", 0, "Nightly server backup", "23:00"),
    ("dump", 0, "Database dump", "22:00"),
    ("offsite", 1, "Offsite copy", "21:00"),
    ("archive", 2, "Mail archive", "20:00"),
    ("paused", 2, "Paused job", "23:30"),
)


async def build_scenario(
    client: httpx.AsyncClient,
    csrf: str,
    clock: FakeClock,
    tick: Callable[[], Awaitable[None]],
) -> dict[str, dict[str, Any]]:
    """The scenario through the API; returns the jobs by key."""
    headers = {CSRF_HEADER: csrf}
    clients = [await make_client(client, csrf, name) for name in CLIENT_NAMES]
    jobs = {
        key: await make_job(
            client, csrf, clients[index]["id"], name, schedule_expr=expr
        )
        for key, index, name, expr in SCENARIO_JOBS
    }
    paused = await client.post(
        f"/api/v1/jobs/{jobs['paused']['id']}/pause", headers=headers
    )
    assert paused.status_code == 200
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Scripts", "scope": "ingest"},
        headers=headers,
    )
    assert created.status_code == 201
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}

    async def post_result(body: dict[str, Any]) -> None:
        response = await client.post("/api/v1/results", json=body, headers=bearer)
        assert response.status_code == 202, response.text

    nights = ((4, "success", 15, ""), (5, "warning", 10, "/fail"))
    for day, archive, dump_minute, dump_signal in nights:
        evening = datetime(2027, 1, day, 20, tzinfo=UTC)
        await move_to(client, clock, evening.replace(minute=31))
        await post_result(
            {
                "job_id": jobs["archive"]["id"],
                "status": archive,
                "started_at": evening.replace(second=30).isoformat(),
                "finished_at": evening.replace(minute=30).isoformat(),
            }
        )
        await move_to(client, clock, evening.replace(hour=22, minute=dump_minute))
        dumped = await client.get(ping_path(jobs["dump"]) + dump_signal)
        assert dumped.status_code == 200
        await move_to(client, clock, evening.replace(hour=23, minute=20))
        assert (await client.get(ping_path(jobs["nightly"]))).status_code == 200
        if day == 4:
            await move_to(client, clock, datetime(2027, 1, 5, 9, tzinfo=UTC))
            await tick()
            await move_to(client, clock, datetime(2027, 1, 5, 12, tzinfo=UTC))
            await post_result(
                {
                    "job_name": "Unknown export job",
                    "client_hint": "Nobody Example Ltd",
                    "status": "failed",
                }
            )
    await move_to(client, clock, SCENARIO_END)
    await tick()
    return jobs


# A synthetic alert mail of the scenario's nightly backup (written for the
# tests, generic-keywords style). Its relay header and its last body line
# carry a secret-looking value that no export, digest or activity may show.
MAIL_SECRET = "Canary-mail-" + "k" * 16
MAIL_MESSAGE_ID = "<c8-nightly-1@backup.example.com>"
MAIL_INBOX = "Alert mailbox"
NIGHTLY_MAIL = (
    "From: Backup Server <backup@example.com>\r\n"
    "To: alerts@example.com\r\n"
    "Subject: [Success] Nightly server backup\r\n"
    "Date: Wed, 6 Jan 2027 08:55:00 +0000\r\n"
    f"Message-ID: {MAIL_MESSAGE_ID}\r\n"
    f"X-Relay-Credential: {MAIL_SECRET}\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    f"Client: {CLIENT_NAMES[0]}\r\n"
    "Status: Success\r\n"
    "Host: fs01.example.com\r\n"
    f"Api key: {MAIL_SECRET}\r\n"
).encode()


async def deliver_mail(
    client: httpx.AsyncClient, csrf: str, parse: Callable[[], Awaitable[None]]
) -> str:
    """NIGHTLY_MAIL through an SMTP inbox's HTTP receiver, then the worker's
    parse hook (parse): the result is bound to the nightly backup of the
    dental clinic. Returns the stored message's id."""
    headers = {CSRF_HEADER: csrf}
    inbox = await client.post(
        "/api/v1/inboxes", json={"kind": "smtp", "label": MAIL_INBOX}, headers=headers
    )
    assert inbox.status_code == 201, inbox.text
    token = await client.post(
        "/api/v1/tokens",
        json={"label": "Mail relay", "scope": "ingest"},
        headers=headers,
    )
    assert token.status_code == 201, token.text
    code = str(inbox.json()["ingest_url"]).rsplit("/", 1)[1]
    sent = await client.post(
        f"/api/v1/ingest/email/{code}",
        content=NIGHTLY_MAIL,
        headers={
            "Authorization": f"Bearer {token.json()['token']}",
            "Content-Type": "message/rfc822",
        },
    )
    assert sent.status_code == 202, sent.text
    await parse()
    message_id: str = sent.json()["message_id"]
    return message_id


class RelayCapture:
    """The handler of a test SMTP relay: keeps every message it accepts as
    (sender, recipients, raw bytes)."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, list[str], bytes]] = []

    async def handle_DATA(
        self, server: SMTP, session: Session, envelope: Envelope
    ) -> str:
        content = envelope.original_content or b""
        sender = str(envelope.mail_from)
        self.messages.append((sender, list(envelope.rcpt_tos), content))
        return "250 OK"


@asynccontextmanager
async def smtp_relay(
    capture: RelayCapture, *, login: tuple[str, str] | None = None
) -> AsyncIterator[int]:
    """A capturing SMTP relay on 127.0.0.1 and a free port (yielded). With
    login it offers AUTH PLAIN and LOGIN without TLS and accepts only that
    user name and password."""

    def authenticator(
        server: SMTP, session: Session, envelope: Envelope, mechanism: str, data: Any
    ) -> AuthResult:
        accepted = (
            login is not None
            and isinstance(data, LoginPassword)
            and (data.login, data.password) == tuple(map(str.encode, login))
        )
        return AuthResult(success=accepted)

    options: dict[str, Any] = {}
    if login is not None:
        options = {"authenticator": authenticator, "auth_require_tls": False}
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: SMTP(capture, hostname="relay.test", **options), "127.0.0.1", 0
    )
    try:
        yield int(server.sockets[0].getsockname()[1])
    finally:
        server.close()
        await server.wait_closed()


def http_answer(status: int = 200) -> bytes:
    """The bytes of a minimal HTTP answer with the given status."""
    text = {302: "Found", 404: "Not Found", 500: "Internal Server Error"}.get(
        status, "OK"
    )
    return (
        f"HTTP/1.1 {status} {text}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    ).encode()


# The secret part of a webhook URL: its path. url_host (the host) is shown,
# so a leak check looks for this path, never for the whole URL.
URL_CANARY = "/services/T000/B000/secret-secret"
WEBHOOK_SCHEMA = Path(__file__).parents[1] / "docs" / "webhook-payload.schema.json"


def validate_webhook_payload(body: dict[str, Any]) -> None:
    """A webhook body as sent follows the published contract (payload v1)."""
    schema = json.loads(WEBHOOK_SCHEMA.read_text())
    jsonschema.Draft202012Validator(schema).validate(body)


@dataclass(slots=True)
class HttpRequest:
    """One request the HTTP capture server saw."""

    line: str
    headers: list[str]
    body: dict[str, Any]


class HttpCapture:
    """A scripted HTTP server on 127.0.0.1 for the webhook channel kinds: it
    answers the given responses in order (the last repeats), keeps every
    request it saw, and talks to nothing else. With hang it answers nothing
    at all, until the client gives up and closes."""

    def __init__(self, responses: Sequence[bytes], *, hang: bool = False) -> None:
        self.responses = tuple(responses)
        self.hang = hang
        self.requests: list[HttpRequest] = []
        self.port = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    @property
    def url(self) -> str:
        """A URL with a secret-looking path, as a webhook channel stores it."""
        return f"http://127.0.0.1:{self.port}{URL_CANARY}"

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            head: list[str] = []
            length = 0
            while True:
                header = await asyncio.wait_for(reader.readline(), timeout=5)
                if header in (b"\r\n", b""):
                    break
                head.append(header.decode("ascii", "replace").rstrip("\r\n"))
                if header.lower().startswith(b"content-length:"):
                    length = int(header.split(b":", 1)[1])
            body = await asyncio.wait_for(reader.readexactly(length), timeout=5)
            if self.hang:
                await reader.read()
                return
            # Recorded before the answer, so a client that read the status
            # line already sees its request in self.requests.
            self.requests.append(
                HttpRequest(
                    line=line.decode("ascii", "replace").rstrip("\r\n"),
                    headers=head,
                    body=json.loads(body) if body else {},
                )
            )
            index = min(len(self.requests) - 1, len(self.responses) - 1)
            writer.write(self.responses[index])
            await writer.drain()
        except (TimeoutError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                writer.close()
            except OSError:
                pass
