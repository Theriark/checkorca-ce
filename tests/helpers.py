"""Helpers shared by the tests. Every value here is synthetic."""

import base64
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
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
