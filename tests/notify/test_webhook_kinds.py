"""The slack, teams and webhook channel kinds (app/notify/webhook.py):
their settings, their bodies against the golden files, every webhook payload
against docs/webhook-payload.schema.json, delivery through a capturing HTTP
server on 127.0.0.1, the SSRF guard per kind, and the 10-second timeout.

The capturing server answers from a script; nothing leaves the test. The URL
of a channel is its secret, so its path (a canary) must never reach an error,
a stored sentence or a log. Every name and address is synthetic (legal R-11).
"""

import json
import logging
import socket
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import jsonschema
import pytest

import app.notify.webhook as webhook_module
from app.ext.notifications import (
    ChannelConfigError,
    DeliveryError,
    FlipFacts,
    Message,
    Outbound,
)
from app.ext.reports import Digest, DigestItem, RenderedReport
from app.notify.messages import channel_test_message, digest_message, flip_message
from app.notify.payloads import escape_markup, escape_teams, fit, payload_of
from app.notify.webhook import SlackKind, TeamsKind, WebhookKind, host_of
from app.security.ssrf import check_target
from helpers import HttpCapture, http_answer

# A secret-looking webhook path that must never show in an error or a log.
CANARY = "/services/T000/B000/secret-secret"
BASE_URL = "https://ce-dev-checkorca.theriark.dev"
ZONE = ZoneInfo("Europe/Lisbon")
GOLDEN = Path(__file__).parents[2] / "docs" / "webhook-payload.schema.json"

FLIP_AT = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)
SCHEDULED_FOR = datetime(2027, 1, 4, 23, 0, tzinfo=UTC)
DEADLINE = datetime(2027, 1, 5, 1, 0, tzinfo=UTC)
GENERATED_AT = datetime(2027, 1, 5, 7, 31, tzinfo=UTC)
TEST_AT = datetime(2027, 1, 5, 8, 0, tzinfo=UTC)

FACTS = FlipFacts(
    flip_id=UUID("11111111-1111-4111-8111-111111111111"),
    job_id=UUID("22222222-2222-4222-8222-222222222222"),
    job="Nightly server backup",
    job_kind="backup",
    client_id=UUID("33333333-3333-4333-8333-333333333333"),
    client="Fictional Dental Clinic",
    from_state="ok",
    to_state="missed",
    reason="The run was due at 23:00 and nothing reported by 01:00.",
    at=FLIP_AT,
    scheduled_for=SCHEDULED_FOR,
    deadline=DEADLINE,
    url=f"{BASE_URL}/jobs/22222222-2222-4222-8222-222222222222",
)

DIGEST = Digest(
    day=date(2027, 1, 5),
    timezone="Europe/Lisbon",
    start=datetime(2027, 1, 4, 7, 30, tzinfo=UTC),
    end=datetime(2027, 1, 5, 7, 30, tzinfo=UTC),
    generated_at=GENERATED_AT,
    verified=41,
    warning=2,
    failed=1,
    silent=1,
    items=(
        DigestItem(
            client="Fictional Freight Ltd",
            job="Hyper Backup nightly",
            state="missed",
            scheduled_for=datetime(2027, 1, 4, 23, 0, tzinfo=UTC),
            deadline=datetime(2027, 1, 5, 1, 0, tzinfo=UTC),
        ),
        DigestItem(
            client="Fictional Dental Clinic",
            job="Veeam BR",
            state="failed",
            scheduled_for=datetime(2027, 1, 4, 22, 0, tzinfo=UTC),
            deadline=datetime(2027, 1, 5, 0, 0, tzinfo=UTC),
        ),
    ),
    more_items=0,
    url=f"{BASE_URL}/",
)

KINDS = {"webhook": WebhookKind(), "slack": SlackKind(), "teams": TeamsKind()}


def facts_of(event: str) -> FlipFacts:
    """The flip of the event: ok to the problem, or the problem to ok."""
    changes: dict[str, Any] = {}
    if event == "warning":
        changes = {"to_state": "warning"}
    elif event == "recovered":
        changes = {"from_state": "missed", "to_state": "ok"}
    return replace(FACTS, **changes)


def flip_of(event: str) -> Message:
    return flip_message(event, facts_of(event), ZONE)


