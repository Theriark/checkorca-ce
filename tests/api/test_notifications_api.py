"""channels, channel-rules, notifications, settings and system/status queues
(phase C9-B), and acknowledged_by on the jobs.

The relay password is write-only (legal D-6): a canary value goes in and must
never come out of the API, the logs, the audit trail, the exports or the
digest. The relay is a capturing SMTP server on 127.0.0.1. Every name and
address is synthetic (legal R-11).
"""

import logging
import socket
import uuid
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.models import AppUser, AuditEvent, Channel
from app.main import create_app
from app.repos.notifications import NotificationRepository
from app.security.crypto import MASK
from app.settings import load_settings
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    HttpCapture,
    RelayCapture,
    another_browser,
    http_answer,
    make_client,
    make_job,
    running,
    sign_in,
    smtp_relay,
)

DENTAL, FREIGHT, _ = CLIENT_NAMES
CANARY = "Canary-relay-" + "c" * 20
RELAY_USER = "alerts-relay"
EMAIL_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 2525,
    "starttls": False,
    "from_address": "checkorca@example.com",
    "to": ["ops@example.com"],
}


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def headers(csrf: str) -> dict[str, str]:
    return {CSRF_HEADER: csrf}


async def make_channel(
    client: httpx.AsyncClient, csrf: str, **fields: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"kind": "email", "label": "Ops mail"}
    body["config"] = EMAIL_CONFIG
    response = await client.post(
        "/api/v1/channels", json=body | fields, headers=headers(csrf)
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def make_rule(
    client: httpx.AsyncClient, csrf: str, channel_id: str, **fields: Any
) -> httpx.Response:
    body: dict[str, Any] = {"channel_id": channel_id, "events": ["missed"]}
    return await client.post(
        "/api/v1/channel-rules", json=body | fields, headers=headers(csrf)
    )


async def test_channels_keep_the_secret_write_only(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    created = await make_channel(
        client,
        csrf,
        config=EMAIL_CONFIG | {"username": RELAY_USER, "host": "SMTP.example.com"},
        secret=CANARY,
    )
    assert created["kind"] == "email" and created["enabled"] is True
    assert created["available"] is True
    assert created["secret_label"] == "Relay password"
    assert created["secret_set"] is True
    # The mask only, not the last characters of a chosen password.
    assert created["secret_hint"] == MASK
    assert created["config"]["host"] == "smtp.example.com"
    assert created["config"]["username"] == RELAY_USER
    assert created["last_status"] is None
    listed = await client.get("/api/v1/channels")
    one = await client.get(f"/api/v1/channels/{created['id']}")
    for response in (listed, one):
        assert response.status_code == 200
        assert CANARY not in response.text
    assert listed.json()["items"][0]["id"] == created["id"]
    # Nor in the exports, the digest or the activity timeline (D-6).
    for shown in (
        "/api/v1/exports/day.csv",
        "/api/v1/exports/history.csv",
        "/api/v1/digest/preview",
        "/api/v1/activity",
        "/api/v1/notifications",
    ):
        response = await client.get(shown)
        assert response.status_code == 200 and CANARY not in response.text
    async with db_engine.connect() as connection:
        stored = (await connection.execute(select(Channel.secret_enc))).scalar_one()
        audit = (await connection.execute(select(AuditEvent.details))).scalars().all()
    assert stored is not None and CANARY not in stored
    assert all(CANARY not in str(details) for details in audit)

    path = f"/api/v1/channels/{created['id']}"
    # A new host without the password again would send it to that host.
    moved = await client.patch(
        path, json={"config": {"host": "relay.example.net"}}, headers=headers(csrf)
    )
    assert moved.status_code == 422
    assert moved.json()["errors"][0]["field"] == "body.secret"
    assert "relay password again" in moved.json()["detail"]
    renamed = await client.patch(
        path,
        json={"label": "Night shift", "config": {"to": ["noc@example.com"]}},
        headers=headers(csrf),
    )
    assert renamed.status_code == 200
    assert renamed.json()["label"] == "Night shift"
    assert renamed.json()["config"]["to"] == ["noc@example.com"]
    resent = await client.patch(
        path,
        json={"config": {"host": "relay.example.net"}, "secret": CANARY + "x"},
        headers=headers(csrf),
    )
    assert resent.status_code == 200
    assert resent.json()["secret_hint"] == MASK
    # Without a user name the password can go: an empty secret removes it.
    cleared = await client.patch(
        path,
        json={"config": {"username": None}, "secret": ""},
        headers=headers(csrf),
    )
    assert cleared.status_code == 200
    assert cleared.json()["secret_set"] is False
    assert cleared.json()["secret_hint"] is None
    async with db_engine.connect() as connection:
        query = select(AuditEvent.action, AuditEvent.details).order_by(AuditEvent.at)
        events = (await connection.execute(query)).all()
    updates = sorted(
        details["fields"] for action, details in events if action == "channel.update"
    )
    assert updates == ["config,label", "config,secret", "config,secret"]
    deleted = await client.delete(path, headers=headers(csrf))
    assert deleted.status_code == 204
    assert (await client.get(path)).status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"kind": "slack", "config": {}}, "body.config.url"),
        ({"config": EMAIL_CONFIG | {"port": "25"}}, "body.config.port"),
        ({"config": EMAIL_CONFIG | {"bcc": "x@example.com"}}, "body.config.bcc"),
        ({"config": EMAIL_CONFIG | {"username": RELAY_USER}}, "body.secret"),
        ({"config": {"host": "relay.example.com"}}, "body.config.from_address"),
        ({"label": " "}, "body.label"),
        ({"kind": "pager"}, "body.kind"),
    ],
)
async def test_unusable_channels_are_refused(
    client: httpx.AsyncClient, csrf: str, body: dict[str, Any], field: str
) -> None:
    base = {"kind": "email", "label": "Ops mail", "config": EMAIL_CONFIG}
    response = await client.post(
        "/api/v1/channels", json=base | body, headers=headers(csrf)
    )
    assert response.status_code == 422
    assert [item["field"] for item in response.json()["errors"]] == [field]


