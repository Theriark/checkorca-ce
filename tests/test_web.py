"""The single-page fallback: deep links get index.html, /api/ never gets HTML."""

from pathlib import Path

import httpx
import pytest

from app.main import create_app
from app.security.headers import CONTENT_SECURITY_POLICY
from app.settings import load_settings
from helpers import running

INDEX = "<!doctype html><title>Checkorca-CE</title><div id=root></div>"
SCRIPT = "console.log('synthetic bundle');"


@pytest.fixture
def build(tmp_path: Path) -> Path:
    """A stand-in for frontend/dist."""
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "main-abc123.js").write_text(SCRIPT)
    (tmp_path / "brand").mkdir()
    return tmp_path


def assert_security_headers(response: httpx.Response) -> None:
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/login",
        "/first-run",
        "/clients/0b5e3f9e-6a51-4c43-9d43-2b4f1a7c3e10",
        "/jobs?client=1",
        "/brand",
        "/assets/missing.js",
        "/apiary",
    ],
)
async def test_deep_links_answer_200_with_the_app(build: Path, path: str) -> None:
    async with running(create_app(load_settings(), static_dir=build)) as client:
        response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX
    assert response.headers["cache-control"] == "no-cache"
    assert_security_headers(response)


async def test_a_built_file_is_served_as_itself(build: Path) -> None:
    async with running(create_app(load_settings(), static_dir=build)) as client:
        response = await client.get("/assets/main-abc123.js")
        head = await client.head("/login")
    assert response.status_code == 200
    assert response.text == SCRIPT
    assert "javascript" in response.headers["content-type"]
    assert_security_headers(response)
    assert head.status_code == 200
    assert head.content == b""


@pytest.mark.parametrize(
    "path", ["/api/v1/nope", "/api", "/api/", "/api/v2/clients", "/api/v1/../login"]
)
async def test_unknown_api_paths_are_404_problem_documents(
    build: Path, path: str
) -> None:
    async with running(create_app(load_settings(), static_dir=build)) as client:
        response = await client.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404
    assert "<title>" not in response.text
    assert_security_headers(response)


async def test_other_methods_never_get_the_app(build: Path) -> None:
    async with running(create_app(load_settings(), static_dir=build)) as client:
        posted = await client.post("/login")
        wrong_method = await client.put("/api/v1/auth/me")
    assert posted.status_code == 404
    assert posted.headers["content-type"] == "application/problem+json"
    assert wrong_method.status_code == 405
    assert wrong_method.headers["content-type"] == "application/problem+json"


async def test_path_traversal_stays_inside_the_build(
    build: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    secret = tmp_path_factory.mktemp("outside") / "secret.txt"
    secret.write_text("synthetic secret")
    async with running(create_app(load_settings(), static_dir=build)) as client:
        response = await client.get(f"/..%2F{secret.parent.name}%2Fsecret.txt")
    assert "synthetic secret" not in response.text