def messages() -> dict[str, Message]:
    """One message per event, deterministic (the golden files need that).
    The digest message carries a short synthetic report: the rendering of a
    digest is the renderer's own contract (tests/notify/test_digest.py), the
    payload builders only read its subject and text."""
    report = RenderedReport(
        subject="Checkorca-CE morning check 2027-01-05",
        html="<p>Morning check</p>",
        text="Morning check, 2027-01-05.\n",
    )
    return {
        "missed": flip_of("missed"),
        "warning": flip_of("warning"),
        "recovered": flip_of("recovered"),
        "reminder": flip_of("reminder"),
        "digest": digest_message(report, f"{BASE_URL}/", DIGEST.day, DIGEST),
        "test": channel_test_message("Ops hook", f"{BASE_URL}/", TEST_AT),
    }


@pytest.fixture
async def capture() -> AsyncIterator[HttpCapture]:
    server = HttpCapture([http_answer(200)])
    await server.start()
    yield server
    await server.stop()


async def refused(kind_name: str, url: str, outbound: Outbound) -> DeliveryError:
    with pytest.raises(DeliveryError) as failure:
        await KINDS[kind_name].send({}, url, messages()["missed"], outbound)
    return failure.value


def test_the_settings_keep_only_the_http_answer() -> None:
    kind = WebhookKind()
    assert kind.url_key == "url" and kind.secret_targets == frozenset()
    assert kind.check_config(
        {"url": " https://Hooks.Example.com./services/x "}, has_secret=False
    ) == {"url_set": True, "url_host": "hooks.example.com"}
    # A stored URL keeps the answer, whatever the request re-sent.
    assert kind.check_config(
        {"url_set": True, "url_host": "hooks.example.com"}, has_secret=True
    ) == {"url_set": True, "url_host": "hooks.example.com"}
    assert kind.check_config({"url_set": True}, has_secret=True) == {
        "url_set": True,
        "url_host": None,
    }


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({}, "Set the channel's URL."),
        ({"url": None}, "Set the channel's URL."),
        ({"url": "  "}, "Set the channel's URL."),
        ({"url": 12}, "Use the channel's URL as text."),
        ({"webhook": "x"}, "Unknown setting."),
        ({"url_set": True}, "Set the channel's URL."),
        ({"url": "ftp://hooks.example.com/x"}, "must start with http:// or https://"),
        ({"url": "https://user:pass@hooks.example.com/"}, "user name or password"),
        ({"url": "https:///hook"}, "has no host"),
        ({"url": "https://hooks.example.com/a b"}, "spaces or control characters"),
        ({"url": "https://hooks.example.com:99999/"}, "cannot be read"),
        ({"url": "https://" + "h" * 2000}, "at most 2000 characters"),
    ],
)
def test_unusable_settings_name_their_field(
    config: dict[str, Any], message: str
) -> None:
    with pytest.raises(ChannelConfigError) as failure:
        WebhookKind().check_config(config, has_secret=False)
    assert failure.value.field == "url"
    assert message in failure.value.message


def test_host_of_reads_the_host_only() -> None:
    assert host_of("http://hooks.example.com/services/x") == "hooks.example.com"
    assert host_of("https://[fd00::25]:8443/hook") == "fd00::25"
    assert host_of("HTTP://Hooks.Example.com./x") == "hooks.example.com"


def test_escape_markup_keeps_user_content_text() -> None:
    assert escape_markup("<b> & </b>") == "&lt;b&gt; &amp; &lt;/b&gt;"


@pytest.mark.parametrize("kind_name", list(KINDS))
@pytest.mark.parametrize(
    "event", ["missed", "warning", "recovered", "reminder", "digest", "test"]
)
def test_bodies_match_the_golden_files(kind_name: str, event: str) -> None:
    """Every kind's body for every event is the committed golden file."""
    body = KINDS[kind_name].body_of(messages()[event])
    golden = (
        Path(__file__).parent / "golden" / f"{kind_name}-{event}.json"
    ).read_text()
    assert body == json.loads(golden)


