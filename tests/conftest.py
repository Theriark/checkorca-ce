"""Shared test setup: synthetic settings for every test, and the database.

CI provides DATABASE_URL (PostgreSQL 16 service container, database
checkorca_test). The secret values in helpers.py are synthetic and protect
nothing.
"""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from alembic import command
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.__main__ import alembic_config
from app.db.models import AppUser
from app.main import create_app
from app.settings import get_settings, load_settings
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DATABASE_URL,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    TEST_FERNET_KEY,
    TEST_SECRET_KEY,
    FakeClock,
    add_user,
    running,
)

OPTIONAL_VARIABLES = (
    "REVISION",
    "ROLE",
    "PORT",
    "SMTP_PORT",
    "MAIL_DOMAIN",
    "SMTP_TLS_CERT_FILE",
    "SMTP_TLS_KEY_FILE",
    "BASE_URL",
    "LOG_LEVEL",
    "DEV_SEED",
    "DEV_SEED_ACCOUNTS",
    "DEV_SEED_PASSWORD_ADMIN",
    "DEV_SEED_PASSWORD_TECHNICIAN",
    "DEV_DEMO_DATA",
    "ALLOW_PRIVATE_TARGETS",
    "OUTBOUND_ALLOWED_HOSTS",
)
# Emptied before each database test; settings keeps its single row.
TABLES = (
    "notification",
    "channel_rule",
    "channel",
    "flip",
    "occurrence",
    "job_state",
    "parser_pack",
    "worker_heartbeat",
    "job_result",
    "raw_message",
    "inbox",
    "job",
    "client",
    "app_session",
    "api_token",
    "audit_event",
    "app_user",
)


@pytest.fixture(autouse=True)
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A complete, valid environment; tests remove or change single values."""
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("FERNET_KEY", TEST_FERNET_KEY)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    for name in OPTIONAL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def migrated() -> None:
    """The test database at the newest revision, once per test run."""
    settings = load_settings(
        secret_key=TEST_SECRET_KEY,
        fernet_key=TEST_FERNET_KEY,
        database_url=DATABASE_URL,
    )
    command.upgrade(alembic_config(settings), "head")


@pytest.fixture
async def db_engine(migrated: None) -> AsyncIterator[AsyncEngine]:
    """An engine on the migrated test database with the tables emptied."""
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
        await connection.execute(
            text(
                "UPDATE settings SET external_heartbeat_url_enc = NULL, "
                "demo_seeded = false, digest_timezone = 'Europe/Lisbon', "
                "digest_time_local = '07:30', reminder_24h = false"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def quiet_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep pytest's log capture: python -m app would replace the root handlers."""
    monkeypatch.setattr("app.__main__.configure_logging", lambda *args: None)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app(db_engine: AsyncEngine, clock: FakeClock) -> FastAPI:
    """The app on the test database with the fake clock."""
    return create_app(load_settings(), static_dir=None, clock=clock)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An API client (one browser) with the app's lifespan running."""
    async with running(app) as api:
        yield api


@pytest.fixture
async def admin(db_engine: AsyncEngine) -> AppUser:
    return await add_user(db_engine, ADMIN_EMAIL, ADMIN_PASSWORD, "admin")


@pytest.fixture
async def technician(db_engine: AsyncEngine) -> AppUser:
    return await add_user(
        db_engine, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD, "technician"
    )
