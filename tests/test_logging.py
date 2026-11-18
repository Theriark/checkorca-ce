"""JSON logs with the request id; ids, never content or secrets (D-6, D-7)."""

import io
import json
import logging
import sys
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from app.logging import (
    REDACTED,
    JsonFormatter,
    configure_logging,
    quiet_libraries,
    request_id_var,
)
from app.settings import known_secrets, load_settings
from helpers import ADMIN_EMAIL, CSRF_HEADER, running

# A secret that must never reach a log line: used as a password, in a rejected
# body and in the text of an unhandled error.
CANARY = "Canary-" + "q" * 16
SYNTHETIC_DATABASE_URL = "postgresql+asyncpg://u:synthetic-db-password@db.test/x"


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    """Every record at debug level, formatted as in production but unredacted,
    so the test proves the code never logs the canary in the first place."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    quiet_libraries()
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(level)


def record(message: str, **extra: object) -> logging.LogRecord:
    entry = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, (), None)
    entry.__dict__.update(extra)
    return entry


def test_a_line_is_one_json_object_with_the_request_id() -> None:
    token = request_id_var.set("req-0001")
    try:
        line = JsonFormatter().format(record("seed done", accounts=2))
    finally:
        request_id_var.reset(token)
    entry = json.loads(line)
    assert entry["message"] == "seed done"
    assert entry["level"] == "info"
    assert entry["logger"] == "app.test"
    assert entry["request_id"] == "req-0001"
    assert entry["accounts"] == 2
    assert entry["at"].endswith("Z")


def test_an_exception_keeps_its_class_and_frames_but_not_its_text() -> None:
    try:
        raise ValueError(f"INSERT ... parameters ({CANARY})")
    except ValueError:
        entry = record("failed")
        entry.exc_info = sys.exc_info()
    line = JsonFormatter().format(entry)
    parsed = json.loads(line)
    assert parsed["error"] == "ValueError"
    assert "test_logging.py" in parsed["stack"]
    assert CANARY not in line


def test_known_secrets_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_SEED_PASSWORD_ADMIN", CANARY)
    settings = load_settings(database_url=SYNTHETIC_DATABASE_URL)
    secrets = known_secrets(settings)
    assert CANARY in secrets
    assert settings.secret_key.get_secret_value() in secrets
    assert "synthetic-db-password" in secrets
    line = JsonFormatter(secrets).format(record(f"oops {CANARY} and \\"))
    assert CANARY not in line
    assert REDACTED in line


def test_configure_logging_installs_one_json_handler() -> None:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        configure_logging("warning", ["x" * 10])
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.WARNING
        assert logging.getLogger("uvicorn.error").propagate
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)


async def test_no_canary_in_the_logs_of_the_auth_flows(
    app: FastAPI, log_stream: io.StringIO
) -> None:
    @app.get("/test-only/boom")
    async def boom() -> None:
        raise RuntimeError(f"failure while handling {CANARY}")

    async with running(app) as client:
        created = await client.post(
            "/api/v1/auth/first-run", json={"email": ADMIN_EMAIL, "password": CANARY}
        )
        assert created.status_code == 201
        csrf = created.json()["csrf_token"]
        wrong = await client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": CANARY + "x"},
        )
        assert wrong.status_code == 401
        invalid = await client.post(
            "/api/v1/users",
            json={"email": ADMIN_EMAIL, "password": CANARY, "role": CANARY},
            headers={CSRF_HEADER: csrf},
        )
        assert invalid.status_code == 422
        assert CANARY not in invalid.text
        issued = await client.post(
            "/api/v1/tokens",
            json={"label": "canary check", "scope": "read"},
            headers={CSRF_HEADER: csrf},
        )
        value = issued.json()["token"]
        assert (await client.get("/test-only/boom")).status_code == 500
        await client.get("/api/v1/users", headers={"Authorization": f"Bearer {value}"})

    output = log_stream.getvalue()
    lines = [json.loads(line) for line in output.splitlines()]
    assert any(line.get("route") == "/api/v1/auth/login" for line in lines)
    assert any(line.get("error") == "RuntimeError" for line in lines)
    for forbidden in (CANARY, value, ADMIN_EMAIL, csrf):
        assert forbidden not in output
    for line in lines:
        if line["message"] == "request":
            assert line["request_id"]


async def test_the_access_log_names_templates_not_paths(
    client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    await client.get("/api/v1/users/00000000-0000-4000-8000-000000000000?q=x")
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    routes = [line["route"] for line in lines if line["message"] == "request"]
    assert routes == ["/api/v1/users/{user_id}"]
    assert "00000000-0000-4000-8000-000000000000" not in log_stream.getvalue()
