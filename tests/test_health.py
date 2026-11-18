"""/healthz, /readyz and the web app mount."""

from pathlib import Path

import pytest

from app import __version__
from app.main import create_app
from app.settings import load_settings
from helpers import UNREACHABLE_DATABASE_URL, running

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


async def test_readyz_answers_200_when_the_database_answers() -> None:
    async with running(create_app(load_settings(), static_dir=None)) as client:
        response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


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
