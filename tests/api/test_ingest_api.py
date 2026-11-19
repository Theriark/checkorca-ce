"""The HTTP receivers: POST ingest/email, POST results, the ping URLs and the
.eml upload, with token scopes, limits, duplicates and the log canary. Mail,
names and addresses are synthetic (R-11)."""

import logging
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AppUser
from app.ingest.store import MAX_MESSAGE_BYTES
from app.logging import JsonFormatter, quiet_libraries
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    another_browser,
    make_client,
    make_job,
    sign_in,
)

DENTAL = CLIENT_NAMES[0]
JOB = "Nightly server backup"


def veeam_style(number: int = 1, sender: str = "backup@example.com") -> bytes:
    """A synthetic Veeam-style job report (written for the test, not copied)."""
    return (
        f"From: Backup Server <{sender}>\r\n"
        "To: alerts@example.com\r\n"
        f"Subject: [Success] {JOB} (synthetic {number})\r\n"
        "Date: Mon, 4 Jan 2027 06:29:00 +0000\r\n"
        f"Message-ID: <ingest-{number}@backup.example.com>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"Job {JOB} for {DENTAL} finished: Success\r\n"
    ).encode()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def new_token(client: httpx.AsyncClient, csrf: str, scope: str) -> str:
    response = await client.post(
        "/api/v1/tokens",
        json={"label": f"{scope} script", "scope": scope},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 201, response.text
    token: str = response.json()["token"]
    return token


async def new_inbox(
    client: httpx.AsyncClient, csrf: str, kind: str, **fields: Any
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/inboxes",
        json={"kind": kind, "label": f"Synthetic {kind} inbox", **fields},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 201, response.text
    inbox: dict[str, Any] = response.json()
    return inbox


def ingest_path(inbox: dict[str, Any]) -> str:
    return "/api/v1/ingest/email/" + str(inbox["ingest_url"]).rsplit("/", 1)[1]


async def message_rows(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        count = await connection.scalar(text("SELECT count(*) FROM raw_message"))
    return int(count or 0)


async def test_raw_mail_with_an_ingest_token_is_stored_once(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    token = await new_token(client, csrf, "ingest")
    inbox = await new_inbox(client, csrf, "smtp")
    path = ingest_path(inbox)
    headers = {**bearer(token), "Content-Type": "message/rfc822"}
    first = await client.post(path, content=veeam_style(), headers=headers)
    assert first.status_code == 202, first.text
    assert first.json()["duplicate"] is False
    # The same Message-ID again: accepted, one row.
    again = await client.post(path, content=veeam_style(), headers=headers)
    assert again.status_code == 202
    assert again.json() == {"message_id": first.json()["message_id"], "duplicate": True}
    assert await message_rows(db_engine) == 1
    listed = (await client.get("/api/v1/messages")).json()["items"]
    assert [item["id"] for item in listed] == [first.json()["message_id"]]
    assert listed[0]["subject"] == f"[Success] {JOB} (synthetic 1)"
    assert listed[0]["inbox_id"] == inbox["id"]


async def test_ingest_needs_an_ingest_scope_token(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    inbox = await new_inbox(client, csrf, "smtp")
    path = ingest_path(inbox)
    read = await new_token(client, csrf, "read")
    refused = await client.post(path, content=veeam_style(), headers=bearer(read))
    assert refused.status_code == 403
    assert (await client.post(path, content=veeam_style())).status_code == 401
    unknown = bearer("chk_" + "u" * 32)
    invalid = await client.post(path, content=veeam_style(), headers=unknown)
    assert invalid.status_code == 401
    assert await message_rows(db_engine) == 0


async def test_an_unknown_inbox_code_is_404(
    client: httpx.AsyncClient, csrf: str
) -> None:
    token = await new_token(client, csrf, "ingest")
    path = "/api/v1/ingest/email/" + "a" * 24
    unknown = await client.post(path, content=veeam_style(), headers=bearer(token))
    assert unknown.status_code == 404
    assert unknown.headers["content-type"] == "application/problem+json"


async def test_a_webhook_inbox_token_writes_only_to_its_inbox(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    webhook = await new_inbox(client, csrf, "webhook")
    other = await new_inbox(client, csrf, "webhook")
    smtp = await new_inbox(client, csrf, "smtp")
    own = bearer(webhook["webhook_token"])
    stored = await client.post(ingest_path(webhook), content=veeam_style(), headers=own)
    assert stored.status_code == 202
    for target in (other, smtp):
        path = ingest_path(target)
        refused = await client.post(path, content=veeam_style(2), headers=own)
        assert refused.status_code == 403
    # A rotated token stops working at once.
    rotated = await client.post(
        f"/api/v1/inboxes/{webhook['id']}/token", headers={CSRF_HEADER: csrf}
    )
    assert rotated.status_code == 200
    old = await client.post(ingest_path(webhook), content=veeam_style(3), headers=own)
    assert old.status_code == 401
    fresh = bearer(rotated.json()["webhook_token"])
    path = ingest_path(webhook)
    renewed = await client.post(path, content=veeam_style(3), headers=fresh)
    assert renewed.status_code == 202
    assert await message_rows(db_engine) == 2


async def test_size_empty_and_non_mail_bodies_are_refused(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    token = await new_token(client, csrf, "ingest")
    path = ingest_path(await new_inbox(client, csrf, "smtp"))
    big = veeam_style() + b"x" * MAX_MESSAGE_BYTES
    too_large = await client.post(path, content=big, headers=bearer(token))
    assert too_large.status_code == 413
    for body in (b"", b"just some words, no headers", b"\x89PNG\r\n\x1a\n"):
        refused = await client.post(path, content=body, headers=bearer(token))
        assert refused.status_code == 422, body
        assert refused.json()["title"] == "Not an e-mail message"
    assert await message_rows(db_engine) == 0


async def test_the_sender_allowlist_refuses_with_422(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    token = await new_token(client, csrf, "ingest")
    inbox = await new_inbox(client, csrf, "smtp", sender_allowlist=["@example.com"])
    path = ingest_path(inbox)
    intruder = veeam_style(sender="intruder@attacker.test")
    refused = await client.post(path, content=intruder, headers=bearer(token))
    assert refused.status_code == 422
    assert refused.json()["title"] == "Message refused"
    assert "attacker" not in refused.text
    allowed = await client.post(path, content=veeam_style(), headers=bearer(token))
    assert allowed.status_code == 202
    assert await message_rows(db_engine) == 1


async def test_an_html_only_mail_is_shown_as_text_without_script(
    client: httpx.AsyncClient, csrf: str
) -> None:
    token = await new_token(client, csrf, "ingest")
    path = ingest_path(await new_inbox(client, csrf, "smtp"))
    html = (
        b"From: backup@example.com\r\nSubject: HTML report\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<html><head><script>alert(document.cookie)</script></head>"
        b"<body><p>Job <b>Nightly server backup</b>: Failed</p>"
        b'<img src=x onerror="alert(1)"></body></html>'
    )
    stored = await client.post(path, content=html, headers=bearer(token))
    detail = await client.get(f"/api/v1/messages/{stored.json()['message_id']}")
    assert detail.json()["text"] == "Job Nightly server backup: Failed"
    assert "<" not in detail.json()["text"] and "alert" not in detail.json()["text"]


async def job_with_token(
    client: httpx.AsyncClient, csrf: str, name: str = JOB
) -> tuple[str, str]:
    """A job of the dental clinic and its ping token."""
    found = await client.get("/api/v1/clients", params={"q": DENTAL})
    owners = found.json()["items"]
    owner = owners[0] if owners else await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, owner["id"], name)
    return job["id"], str(job["ping_url"]).rsplit("/", 1)[1]


async def job_results(client: httpx.AsyncClient, job_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/api/v1/jobs/{job_id}/results")
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_results_by_job_id_ping_token_or_names(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    token = await new_token(client, csrf, "ingest")
    job_id, ping_token = await job_with_token(client, csrf)
    by_id = await client.post(
        "/api/v1/results",
        json={
            "status": "warning",
            "job_id": job_id,
            "started_at": "2027-01-04T05:00:00Z",
            "finished_at": "2027-01-04T05:41:07+00:00",
            "run_id": "run-0001",
            "details": {"processed_gb": 12, "skipped": ["C:\\pagefile.sys"]},
        },
        headers=bearer(token),
    )
    assert by_id.status_code == 202, by_id.text
    assert by_id.json()["job_id"] == job_id
    clock.advance(seconds=1)
    by_ping = await client.post(
        "/api/v1/results",
        json={"status": "failed", "ping_token": ping_token},
        headers=bearer(token),
    )
    assert by_ping.status_code == 202 and by_ping.json()["job_id"] == job_id
    clock.advance(seconds=1)
    by_names = await client.post(
        "/api/v1/results",
        json={"status": "success", "client_hint": DENTAL, "job_name": JOB},
        headers=bearer(token),
    )
    assert by_names.status_code == 202 and by_names.json()["job_id"] is None
    results = await job_results(client, job_id)
    assert [item["status"] for item in results] == ["failed", "warning"]
    assert results[1]["finished_at"] == "2027-01-04T05:41:07Z"
    details = {"processed_gb": 12, "skipped": ["C:\\pagefile.sys"]}
    assert results[1]["details"] == details
    everything = (await client.get("/api/v1/results")).json()["items"]
    assert everything[0]["job_name"] == JOB and everything[0]["job_id"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"status": "success"},
        {"status": "success", "client_hint": DENTAL},
        {"status": "done", "client_hint": DENTAL, "job_name": JOB},
        {"status": "success", "job_name": JOB, "client_hint": DENTAL, "x": 1},
        {
            "status": "success",
            "client_hint": DENTAL,
            "job_name": JOB,
            "finished_at": "2027-01-04T05:41:07",
        },
        {"status": "success", "client_hint": DENTAL, "job_name": "j" * 201},
        {
            "status": "success",
            "client_hint": DENTAL,
            "job_name": JOB,
            "details": {"log": "x" * 17_000},
        },
    ],
)
async def test_invalid_results_are_422(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, body: dict[str, Any]
) -> None:
    token = await new_token(client, csrf, "ingest")
    response = await client.post("/api/v1/results", json=body, headers=bearer(token))
    assert response.status_code == 422, response.text
    async with db_engine.connect() as connection:
        count = await connection.scalar(text("SELECT count(*) FROM job_result"))
    assert count == 0


async def test_results_need_a_known_job_and_an_ingest_token(
    client: httpx.AsyncClient, csrf: str
) -> None:
    token = await new_token(client, csrf, "ingest")
    job_id, ping_token = await job_with_token(client, csrf)
    both = {"status": "success", "job_id": job_id, "ping_token": ping_token}
    twice = await client.post("/api/v1/results", json=both, headers=bearer(token))
    assert twice.status_code == 422
    for reference in (
        {"job_id": "00000000-0000-4000-8000-000000000000"},
        {"ping_token": "Z" * 24},
    ):
        body = {"status": "success", **reference}
        missing = await client.post("/api/v1/results", json=body, headers=bearer(token))
        assert missing.status_code == 404
    read = await new_token(client, csrf, "read")
    body = {"status": "success", "job_id": job_id}
    refused = await client.post("/api/v1/results", json=body, headers=bearer(read))
    assert refused.status_code == 403


async def test_ping_start_then_success_then_fail(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    job_id, ping_token = await job_with_token(client, csrf)
    start = await client.get(f"/api/v1/ping/{ping_token}/start")
    assert (start.status_code, start.text) == (200, "OK")
    assert start.headers["content-type"].startswith("text/plain")
    clock.advance(minutes=41)
    success = await client.post(f"/api/v1/ping/{ping_token}")
    assert (success.status_code, success.text) == (200, "OK")
    clock.advance(minutes=1)
    fail = await client.get(f"/api/v1/ping/{ping_token}/fail")
    assert fail.status_code == 200
    results = await job_results(client, job_id)
    assert [item["status"] for item in results] == ["failed", "success", "started"]
    assert all(item["details"] == {"source": "ping"} for item in results)


async def test_a_ping_with_an_unknown_or_malformed_token(
    client: httpx.AsyncClient,
) -> None:
    unknown = await client.get("/api/v1/ping/" + "Z" * 24)
    assert unknown.status_code == 404
    assert unknown.json()["title"] == "Ping URL not found"
    assert (await client.get("/api/v1/ping/bad-token!")).status_code == 422
    assert (await client.get("/api/v1/ping/" + "Z" * 65)).status_code == 422
    assert (await client.get("/api/v1/ping/" + "Z" * 24 + "/done")).status_code == 422


async def test_ping_urls_allow_120_requests_a_minute_per_token(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    _, ping_token = await job_with_token(client, csrf)
    url = f"/api/v1/ping/{ping_token}"
    codes = [(await client.get(url)).status_code for _ in range(120)]
    assert codes == [200] * 120
    limited = await client.get(url)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    # Another token has its own bucket; the first refills over time.
    _, other = await job_with_token(client, csrf, "Weekly archive")
    assert (await client.get(f"/api/v1/ping/{other}")).status_code == 200
    clock.advance(seconds=1)
    assert (await client.get(url)).status_code == 200


async def test_a_webhook_token_allows_120_messages_a_minute(
    client: httpx.AsyncClient, csrf: str
) -> None:
    webhook = await new_inbox(client, csrf, "webhook")
    headers = bearer(webhook["webhook_token"])
    path = ingest_path(webhook)
    codes = [
        (await client.post(path, content=veeam_style(n), headers=headers)).status_code
        for n in range(121)
    ]
    assert codes == [202] * 120 + [429]


async def test_eml_upload_with_csrf_stores_into_the_inbox(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    inbox = await new_inbox(client, csrf, "upload")
    files = {"file": ("report.eml", veeam_style(), "message/rfc822")}
    data = {"inbox_id": inbox["id"]}
    refused = await client.post("/api/v1/messages/upload", files=files, data=data)
    assert refused.status_code == 403
    uploaded = await client.post(
        "/api/v1/messages/upload", files=files, data=data, headers={CSRF_HEADER: csrf}
    )
    assert uploaded.status_code == 202, uploaded.text
    assert uploaded.json()["duplicate"] is False
    again = await client.post(
        "/api/v1/messages/upload", files=files, data=data, headers={CSRF_HEADER: csrf}
    )
    assert again.json() == {
        "message_id": uploaded.json()["message_id"],
        "duplicate": True,
    }
    assert await message_rows(db_engine) == 1
    async with db_engine.connect() as connection:
        actions = await connection.scalars(
            text("SELECT action FROM audit_event WHERE action = 'message.upload'")
        )
        assert list(actions) == ["message.upload", "message.upload"]


async def test_upload_and_ingest_of_one_message_give_one_row(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    token = await new_token(client, csrf, "ingest")
    inbox = await new_inbox(client, csrf, "smtp")
    ingested = await client.post(
        ingest_path(inbox), content=veeam_style(), headers=bearer(token)
    )
    uploaded = await client.post(
        "/api/v1/messages/upload",
        files={"file": ("copy.eml", veeam_style(), "message/rfc822")},
        data={"inbox_id": inbox["id"]},
        headers={CSRF_HEADER: csrf},
    )
    assert uploaded.json() == {**ingested.json(), "duplicate": True}
    assert await message_rows(db_engine) == 1


async def test_upload_refuses_unknown_inboxes_other_files_and_oversize(
    app: FastAPI, client: httpx.AsyncClient, technician: AppUser, csrf: str
) -> None:
    inbox = await new_inbox(client, csrf, "upload")
    tech = another_browser(app)
    async with tech:
        tech_csrf = await sign_in(tech, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
        headers = {CSRF_HEADER: tech_csrf}

        async def upload(content: bytes, inbox_id: str = inbox["id"]) -> httpx.Response:
            return await tech.post(
                "/api/v1/messages/upload",
                files={"file": ("x.eml", content, "message/rfc822")},
                data={"inbox_id": inbox_id},
                headers=headers,
            )

        assert (await upload(veeam_style())).status_code == 202
        unknown = await upload(veeam_style(2), "00000000-0000-4000-8000-000000000000")
        assert unknown.status_code == 404
        assert (await upload(b"%PDF-1.7 not a message")).status_code == 422
        too_large = await upload(veeam_style(3) + b"x" * MAX_MESSAGE_BYTES)
        assert too_large.status_code == 413


async def test_no_token_address_code_or_content_in_the_logs(
    client: httpx.AsyncClient, csrf: str, caplog: pytest.LogCaptureFixture
) -> None:
    canary = "Canary-" + "h" * 16
    token = await new_token(client, csrf, "ingest")
    inbox = await new_inbox(client, csrf, "smtp")
    _, ping_token = await job_with_token(client, csrf)
    code = ingest_path(inbox).rsplit("/", 1)[1]
    quiet_libraries()
    caplog.set_level(logging.DEBUG)
    body = veeam_style().replace(b"finished: Success", canary.encode())
    await client.post(ingest_path(inbox), content=body, headers=bearer(token))
    await client.post(f"/api/v1/ping/{ping_token}/start")
    await client.post(
        "/api/v1/results",
        json={"status": "failed", "client_hint": canary, "job_name": JOB},
        headers=bearer(token),
    )
    routes = [getattr(record, "route", None) for record in caplog.records]
    assert "/api/v1/ingest/email/{inbox_code}" in routes
    assert "/api/v1/ping/{ping_token}/{signal}" in routes
    # As written in production: the message and every extra field.
    output = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    for forbidden in (canary, token, code, ping_token, "backup@example.com"):
        assert forbidden not in output
