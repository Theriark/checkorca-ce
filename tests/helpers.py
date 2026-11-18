"""Helpers shared by the tests. Every value here is synthetic."""

import base64
import os
from collections.abc import AsyncIterator
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