async def test_only_admins_change_channels_and_settings(
    app: FastAPI,
    client: httpx.AsyncClient,
    csrf: str,
    technician: AppUser,
) -> None:
    channel = await make_channel(client, csrf)
    async with another_browser(app) as other:
        tech = await sign_in(other, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
        assert (await other.get("/api/v1/channels")).status_code == 200
        assert (await other.get("/api/v1/channel-rules")).status_code == 200
        assert (await other.get("/api/v1/notifications")).status_code == 200
        refused = [
            await other.post(
                "/api/v1/channels",
                json={"kind": "email", "label": "x", "config": EMAIL_CONFIG},
                headers=headers(tech),
            ),
            await other.patch(
                f"/api/v1/channels/{channel['id']}",
                json={"label": "x"},
                headers=headers(tech),
            ),
            await other.post(
                f"/api/v1/channels/{channel['id']}/test", headers=headers(tech)
            ),
            await make_rule(other, tech, channel["id"]),
            await other.get("/api/v1/settings"),
            await other.patch(
                "/api/v1/settings", json={"reminder_24h": True}, headers=headers(tech)
            ),
            await other.post(
                "/api/v1/channels/check-url",
                json={"url": "https://hooks.example.com/"},
                headers=headers(tech),
            ),
        ]
    assert [response.status_code for response in refused] == [403] * 7


async def test_a_read_token_lists_but_cannot_change(
    app: FastAPI, client: httpx.AsyncClient, csrf: str
) -> None:
    await make_channel(client, csrf, secret=None)
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Dashboards", "scope": "read"},
        headers=headers(csrf),
    )
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    async with another_browser(app) as script:
        listed = await script.get("/api/v1/channels", headers=bearer)
        assert listed.status_code == 200 and len(listed.json()["items"]) == 1
        history = await script.get("/api/v1/notifications", headers=bearer)
        assert history.status_code == 200
        changed = await script.post(
            "/api/v1/channels", json={"kind": "email"}, headers=bearer
        )
        assert changed.status_code == 401