def test_every_payload_validates_against_the_schema() -> None:
    """Every payload the webhook kind sends follows the published contract."""
    validator = jsonschema.Draft202012Validator(json.loads(GOLDEN.read_text()))
    for message in messages().values():
        validator.validate(payload_of(message))
    # A payload that misses what its event needs does not validate.
    with pytest.raises(jsonschema.ValidationError):
        validator.validate({"event": "missed", "schema_version": 1})
    with pytest.raises(jsonschema.ValidationError):
        validator.validate({"event": "digest", "schema_version": 1})
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(
            {
                "event": "missed",
                "at": "2027-01-05T07:30:00Z",
                "url": "https://ce-dev-checkorca.theriark.dev/jobs/x",
                "product": "Checkorca-CE",
                "schema_version": 2,
            }
        )


def test_user_content_never_becomes_markup() -> None:
    hostile = replace(FACTS, job="<b>&", client='"><script>')
    bodies = (
        SlackKind().body_of(flip_message("missed", hostile, ZONE)),
        TeamsKind().body_of(flip_message("missed", hostile, ZONE)),
    )
    for body in bodies:
        text = json.dumps(body)
        assert "<b>&" not in text and '"><script>' not in text
        assert "&lt;b&gt;&amp;" in text and "&lt;script&gt;" in text


def test_a_teams_name_never_becomes_a_link_or_an_image() -> None:
    linked = replace(FACTS, job="![x](https://pixel.example.com/a.png)")
    body = TeamsKind().body_of(flip_message("missed", linked, ZONE))
    for field in ("summary", "title", "text"):
        assert "![x](" not in body[field]
        assert "!&#91;x&#93;(https://pixel.example.com/a.png)" in body[field]


def test_fit_never_cuts_an_entity_and_keeps_the_limit() -> None:
    assert fit("a&b", 10, escape_markup) == "a&amp;b"
    assert fit("abc", 2, escape_markup) == "ab"
    # Only whole entities: one "&amp;" fits in 5, a second does not.
    assert fit("&&&&&&&", 5, escape_markup) == "&amp;"
    assert fit("&&&&&&&", 9, escape_markup) == "&amp;"
    assert fit("a[b]", 100, escape_teams) == escape_teams("a[b]")
    assert fit("<<<", 3, escape_markup) == ""
    long = SlackKind().body_of(
        flip_message("missed", replace(FACTS, client="<" * 400), ZONE)
    )
    header = long["blocks"][0]["text"]["text"]
    assert len(header) <= 150 and header.endswith(";")
    assert escape_teams("[a]") == "&#91;a&#93;"


async def test_delivery_reaches_the_checked_target(capture: HttpCapture) -> None:
    for kind_name in KINDS:
        await KINDS[kind_name].send(
            {}, capture.url, messages()["missed"], Outbound(allow_private=True)
        )
    assert len(capture.requests) == 3
    last = capture.requests[-1]
    assert last.line == f"POST {CANARY} HTTP/1.1"
    assert last.body == KINDS["teams"].body_of(messages()["missed"])
    assert f"Host: 127.0.0.1:{capture.port}" in last.headers
    assert "Content-Type: application/json" in last.headers
    assert "Accept: application/json" in last.headers
    assert "Connection: close" in last.headers
    assert any(
        header.startswith("User-Agent: Checkorca-CE/") for header in last.headers
    )
    assert any(header.startswith("Content-Length: ") for header in last.headers)


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (302, "The target answered 302 and redirects are not followed."),
        (404, "The target answered 404."),
        (500, "The target answered 500."),
    ],
)
async def test_answers_that_are_not_a_delivery(
    status: int, detail: str, caplog: pytest.LogCaptureFixture
) -> None:
    server = HttpCapture([http_answer(status)])
    await server.start()
    try:
        with caplog.at_level(logging.DEBUG, logger="app"):
            error = await refused("webhook", server.url, Outbound(allow_private=True))
    finally:
        await server.stop()
    assert str(error) == detail
    # A redirect is not followed: one request, wherever it points.
    assert len(server.requests) == 1
    assert CANARY not in str(error) and CANARY not in caplog.text


