"""exports/day.csv, exports/history.csv and clients/{id}/export.csv (phase
C8-B): golden files of the dashboard scenario (helpers.py), the limits, and
the canaries: no secret ever appears in an export or in the digest.

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.api.v1 import exports
from app.db.models import AppUser
from app.evaluator.tick import evaluate_jobs
from app.repos.settings import SettingsRepository
from app.security.crypto import SecretBox
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from app.worker.parse import ParseHook
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    MAIL_SECRET,
    TEST_FERNET_KEY,
    FakeClock,
    another_browser,
    build_scenario,
    deliver_mail,
    sign_in,
)

GOLDEN = Path(__file__).parent / "golden"
DENTAL = CLIENT_NAMES[0]
# Secrets nobody would type: if one shows up in an export, a secret leaked.
IMAP_CANARY = "Canary-imap-" + "q" * 16
HEARTBEAT_CANARY = "https://hb.example.test/Canary-heartbeat-" + "z" * 16
# Stands for the stored message's id (a new UUID each run) in the golden file.
MESSAGE_ID = "RAW-MESSAGE-ID"


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
async def worker(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


@pytest.fixture
async def jobs(
    client: httpx.AsyncClient, csrf: str, worker: WorkerContext, clock: FakeClock
) -> dict[str, dict[str, Any]]:
    async def tick() -> None:
        await evaluate_jobs(worker, clock.now())

    return await build_scenario(client, csrf, clock, tick)


async def mail_in(
    client: httpx.AsyncClient, csrf: str, worker: WorkerContext, clock: FakeClock
) -> str:
    """The nightly backup's alert mail (helpers.py), received and parsed."""
    return await deliver_mail(client, csrf, lambda: ParseHook()(worker, clock.now()))


def golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


