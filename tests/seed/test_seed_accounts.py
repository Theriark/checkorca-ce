"""Development seed accounts: the host guard, ensure, and quiet logs."""

import asyncio
import logging
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

import app.__main__ as cli
from app.db.models import AppUser
from app.main import create_app
from app.seed.accounts import (
    SeedError,
    check_seed_host,
    ensure_seed_accounts,
    seed_accounts,
)
from app.settings import load_settings
from helpers import FakeClock, running, sign_in

SEED_ADMIN = "checkorca.admin@example.com"
SEED_TECHNICIAN = "checkorca.technician@example.com"
# Synthetic seed passwords; Development generates its own (token24).
SEED_ADMIN_PASSWORD = "Seed-admin-" + "1" * 12
SEED_TECHNICIAN_PASSWORD = "Seed-tech-" + "2" * 12


@pytest.fixture
def seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_SEED", "1")
    monkeypatch.setenv("BASE_URL", "https://ce-dev-checkorca.theriark.dev")
    monkeypatch.setenv("DEV_SEED_ACCOUNTS", f"{SEED_ADMIN},{SEED_TECHNICIAN}")
    monkeypatch.setenv("DEV_SEED_PASSWORD_ADMIN", SEED_ADMIN_PASSWORD)
    monkeypatch.setenv("DEV_SEED_PASSWORD_TECHNICIAN", SEED_TECHNICIAN_PASSWORD)


async def run_cli(argv: list[str]) -> int:
    """python -m app in a thread: it runs its own event loop."""
    return await asyncio.to_thread(cli.main, argv)


async def users(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as connection:
        rows = (await connection.execute(select(AppUser))).all()
    return {row.email: row for row in rows}


@pytest.mark.parametrize(
    "base_url",
    [
        "https://ce-dev-checkorca.theriark.dev",
        "https://ce-stg-checkorca.theriark.dev",
        "http://localhost:8080",
        "https://CE-DEV-checkorca.theriark.dev/",
    ],
)
def test_seed_hosts_are_allowed(base_url: str) -> None:
    check_seed_host(base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://checkorca.example.com",
        "https://monitor.msp.test",
        "https://ce-prd-checkorca.theriark.dev",
        "https://app.ce-dev-checkorca.example.com",
        "http://127.0.0.1:8080",
        "https://localhost.example.com",
    ],
)
def test_production_like_hosts_are_refused(base_url: str) -> None:
    with pytest.raises(SeedError, match="refused"):
        check_seed_host(base_url)


@pytest.mark.usefixtures("seed_env", "quiet_cli")
async def test_the_seed_refuses_a_production_like_host_and_writes_nothing(
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BASE_URL", "https://checkorca.example.com")
    assert await run_cli(["seed"]) == 2
    err = capsys.readouterr().err
    assert "refused" in err
    assert SEED_ADMIN_PASSWORD not in err
    assert await users(db_engine) == {}


@pytest.mark.usefixtures("seed_env", "quiet_cli")
async def test_web_refuses_to_start_on_a_production_like_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASE_URL", "https://checkorca.example.com")
    served: list[bool] = []

    async def fake_serve(settings: object, with_worker: bool) -> None:
        served.append(with_worker)

    monkeypatch.setattr(cli, "migrate", lambda settings: None)
    monkeypatch.setattr(cli, "serve", fake_serve)
    assert await run_cli(["all"]) == 2
    assert served == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DEV_SEED_ACCOUNTS", "only.one@example.com"),
        ("DEV_SEED_ACCOUNTS", "not-an-address,checkorca.technician@example.com"),
        ("DEV_SEED_PASSWORD_ADMIN", ""),
        ("DEV_SEED_PASSWORD_TECHNICIAN", "too-short"),
    ],
)
@pytest.mark.usefixtures("seed_env")
def test_incomplete_seed_settings_are_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(SeedError) as caught:
        seed_accounts(load_settings())
    assert SEED_ADMIN_PASSWORD not in str(caught.value)


@pytest.mark.usefixtures("seed_env")
async def test_the_seed_ensures_both_accounts_and_is_idempotent(
    db_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        await ensure_seed_accounts(load_settings())
    found = await users(db_engine)
    assert {email: row.role for email, row in found.items()} == {
        SEED_ADMIN: "admin",
        SEED_TECHNICIAN: "technician",
    }
    # Only the fact is logged: no address, no password.
    assert "accounts ensured" in caplog.text
    for value in (SEED_ADMIN, SEED_TECHNICIAN, SEED_ADMIN_PASSWORD):
        assert value not in caplog.text

    await ensure_seed_accounts(load_settings())
    again = await users(db_engine)
    assert {email: row.id for email, row in again.items()} == {
        email: row.id for email, row in found.items()
    }
    assert {email: row.password_hash for email, row in again.items()} == {
        email: row.password_hash for email, row in found.items()
    }


@pytest.mark.usefixtures("seed_env")
async def test_the_seed_repairs_a_changed_account(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await ensure_seed_accounts(load_settings())
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE app_user SET role = 'technician', disabled = true, "
                "failed_logins = 5, locked_until = '2099-01-01T00:00:00Z' "
                "WHERE role = 'admin'"
            )
        )
    new_password = "Seed-admin-" + "3" * 12
    monkeypatch.setenv("DEV_SEED_PASSWORD_ADMIN", new_password)
    await ensure_seed_accounts(load_settings())
    admin = (await users(db_engine))[SEED_ADMIN]
    assert admin.role == "admin"
    assert admin.disabled is False
    assert admin.failed_logins == 0
    assert admin.locked_until is None

    application = create_app(load_settings(), static_dir=None, clock=FakeClock())
    async with running(application) as client:
        await sign_in(client, SEED_ADMIN, new_password)
        old = await client.post(
            "/api/v1/auth/login",
            json={"email": SEED_ADMIN, "password": SEED_ADMIN_PASSWORD},
        )
        assert old.status_code == 401


@pytest.mark.usefixtures("seed_env")
async def test_both_seed_accounts_sign_in_and_close_the_first_run(
    db_engine: AsyncEngine,
) -> None:
    await ensure_seed_accounts(load_settings())
    application = create_app(load_settings(), static_dir=None, clock=FakeClock())
    async with running(application) as client:
        state = await client.get("/api/v1/auth/setup-state")
        assert state.json() == {"needs_first_run": False}
        assert (await client.get("/api/v1/auth/first-run")).status_code == 404
        await sign_in(client, SEED_ADMIN, SEED_ADMIN_PASSWORD)
        me: httpx.Response = await client.get("/api/v1/auth/me")
        assert me.json()["role"] == "admin"
        await sign_in(client, SEED_TECHNICIAN, SEED_TECHNICIAN_PASSWORD)
        me = await client.get("/api/v1/auth/me")
        assert me.json()["role"] == "technician"


@pytest.mark.usefixtures("seed_env", "quiet_cli")
async def test_the_seed_command_runs_the_seed(db_engine: AsyncEngine) -> None:
    assert await run_cli(["seed"]) == 0
    assert set(await users(db_engine)) == {SEED_ADMIN, SEED_TECHNICIAN}