async def test_channel_test_answers_ok_or_a_readable_detail(
    client: httpx.AsyncClient,
    csrf: str,
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    capture = RelayCapture()
    async with smtp_relay(capture, login=(RELAY_USER, CANARY)) as port:
        config = EMAIL_CONFIG | {"port": port, "username": RELAY_USER}
        good = await make_channel(client, csrf, config=config, secret=CANARY)
        bad = await make_channel(
            client, csrf, label="Wrong password", config=config, secret="x" * 20
        )
        with caplog.at_level(logging.DEBUG, logger="app"):
            passed = await client.post(
                f"/api/v1/channels/{good['id']}/test", headers=headers(csrf)
            )
            failed = await client.post(
                f"/api/v1/channels/{bad['id']}/test", headers=headers(csrf)
            )
    assert passed.status_code == 200
    assert passed.json() == {"ok": True, "detail": "The test message was delivered."}
    assert failed.status_code == 200
    assert failed.json() == {
        "ok": False,
        "detail": "The relay refused the user name or password.",
    }
    ((sender, recipients, raw),) = capture.messages
    assert (sender, recipients) == ("checkorca@example.com", ["ops@example.com"])
    assert b"test of the channel Ops mail" in raw
    assert CANARY not in caplog.text and CANARY.encode() not in raw
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed = int(probe.getsockname()[1])
    nowhere = await make_channel(
        client, csrf, label="Closed", config=EMAIL_CONFIG | {"port": closed}
    )
    refused = await client.post(
        f"/api/v1/channels/{nowhere['id']}/test", headers=headers(csrf)
    )
    assert refused.json()["ok"] is False
    assert refused.json()["detail"] == (
        f"The relay refused the connection on port {closed}."
    )
    missing = await client.post(
        f"/api/v1/channels/{uuid.uuid4()}/test", headers=headers(csrf)
    )
    assert missing.status_code == 404
    async with db_engine.connect() as connection:
        query = select(AuditEvent.details).where(AuditEvent.action == "channel.test")
        tests = (await connection.execute(query)).scalars().all()
    assert sorted(item["ok"] for item in tests) == [False, False, True]


async def test_check_url_refuses_private_targets_readably(
    client: httpx.AsyncClient, csrf: str
) -> None:
    for url, words in (
        ("http://10.0.0.5/", "10.0.0.5 is a private address"),
        ("http://169.254.169.254/latest", "a cloud metadata address"),
        ("http://[::1]/", "::1 is a loopback address"),
        ("ftp://93.184.215.14/", "Only http:// and https:// URLs"),
    ):
        refused = await client.post(
            "/api/v1/channels/check-url", json={"url": url}, headers=headers(csrf)
        )
        assert refused.status_code == 422
        problem = refused.json()
        assert problem["title"] == "Target refused"
        assert words in problem["detail"]
        expected = [{"field": "body.url", "message": problem["detail"]}]
        assert problem["errors"] == expected
    public = await client.post(
        "/api/v1/channels/check-url",
        json={"url": "https://93.184.215.14/hook"},
        headers=headers(csrf),
    )
    assert public.status_code == 200
    assert public.json() == {
        "ok": True,
        "host": "93.184.215.14",
        "port": 443,
        "addresses": ["93.184.215.14"],
        "allowed_by": "public",
    }


async def test_outbound_allowed_hosts_lets_exactly_those_hosts_through(
    db_engine: AsyncEngine, clock: FakeClock, admin: AppUser
) -> None:
    settings = load_settings(outbound_allowed_hosts="10.0.0.5")
    application = create_app(settings, static_dir=None, clock=clock)
    async with running(application) as api:
        token = await sign_in(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        allowed = await api.post(
            "/api/v1/channels/check-url",
            json={"url": "http://10.0.0.5:8025/hook"},
            headers=headers(token),
        )
        other = await api.post(
            "/api/v1/channels/check-url",
            json={"url": "http://10.0.0.6/"},
            headers=headers(token),
        )
    assert allowed.status_code == 200
    assert allowed.json()["allowed_by"] == "allowed_host"
    assert other.status_code == 422


async def test_rules_follow_their_scope(client: httpx.AsyncClient, csrf: str) -> None:
    channel = await make_channel(client, csrf)
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    every = await make_rule(client, csrf, channel["id"], events=["missed", "digest"])
    assert every.status_code == 201, every.text
    assert every.json()["scope"] == "all" and every.json()["scope_id"] is None
    assert every.json()["events"] == ["missed", "digest"]
    for_client = await make_rule(
        client,
        csrf,
        channel["id"],
        scope="client",
        scope_id=dental["id"],
        events=["failing", "failing", "recovered"],
    )
    assert for_client.status_code == 201
    assert for_client.json()["scope_name"] == DENTAL
    assert for_client.json()["events"] == ["failing", "recovered"]
    for_job = await make_rule(
        client, csrf, channel["id"], scope="job", scope_id=job["id"]
    )
    assert for_job.json()["scope_name"] == f"{DENTAL} / Nightly server backup"

    for fields, field in (
        ({"scope": "client", "scope_id": str(uuid.uuid4())}, "body.scope_id"),
        ({"scope": "job"}, "body.scope_id"),
        ({"scope_id": dental["id"]}, "body.scope_id"),
        (
            {"scope": "client", "scope_id": dental["id"], "events": ["digest"]},
            "body.events",
        ),
        ({"events": []}, "body.events"),
        ({"events": ["exploded"]}, "body.events.0"),
    ):
        refused = await make_rule(client, csrf, channel["id"], **fields)
        assert refused.status_code == 422, fields
        assert refused.json()["errors"][0]["field"] == field
    unknown = await make_rule(client, csrf, str(uuid.uuid4()))
    assert unknown.json()["errors"][0]["field"] == "body.channel_id"

    path = f"/api/v1/channel-rules/{for_job.json()['id']}"
    widened = await client.patch(path, json={"scope": "all"}, headers=headers(csrf))
    assert widened.status_code == 200
    assert (widened.json()["scope"], widened.json()["scope_id"]) == ("all", None)
    narrowed = await client.patch(path, json={"scope": "client"}, headers=headers(csrf))
    assert narrowed.status_code == 422
    listed = await client.get(
        "/api/v1/channel-rules", params={"channel_id": channel["id"], "limit": 2}
    )
    page = listed.json()
    assert len(page["items"]) == 2 and page["next_cursor"] is not None
    rest = await client.get(
        "/api/v1/channel-rules",
        params={"channel_id": channel["id"], "cursor": page["next_cursor"]},
    )
    assert len(rest.json()["items"]) == 1
    assert (await client.delete(path, headers=headers(csrf))).status_code == 204
    assert (await client.delete(path, headers=headers(csrf))).status_code == 404
    # Deleting the channel deletes its rules.
    await client.delete(f"/api/v1/channels/{channel['id']}", headers=headers(csrf))
    assert (await client.get("/api/v1/channel-rules")).json()["items"] == []


async def test_the_notification_history_pages_newest_first(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    channel = await make_channel(client, csrf)
    days = [date(2027, 1, 1), date(2027, 1, 2), date(2027, 1, 3)]
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        repository = NotificationRepository(db, AllowAllPolicy())
        for offset, day in enumerate(days):
            await repository.queue(
                SYSTEM,
                [
                    {
                        "channel_id": uuid.UUID(channel["id"]),
                        "event": "digest",
                        "digest_day": day,
                        "created_at": clock.now() + timedelta(minutes=offset),
                        "next_attempt_at": clock.now() + timedelta(days=1),
                    }
                ],
            )
        await db.commit()
        await db.execute(
            text("UPDATE notification SET status = 'failed' WHERE digest_day = :day"),
            {"day": days[0]},
        )
        await db.commit()
    first = (await client.get("/api/v1/notifications", params={"limit": 2})).json()
    newest = [item["digest_day"] for item in first["items"]]
    assert newest == ["2027-01-03", "2027-01-02"]
    item = first["items"][0]
    assert item["channel_label"] == "Ops mail" and item["channel_kind"] == "email"
    assert (item["event"], item["status"]) == ("digest", "queued")
    assert item["flip_id"] is None and item["job_name"] is None
    rest = await client.get(
        "/api/v1/notifications", params={"cursor": first["next_cursor"]}
    )
    assert [item["digest_day"] for item in rest.json()["items"]] == ["2027-01-01"]
    failed = await client.get("/api/v1/notifications", params={"status": "failed"})
    assert len(failed.json()["items"]) == 1
    status = (await client.get("/api/v1/system/status")).json()["queue"]
    assert status["pending_notifications"] == 2
    # A failure without a last attempt time is not counted as recent.
    assert status["failed_notifications"] == 0
    broken = await client.get("/api/v1/notifications", params={"cursor": "nope"})
    assert broken.status_code == 400


async def test_the_digest_settings(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    default = await client.get("/api/v1/settings")
    assert default.json() == {
        "digest_time_local": "07:30",
        "digest_timezone": "Europe/Lisbon",
        "reminder_24h": False,
    }
    changed = await client.patch(
        "/api/v1/settings",
        json={
            "digest_time_local": "06:45",
            "digest_timezone": "America/New_York",
            "reminder_24h": True,
        },
        headers=headers(csrf),
    )
    assert changed.status_code == 200
    assert changed.json() == {
        "digest_time_local": "06:45",
        "digest_timezone": "America/New_York",
        "reminder_24h": True,
    }
    assert (await client.get("/api/v1/settings")).json() == changed.json()
    for body in (
        {},
        {"digest_time_local": "24:00"},
        {"digest_time_local": "7:30"},
        {"digest_timezone": "Mars/Olympus"},
        {"digest_timezone": "../../etc/passwd"},
        {"reminder_24h": "sometimes"},
        {"retention_raw_days": 1},
    ):
        refused = await client.patch(
            "/api/v1/settings", json=body, headers=headers(csrf)
        )
        assert refused.status_code == 422, body
    async with db_engine.connect() as connection:
        query = select(AuditEvent.details).where(AuditEvent.action == "settings.update")
        (details,) = (await connection.execute(query)).scalars().all()
    assert details == {"fields": "digest_time_local,digest_timezone,reminder_24h"}


async def test_jobs_say_who_acknowledged(
    app: FastAPI, client: httpx.AsyncClient, csrf: str, admin: AppUser
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "Nightly server backup")
    assert job["acknowledged_by"] is None
    acknowledged = await client.post(
        f"/api/v1/jobs/{job['id']}/acknowledge", headers=headers(csrf)
    )
    expected = {"id": str(admin.id), "email": ADMIN_EMAIL}
    assert acknowledged.json()["acknowledged_by"] == expected
    one = await client.get(f"/api/v1/jobs/{job['id']}")
    assert one.json()["acknowledged_by"] == expected
    listed = (await client.get("/api/v1/jobs")).json()["items"]
    assert listed[0]["acknowledged_by"] == expected
    created = await client.post(
        "/api/v1/tokens",
        json={"label": "Dashboards", "scope": "read"},
        headers=headers(csrf),
    )
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    async with another_browser(app) as script:
        seen = await script.get(f"/api/v1/jobs/{job['id']}", headers=bearer)
    assert seen.json()["acknowledged_by"] == {"id": str(admin.id), "email": None}


async def make_url_channel(
    client: httpx.AsyncClient, csrf: str, kind: str, url: str, **fields: Any
) -> httpx.Response:
    """POST a channel of one of the URL kinds; the URL goes in config.url."""
    body: dict[str, Any] = {"kind": kind, "label": "Ops hook", "config": {"url": url}}
    return await client.post(
        "/api/v1/channels", json=body | fields, headers=headers(csrf)
    )


async def test_http_channels_take_the_url_in_config_and_store_it_as_the_secret(
    db_engine: AsyncEngine,
    clock: FakeClock,
    admin: AppUser,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The URL of a slack, teams or webhook channel is its secret: write-only
    (D-6), answered as url_set and url_host only, checked by the SSRF guard
    before it is stored, and never in a log, an export, the digest or the
    audit trail."""
    caplog.set_level(logging.DEBUG, logger="app")
    application = create_app(
        load_settings(allow_private_targets=True), static_dir=None, clock=clock
    )
    capture = HttpCapture([http_answer(200)])
    await capture.start()
    try:
        async with running(application) as api:
            csrf = await sign_in(api, ADMIN_EMAIL, ADMIN_PASSWORD)
            created = await make_url_channel(api, csrf, "webhook", capture.url)
            assert created.status_code == 201, created.text
            channel = created.json()
            assert channel["config"] == {"url_set": True, "url_host": "127.0.0.1"}
            assert channel["secret_label"] == "Webhook URL"
            assert channel["secret_set"] is True and channel["secret_hint"] == MASK
            assert capture.url not in created.text
            # Nor in the exports, the digest, the activity or the history.
            for shown in (
                "/api/v1/channels",
                "/api/v1/exports/day.csv",
                "/api/v1/exports/history.csv",
                "/api/v1/digest/preview",
                "/api/v1/activity",
                "/api/v1/notifications",
            ):
                answer = await api.get(shown)
                assert answer.status_code == 200 and capture.url not in answer.text
            async with db_engine.connect() as connection:
                stored = (
                    await connection.execute(select(Channel.secret_enc))
                ).scalar_one()
                audit = (
                    (await connection.execute(select(AuditEvent.details)))
                    .scalars()
                    .all()
                )
            assert stored is not None and capture.url not in stored
            assert all(capture.url not in str(details) for details in audit)

            # The test send reaches the capture with the test payload, and
            # does not change last_status (a test is not a delivery).
            path = f"/api/v1/channels/{channel['id']}"
            tested = await api.post(f"{path}/test", headers=headers(csrf))
            assert tested.json() == {
                "ok": True,
                "detail": "The test message was delivered.",
            }
            (request,) = capture.requests
            assert request.body["event"] == "test"
            assert request.body["schema_version"] == 1
            assert (await api.get(path)).json()["last_status"] is None

            # The label changes; the URL stays.
            renamed = await api.patch(
                path, json={"label": "Night hooks"}, headers=headers(csrf)
            )
            assert renamed.status_code == 200
            assert renamed.json()["config"] == {
                "url_set": True,
                "url_host": "127.0.0.1",
            }
            assert renamed.json()["secret_set"] is True
            # Removing the URL is refused, as an e-mail channel without its
            # relay host; so is an empty one, and a separate secret.
            for body, field in (
                ({"config": {"url": None}}, "body.config.url"),
                ({"config": {"url": " "}}, "body.config.url"),
                ({"secret": "https://hooks.example.com/x"}, "body.secret"),
            ):
                refused = await api.patch(path, json=body, headers=headers(csrf))
                assert refused.status_code == 422, body
                assert refused.json()["errors"][0]["field"] == field
            # A metadata target stays refused even with private targets
            # allowed, with the guard's sentence.
            refused = await api.patch(
                path,
                json={"config": {"url": "http://169.254.169.254/latest"}},
                headers=headers(csrf),
            )
            assert refused.status_code == 422
            assert refused.json()["title"] == "Target refused"
            assert refused.json()["errors"][0]["field"] == "body.config.url"

            # A new URL replaces the stored one and is checked first.
            moved = HttpCapture([http_answer(200)])
            await moved.start()
            changed = await api.patch(
                path, json={"config": {"url": moved.url}}, headers=headers(csrf)
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["config"] == {
                "url_set": True,
                "url_host": "127.0.0.1",
            }
            async with db_engine.connect() as connection:
                again = (
                    await connection.execute(select(Channel.secret_enc))
                ).scalar_one()
            assert again != stored and moved.url not in again
            tested_again = await api.post(f"{path}/test", headers=headers(csrf))
            assert tested_again.json()["ok"] is True
            assert len(capture.requests) == 1 and len(moved.requests) == 1
            await moved.stop()
            deleted = await api.delete(path, headers=headers(csrf))
            assert deleted.status_code == 204
    finally:
        await capture.stop()
    assert capture.url not in caplog.text and moved.url not in caplog.text


@pytest.mark.parametrize(
    ("url", "title", "words"),
    [
        ("http://10.0.0.5/", "Target refused", "10.0.0.5 is a private address"),
        ("http://127.0.0.1/", "Target refused", "127.0.0.1 is a loopback address"),
        ("http://169.254.169.254/latest", "Target refused", "never called"),
        ("http://[::1]/", "Target refused", "::1 is a loopback address"),
        ("https://[fd00::]/", "Target refused", "fd00:: is a private address"),
        ("ftp://hooks.example.com/x", "Invalid channel settings", "http:// or https"),
        (
            "https://user:pass@hooks.example.com/",
            "Invalid channel settings",
            "user name or password",
        ),
    ],
)
async def test_creating_a_channel_refuses_what_the_guard_refuses(
    client: httpx.AsyncClient, csrf: str, url: str, title: str, words: str
) -> None:
    """A target the guard refuses is never stored, whatever the kind."""
    for kind in ("webhook", "slack", "teams"):
        refused = await make_url_channel(client, csrf, kind, url)
        assert refused.status_code == 422, (kind, url)
        assert refused.json()["title"] == title
        assert words in refused.json()["detail"]
        assert refused.json()["errors"][0]["field"] == "body.config.url"
    none_left = await client.get("/api/v1/channels")
    assert none_left.json()["items"] == []


async def test_a_public_target_and_an_allowed_host_can_be_stored(
    db_engine: AsyncEngine, clock: FakeClock, admin: AppUser
) -> None:
    """A public literal address stores (never sent to); OUTBOUND_ALLOWED_HOSTS
    is the narrow way to a private one."""
    application = create_app(
        load_settings(outbound_allowed_hosts="10.0.0.5"), static_dir=None, clock=clock
    )
    async with running(application) as api:
        csrf = await sign_in(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        for kind, url in (
            ("webhook", "http://93.184.215.14/hook"),
            ("slack", "http://10.0.0.5/hook"),
        ):
            created = await make_url_channel(api, csrf, kind, url)
            assert created.status_code == 201, created.text
            assert created.json()["config"]["url_host"] in ("93.184.215.14", "10.0.0.5")
            deleted = await api.delete(
                f"/api/v1/channels/{created.json()['id']}", headers=headers(csrf)
            )
            assert deleted.status_code == 204


async def test_a_stored_target_the_guard_now_refuses_fails_the_test_readably(
    db_engine: AsyncEngine, clock: FakeClock, admin: AppUser
) -> None:
    """A URL stored while private targets were allowed, tested after the
    operator turned that off: 422 Target refused with the guard's sentence,
    recorded as a failed test, nothing sent and no part of the path shown."""
    allowed = create_app(
        load_settings(allow_private_targets=True), static_dir=None, clock=clock
    )
    async with running(allowed) as api:
        csrf = await sign_in(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        created = await make_url_channel(
            api, csrf, "webhook", "http://10.0.0.5/hook-canary-path"
        )
        assert created.status_code == 201, created.text
    path = f"/api/v1/channels/{created.json()['id']}"
    strict = create_app(load_settings(), static_dir=None, clock=clock)
    async with running(strict) as api:
        csrf = await sign_in(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        tested = await api.post(f"{path}/test", headers=headers(csrf))
        assert (await api.get(path)).json()["last_status"] is None
    assert tested.status_code == 422
    problem = tested.json()
    assert problem["title"] == "Target refused"
    assert "10.0.0.5 is a private address" in problem["detail"]
    assert problem["errors"] == [{"field": "config.url", "message": problem["detail"]}]
    assert "hook-canary-path" not in tested.text
    async with db_engine.connect() as connection:
        query = select(AuditEvent.details).where(AuditEvent.action == "channel.test")
        tests = (await connection.execute(query)).scalars().all()
    assert [item["ok"] for item in tests] == [False]