@pytest.mark.parametrize("kind_name", list(KINDS))
async def test_a_redirect_to_a_private_address_is_never_followed(
    kind_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The SSRF table's redirect row: a public-looking target that answers
    302 to the metadata service or a private host gets one request, and the
    Location is neither followed nor repeated in the error."""
    redirect = (
        b"HTTP/1.1 302 Found\r\n"
        b"Location: http://169.254.169.254/latest/meta-data/\r\n"
        b"Content-Length: 0\r\n"
        b"Connection: close\r\n"
        b"\r\n"
    )
    server = HttpCapture([redirect])
    await server.start()
    try:
        with caplog.at_level(logging.DEBUG, logger="app"):
            error = await refused(kind_name, server.url, Outbound(allow_private=True))
    finally:
        await server.stop()
    assert str(error) == "The target answered 302 and redirects are not followed."
    assert len(server.requests) == 1
    assert "169.254.169.254" not in str(error) and "169.254" not in caplog.text


async def test_an_answer_that_is_not_http() -> None:
    server = HttpCapture([b"garbage, not a status line\r\n"])
    await server.start()
    try:
        error = await refused("webhook", server.url, Outbound(allow_private=True))
    finally:
        await server.stop()
    assert str(error) == "The target did not answer with HTTP."


async def test_a_closed_port_is_a_readable_failure() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    error = await refused(
        "webhook", f"http://127.0.0.1:{port}{CANARY}", Outbound(allow_private=True)
    )
    assert str(error) == f"The target refused the connection on port {port}."
    assert CANARY not in str(error)


async def test_a_target_that_never_answers_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webhook_module, "REQUEST_TIMEOUT", 0.3)
    server = HttpCapture([], hang=True)
    await server.start()
    try:
        error = await refused("webhook", server.url, Outbound(allow_private=True))
    finally:
        await server.stop()
    assert "The target did not answer within" in str(error)


async def test_a_channel_without_a_url_says_so() -> None:
    error = await refused("slack", "", Outbound())
    assert str(error) == "The channel has no URL."


SSRF_TABLE = (
    ("http://10.0.0.5/", "10.0.0.5 is a private address"),
    ("http://127.0.0.1/", "127.0.0.1 is a loopback address"),
    ("http://169.254.169.254/latest", "never called"),
    ("http://169.254.0.1/", "never called"),
    ("http://[::1]/", "::1 is a loopback address"),
    ("https://[fd00::]/", "fd00:: is a private address"),
    ("http://[fe80::1]/", "never called"),
    ("ftp://hooks.example.com/hook", "Only http:// and https:// URLs"),
)


@pytest.mark.parametrize("kind_name", list(KINDS))
@pytest.mark.parametrize(("url", "words"), SSRF_TABLE)
async def test_every_kind_refuses_the_guard_s_table(
    kind_name: str, url: str, words: str
) -> None:
    error = await refused(kind_name, url, Outbound())
    assert words in str(error)
    assert CANARY not in str(error)


async def test_every_kind_refuses_a_name_that_resolves_privately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kinds keep the guard's resolver seam: a name that resolves to a
    private address is refused per kind too."""

    async def private(host: str, port: int) -> list[str]:
        return ["10.0.0.7"]

    async def checked(
        url: str, *, allow_private: bool, allowed_hosts: frozenset[str]
    ) -> object:
        return await check_target(
            url,
            allow_private=allow_private,
            allowed_hosts=allowed_hosts,
            resolver=private,
        )

    monkeypatch.setattr(webhook_module, "check_target", checked)
    for kind_name in KINDS:
        error = await refused(
            kind_name, "https://internal.example.com/hook", Outbound()
        )
        assert "internal.example.com resolves to 10.0.0.7, a private address" in str(
            error
        )


async def test_the_allowed_hosts_let_a_kind_through_to_the_capture(
    capture: HttpCapture,
) -> None:
    """OUTBOUND_ALLOWED_HOSTS is the narrow way to a local receiver: the
    capture server answers with loopback allowed by name."""
    await SlackKind().send(
        {},
        capture.url,
        messages()["missed"],
        Outbound(allowed_hosts=frozenset({"127.0.0.1"})),
    )
    assert len(capture.requests) == 1
    assert capture.requests[0].body == SlackKind().body_of(messages()["missed"])


async def test_link_local_stays_refused_under_allow_private() -> None:
    """C9-I refused link-local even under ALLOW_PRIVATE_TARGETS (the C9-B
    security re-review note); metadata was already never allowed."""
    for url in ("http://169.254.0.1/", "http://[fe80::1]/"):
        error = await refused("webhook", url, Outbound(allow_private=True))
        assert "never called" in str(error)