def csv_text(response: httpx.Response) -> str:
    """The body without its byte order mark, with LF line ends."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.content.startswith(b"\xef\xbb\xbf")
    return response.content.decode("utf-8-sig").replace("\r\n", "\n")


async def test_the_day_export_matches_its_golden_file(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]]
) -> None:
    day = {"date": "2027-01-05"}
    response = await client.get("/api/v1/exports/day.csv", params=day)
    assert csv_text(response) == golden("day-2027-01-05.csv")
    disposition = response.headers["content-disposition"]
    assert disposition == 'attachment; filename="checkorca-day-2027-01-05.csv"'
    today = await client.get("/api/v1/exports/day.csv")
    lines = csv_text(today).splitlines()
    # Today (6 January) nothing was due yet: the header only.
    assert lines == [golden("day-2027-01-05.csv").splitlines()[0]]


async def test_the_history_export_matches_its_golden_file(
    client: httpx.AsyncClient, jobs: dict[str, dict[str, Any]]
) -> None:
    window = {"from": "2027-01-04", "to": "2027-01-05"}
    response = await client.get("/api/v1/exports/history.csv", params=window)
    assert csv_text(response) == golden("history-2027-01-04-2027-01-05.csv")
    dental = jobs["dump"]["client_id"]
    one = await client.get(
        "/api/v1/exports/history.csv", params=window | {"client_id": dental}
    )
    rows = csv_text(one).splitlines()[1:]
    assert len(rows) == 4 and all(f",{DENTAL}," in row for row in rows)
    default = await client.get("/api/v1/exports/history.csv")
    assert len(csv_text(default).splitlines()) == 9
    backwards = await client.get(
        "/api/v1/exports/history.csv", params={"from": "2027-01-05", "to": "2027-01-04"}
    )
    assert backwards.status_code == 422
    # At most 366 days, both included.
    longest = await client.get(
        "/api/v1/exports/history.csv", params={"from": "2026-01-06", "to": "2027-01-06"}
    )
    assert len(csv_text(longest).splitlines()) == 9
    too_long = await client.get(
        "/api/v1/exports/history.csv", params={"from": "2026-01-05", "to": "2027-01-06"}
    )
    assert too_long.status_code == 422
    unknown = await client.get(
        "/api/v1/exports/history.csv",
        params={"client_id": "00000000-0000-4000-8000-000000000000"},
    )
    assert unknown.status_code == 404


async def test_the_client_export_holds_the_full_history(
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    dental = jobs["dump"]["client_id"]
    headers = {CSRF_HEADER: csrf}
    changed = await client.patch(
        f"/api/v1/clients/{dental}",
        json={"notes": "Front desk opens at 08:00.", "aliases": ["FDC Main Office"]},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    archived = await client.post(
        f"/api/v1/jobs/{jobs['dump']['id']}/archive", headers=headers
    )
    assert archived.status_code == 200, archived.text
    message_id = await mail_in(client, csrf, worker, clock)
    response = await client.get(f"/api/v1/clients/{dental}/export.csv")
    text = csv_text(response).replace(message_id, MESSAGE_ID)
    assert text == golden("client-dental.csv")
    assert MAIL_SECRET not in text
    disposition = response.headers["content-disposition"]
    assert disposition == f'attachment; filename="checkorca-client-{dental}.csv"'
    missing = await client.get(
        "/api/v1/clients/00000000-0000-4000-8000-000000000000/export.csv"
    )
    assert missing.status_code == 404


async def test_a_formula_in_a_name_is_written_as_text(
    client: httpx.AsyncClient, csrf: str, jobs: dict[str, dict[str, Any]]
) -> None:
    renamed = await client.patch(
        f"/api/v1/jobs/{jobs['offsite']['id']}",
        json={"name": "=HYPERLINK(1)"},
        headers={CSRF_HEADER: csrf},
    )
    assert renamed.status_code == 200
    day = {"date": "2027-01-05"}
    response = await client.get("/api/v1/exports/day.csv", params=day)
    assert ",'=HYPERLINK(1)," in csv_text(response)


async def test_no_secret_appears_in_an_export_or_the_digest(
    client: httpx.AsyncClient,
    csrf: str,
    jobs: dict[str, dict[str, Any]],
    db_engine: AsyncEngine,
    worker: WorkerContext,
    clock: FakeClock,
) -> None:
    headers = {CSRF_HEADER: csrf}
    # A received mail whose relay header and body carry a secret.
    await mail_in(client, csrf, worker, clock)
    imap = await client.post(
        "/api/v1/inboxes",
        json={
            "kind": "imap",
            "label": "Shared alert mailbox",
            "imap": {
                "host": "imap.example.com",
                "username": "alerts@example.com",
                "password": IMAP_CANARY,
            },
        },
        headers=headers,
    )
    assert imap.status_code == 201
    webhook = await client.post(
        "/api/v1/inboxes", json={"kind": "webhook", "label": "Hook"}, headers=headers
    )
    webhook_token = webhook.json()["webhook_token"]
    tokens = []
    for scope in ("read", "ingest"):
        created = await client.post(
            "/api/v1/tokens", json={"label": scope, "scope": scope}, headers=headers
        )
        tokens.append(created.json()["token"])
    async with async_sessionmaker(db_engine)() as db:
        box = SecretBox(TEST_FERNET_KEY)
        await SettingsRepository(db, AllowAllPolicy(), box).set_external_heartbeat_url(
            SYSTEM, HEARTBEAT_CANARY
        )
        await db.commit()
    ping_tokens = [str(job["ping_url"]).rsplit("/", 1)[1] for job in jobs.values()]
    secrets = [IMAP_CANARY, HEARTBEAT_CANARY, webhook_token, *tokens, *ping_tokens]
    secrets += [hashlib.sha256(value.encode()).hexdigest() for value in secrets]
    secrets.append(MAIL_SECRET)

    texts = []
    for path in (
        "/api/v1/exports/day.csv?date=2027-01-05",
        "/api/v1/exports/history.csv?from=2027-01-01&to=2027-01-06",
    ):
        texts.append(csv_text(await client.get(path)))
    for job in jobs.values():
        export = await client.get(f"/api/v1/clients/{job['client_id']}/export.csv")
        texts.append(csv_text(export))
    preview = (await client.get("/api/v1/digest/preview")).json()
    texts += [preview["subject"], preview["html"], preview["text"]]
    for text in texts:
        for secret in secrets:
            assert secret not in text
    # The canaries are real: the IMAP password is stored (encrypted), and the
    # mail reached the client export (its subject is there, its secret not).
    assert imap.json()["imap"]["secret_set"] is True
    assert any("[Success] Nightly server backup" in text for text in texts)


async def test_an_export_over_the_row_limit_is_refused_not_cut(
    client: httpx.AsyncClient,
    jobs: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Three rows at most: 5 January has four runs, the dental clinic four
    # occurrences and four results; the freight company two of each kind.
    monkeypatch.setattr(exports, "MAX_ROWS", 3)
    dental = jobs["dump"]["client_id"]
    freight = jobs["offsite"]["client_id"]
    for path in (
        "/api/v1/exports/day.csv?date=2027-01-05",
        "/api/v1/exports/history.csv?from=2027-01-04&to=2027-01-05",
        f"/api/v1/clients/{dental}/export.csv",
    ):
        refused = await client.get(path)
        assert refused.status_code == 422, path
        assert refused.json()["title"] == "Export too large"
    allowed = await client.get(f"/api/v1/clients/{freight}/export.csv")
    assert allowed.status_code == 200


async def test_exports_need_a_reader(
    app: FastAPI,
    client: httpx.AsyncClient,
    jobs: dict[str, dict[str, Any]],
    csrf: str,
) -> None:
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Reports", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    dental = jobs["dump"]["client_id"]
    async with another_browser(app) as anonymous:
        for path in (
            "/api/v1/exports/day.csv",
            "/api/v1/exports/history.csv",
            f"/api/v1/clients/{dental}/export.csv",
        ):
            assert (await anonymous.get(path)).status_code == 401
            assert (await anonymous.get(path, headers=bearer)).status_code == 200
