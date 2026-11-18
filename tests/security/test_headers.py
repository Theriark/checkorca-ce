"""Security headers, the request id and problem documents on every answer."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.security.headers import CONTENT_SECURITY_POLICY
from app.settings import load_settings
from helpers import running

EXPECTED = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
}


def assert_security_headers(response: httpx.Response) -> None:
    for name, value in EXPECTED.items():
        assert response.headers.get_list(name) == [value], name


def test_the_policy_allows_no_inline_or_foreign_script() -> None:
    directives = dict(
        part.strip().split(" ", 1) for part in CONTENT_SECURITY_POLICY.split(";")
    )
    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"
    assert "unsafe" not in directives["script-src"] + directives["default-src"]


@pytest.mark.parametrize(
    "path", ["/healthz", "/api/v1/auth/me", "/api/v1/nowhere", "/", "/index.html"]
)
async def test_every_answer_carries_the_headers(tmp_path: Path, path: str) -> None:
    (tmp_path / "index.html").write_text("<title>Checkorca-CE</title>")
    application = create_app(load_settings(), static_dir=tmp_path)
    async with running(application) as client:
        response = await client.get(path)
    assert_security_headers(response)
    assert len(response.headers["x-request-id"]) == 32


async def test_api_answers_are_not_cached(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/setup-state")
    assert response.headers["cache-control"] == "no-store"
    health = await client.get("/healthz")
    assert "cache-control" not in health.headers


async def test_a_safe_request_id_is_kept_and_an_unsafe_one_replaced(
    client: httpx.AsyncClient,
) -> None:
    kept = await client.get("/healthz", headers={"X-Request-ID": "proxy-id-0001"})
    assert kept.headers["x-request-id"] == "proxy-id-0001"
    replaced = await client.get("/healthz", headers={"X-Request-ID": "not a safe id!"})
    assert replaced.headers["x-request-id"] != "not a safe id!"
    assert len(replaced.headers["x-request-id"]) == 32


async def test_unknown_routes_answer_with_problem_details(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/nowhere")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["title"] == "Not Found"
    assert problem["instance"] == "/api/v1/nowhere"
    assert problem["request_id"] == response.headers["x-request-id"]
    wrong_method = await client.put("/api/v1/auth/me")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["status"] == 405


async def test_an_unhandled_error_answers_500_with_a_request_id(
    app: FastAPI, db_engine: object
) -> None:
    @app.get("/test-only/boom")
    async def boom() -> None:
        raise RuntimeError("synthetic failure")

    async with running(app) as client:
        response = await client.get("/test-only/boom")
    assert response.status_code == 500
    problem = response.json()
    assert problem["title"] == "Internal Server Error"
    assert problem["request_id"] == response.headers["x-request-id"]
    assert "synthetic failure" not in response.text
    assert_security_headers(response)
