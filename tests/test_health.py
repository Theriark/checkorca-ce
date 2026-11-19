"""/healthz, /readyz and the web app mount."""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app import __version__
from app.access import SYSTEM, AccessDenied, Action, AllowAllPolicy, Principal
from app.main import create_app
from app.repos.heartbeat import HeartbeatRepository
from app.settings import load_settings
from helpers import UNREACHABLE_DATABASE_URL, FakeClock, running

REVISION = "0123456789abcdef0123456789abcdef01234567"


def test_version_is_the_first_release() -> None:
    assert __version__ == "27.0.0"


async def test_healthz_reports_status_version_and_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVISION", REVISION)
    async with running(create_app(load_settings(), static_dir=None)) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "27.0.0",
        "revision": REVISION,
    }


async def test_healthz_without_revision_reports_null() -> None:
    async with running(create_app(load_settings(), static_dir=None)) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["revision"] is None


async def beat(engine: AsyncEngine, at: datetime) -> None:
    """Write the heartbeat row as the worker does."""
    async with async_sessionmaker(engine)() as db:
        await HeartbeatRepository(db, AllowAllPolicy()).beat(
            SYSTEM, at=at, holder="test-host pid 1", started_at=at
        )
        await db.commit()


async def test_readyz_needs_a_heartbeat_younger_than_3_minutes(
    db_engine: AsyncEngine, clock: FakeClock
) -> None:
    app = create_app(load_settings(), static_dir=None, clock=clock)
    async with running(app) as client:
        missing = await client.get("/readyz")
        assert missing.status_code == 503
        assert missing.json() == {
            "status": "unavailable",
            "database": "ok",
            "worker": "missing",
        }

        await beat(db_engine, clock.now())
        clock.advance(minutes=2, seconds=59)
        fresh = await client.get("/readyz")
        assert fresh.status_code == 200
        assert fresh.json() == {"status": "ready", "database": "ok", "worker": "ok"}

        clock.advance(seconds=1)
        stale = await client.get("/readyz")
        assert stale.status_code == 503
        assert stale.json()["worker"] == "stale"

        # The next tick makes it ready again.
        await beat(db_engine, clock.now())
        assert (await client.get("/readyz")).status_code == 200


async def test_readyz_is_not_ready_when_the_heartbeat_cannot_be_read(
    db_engine: AsyncEngine,
) -> None:
    class Refuses(AllowAllPolicy):
        def check(self, principal: Principal, action: Action) -> None:
            raise AccessDenied(action.resource)

    app = create_app(load_settings(), static_dir=None, policy=Refuses())
    async with running(app) as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["worker"] == "unknown"


async def test_readyz_answers_503_without_a_database() -> None:
    settings = load_settings(database_url=UNREACHABLE_DATABASE_URL)
    async with running(create_app(settings, static_dir=None)) as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}


async def test_serves_the_built_web_app_beside_the_api(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>Checkorca-CE</title>")
    async with running(create_app(load_settings(), static_dir=tmp_path)) as client:
        page = await client.get("/")
        health = await client.get("/healthz")
    assert page.status_code == 200
    assert "<title>Checkorca-CE</title>" in page.text
    assert health.json()["status"] == "ok"


async def test_no_web_app_mount_without_a_build(tmp_path: Path) -> None:
    async with running(create_app(load_settings(), static_dir=tmp_path)) as client:
        response = await client.get("/")
    assert response.status_code == 404


def test_create_app_reads_the_environment_by_default() -> None:
    app = create_app(static_dir=None)
    assert app.version == "27.0.0"
