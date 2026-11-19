"""The SMTP listener: RCPT 550 for an unknown code, the size, recipient,
rate and connection limits, the timeout, sender rules, STARTTLS, one row per
message and no address or content in the logs. Mail is synthetic (R-11)."""

import asyncio
import functools
import ipaddress
import logging
import smtplib
import ssl
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from aiosmtpd.smtp import Envelope, Session
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.access import SYSTEM
from app.db.models import Inbox, RawMessage
from app.ingest import smtp
from app.ingest.imap import ImapPoller
from app.ingest.smtp import SmtpReceiver, source_address
from app.ingest.store import MAX_MESSAGE_BYTES
from app.logging import quiet_libraries
from app.repos.inboxes import InboxRepository
from app.settings import Settings, SettingsError, load_settings
from app.worker.loop import RECEIVERS, WorkerContext, build_context
from helpers import FakeClock

SENDER = "backup@example.com"
# The tests run with BASE_URL http://localhost:8080: inboxes are code@localhost.
DOMAIN = "localhost"


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


async def started(context: WorkerContext, **options: Any) -> SmtpReceiver:
    receiver = SmtpReceiver(context, host="127.0.0.1", port=0, **options)
    await receiver.start(context)
    return receiver


@pytest.fixture
async def receiver(context: WorkerContext) -> AsyncIterator[SmtpReceiver]:
    running = await started(context)
    yield running
    await running.stop()


async def add_inbox(context: WorkerContext, kind: str = "smtp", **fields: Any) -> Inbox:
    async with context.sessionmaker() as db:
        inbox, _ = await InboxRepository(db, context.policy).create(
            SYSTEM,
            kind=kind,
            label=f"SMTP test {kind}",
            now=context.clock.now(),
            **fields,
        )
        await db.commit()
    return inbox


def address(inbox: Inbox) -> str:
    return f"{inbox.code}@{DOMAIN}"


def message(
    to: str,
    *,
    sender: str = SENDER,
    message_id: str = "<run-1@backup.example.com>",
    body: str = "Job Nightly server backup: Success\r\n",
) -> bytes:
    return (
        f"From: Backup Server <{sender}>\r\n"
        f"To: {to}\r\n"
        "Subject: [Success] Nightly server backup (synthetic)\r\n"
        "Date: Mon, 4 Jan 2027 06:29:00 +0000\r\n"
        f"Message-ID: {message_id}\r\n\r\n"
        f"{body}"
    ).encode()


def client(port: int) -> smtplib.SMTP:
    """A connected client after EHLO: aiosmtpd answers 503 to MAIL before it,
    and smtplib's mail() does not send it (sendmail() does)."""
    # local_hostname avoids a DNS lookup of the runner's name.
    session = smtplib.SMTP("127.0.0.1", port, local_hostname="sender.test", timeout=10)
    session.ehlo()
    return session


async def blocking[T](call: Callable[[], T]) -> T:
    """smtplib blocks, so it runs in a thread while the loop serves."""
    return await asyncio.wait_for(asyncio.to_thread(call), timeout=30)


def send(port: int, to: list[str], raw: bytes, sender: str = SENDER) -> Any:
    with client(port) as session:
        return session.sendmail(sender, to, raw)


async def rows(engine: AsyncEngine) -> list[tuple[Any, ...]]:
    query = select(RawMessage.inbox_id, RawMessage.message_id)
    async with engine.connect() as connection:
        return [tuple(row) for row in (await connection.execute(query)).all()]


def test_the_worker_starts_the_listener_and_the_poller() -> None:
    assert RECEIVERS == (SmtpReceiver, ImapPoller)
    assert smtp.TIMEOUT_SECONDS == 30
    assert smtp.MAX_RECIPIENTS == 20
    assert smtp.SOURCE_RATE == (60, 60.0)
    assert MAX_MESSAGE_BYTES == 5 * 1024 * 1024


async def test_a_message_is_stored_once_per_inbox_and_message_id(
    receiver: SmtpReceiver, context: WorkerContext, db_engine: AsyncEngine
) -> None:
    first = await add_inbox(context)
    second = await add_inbox(context)
    to = [address(first), address(second), address(first).upper()]
    raw = message(address(first))
    assert await blocking(lambda: send(receiver.port, to, raw)) == {}
    expected = {
        (first.id, "<run-1@backup.example.com>"),
        (second.id, "<run-1@backup.example.com>"),
    }
    assert set(await rows(db_engine)) == expected
    # The same Message-ID again is accepted and stored nowhere.
    assert await blocking(lambda: send(receiver.port, to, raw)) == {}
    assert len(await rows(db_engine)) == 2


async def test_rcpt_for_an_unknown_code_gets_550(
    receiver: SmtpReceiver, context: WorkerContext
) -> None:
    inbox = await add_inbox(context)
    webhook = await add_inbox(context, kind="webhook")

    def rcpt(to: str) -> int:
        with client(receiver.port) as session:
            session.mail(SENDER)
            code, _ = session.rcpt(to)
            return code

    assert await blocking(lambda: rcpt(address(inbox))) == 250
    for refused in (
        "a" * 24 + "@" + DOMAIN,
        f"{inbox.code}@elsewhere.test",
        address(webhook),
        f"not-a-code!@{DOMAIN}",
    ):
        assert await blocking(functools.partial(rcpt, refused)) == 550, refused


async def test_a_message_over_5_mb_gets_552(
    receiver: SmtpReceiver, context: WorkerContext, db_engine: AsyncEngine
) -> None:
    inbox = await add_inbox(context)
    # Lines of 1,000 bytes up to just past 5 MB.
    big = message(address(inbox))
    big += (b"z" * 998 + b"\r\n") * (MAX_MESSAGE_BYTES // 1000 + 1)

    def declared() -> int:
        with client(receiver.port) as session:
            session.ehlo()
            code, _ = session.mail(SENDER, [f"SIZE={MAX_MESSAGE_BYTES + 1}"])
            return code

    def sent() -> int:
        with client(receiver.port) as session:
            session.mail(SENDER)
            session.rcpt(address(inbox))
            # data() raises only when DATA itself is refused; the answer to the
            # message comes back as the code.
            code, _ = session.data(big)
            return code

    assert await blocking(declared) == 552
    assert await blocking(sent) == 552
    assert await rows(db_engine) == []


async def test_a_header_block_over_256_kb_gets_552(
    receiver: SmtpReceiver, context: WorkerContext, db_engine: AsyncEngine
) -> None:
    inbox = await add_inbox(context)
    filler = b"".join(b"X-Filler-%d: %s\r\n" % (n, b"y" * 960) for n in range(300))
    raw = filler + message(address(inbox))

    def sent() -> int:
        with client(receiver.port) as session:
            session.mail(SENDER)
            session.rcpt(address(inbox))
            code, _ = session.data(raw)
            return code

    assert await blocking(sent) == 552
    assert await rows(db_engine) == []


async def test_handle_data_checks_the_length_itself(receiver: SmtpReceiver) -> None:
    envelope = Envelope()
    envelope.original_content = b"x" * (MAX_MESSAGE_BYTES + 1)
    session = Session(asyncio.get_running_loop())
    answer = await receiver.handler.handle_DATA(None, session, envelope)
    assert answer.startswith("552")


async def test_more_than_20_recipients_get_452(
    receiver: SmtpReceiver, context: WorkerContext, db_engine: AsyncEngine
) -> None:
    inbox = await add_inbox(context)

    def recipients() -> list[int]:
        with client(receiver.port) as session:
            session.mail(SENDER)
            codes = [session.rcpt(address(inbox))[0] for _ in range(21)]
            session.data(message(address(inbox)))
            return codes

    assert await blocking(recipients) == [250] * 20 + [452]
    assert len(await rows(db_engine)) == 1


async def test_60_messages_a_minute_per_source_then_451(
    receiver: SmtpReceiver, clock: FakeClock
) -> None:
    def transactions(count: int) -> list[int]:
        codes = []
        with client(receiver.port) as session:
            for _ in range(count):
                codes.append(session.mail(SENDER)[0])
                session.rset()
        return codes

    assert await blocking(lambda: transactions(61)) == [250] * 60 + [451]
    # The bucket refills one message a second.
    clock.advance(seconds=1)
    assert await blocking(lambda: transactions(2)) == [250, 451]


async def test_an_idle_connection_is_closed_after_the_timeout(
    context: WorkerContext,
) -> None:
    receiver = await started(context, timeout=0.3)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", receiver.port)
        greeting = await asyncio.wait_for(reader.readline(), timeout=5)
        assert greeting.startswith(b"220 ")
        # Nothing sent: the server closes the connection.
        assert await asyncio.wait_for(reader.read(), timeout=5) == b""
        writer.close()
    finally:
        await receiver.stop()


async def test_connections_past_the_cap_get_421(context: WorkerContext) -> None:
    receiver = await started(context, max_sessions=1)
    try:
        first_reader, first = await asyncio.open_connection("127.0.0.1", receiver.port)
        assert (await first_reader.readline()).startswith(b"220 ")
        reader, second = await asyncio.open_connection("127.0.0.1", receiver.port)
        assert (await asyncio.wait_for(reader.readline(), 5)).startswith(b"421 ")
        assert await asyncio.wait_for(reader.read(), timeout=5) == b""
        second.close()
        first.close()
    finally:
        await receiver.stop()


async def test_one_source_cannot_hold_every_session(context: WorkerContext) -> None:
    receiver = await started(context, max_per_source=2)
    try:
        held = []
        for _ in range(2):
            reader, writer = await asyncio.open_connection("127.0.0.1", receiver.port)
            assert (await asyncio.wait_for(reader.readline(), 5)).startswith(b"220 ")
            held.append(writer)
        reader, third = await asyncio.open_connection("127.0.0.1", receiver.port)
        assert (await asyncio.wait_for(reader.readline(), 5)).startswith(b"421 ")
        third.close()
        for writer in held:
            writer.close()
    finally:
        await receiver.stop()


async def test_unknown_recipients_close_the_connection_after_ten(
    receiver: SmtpReceiver,
) -> None:
    def rcpts() -> tuple[list[int], bool]:
        with client(receiver.port) as session:
            session.mail(SENDER)
            codes = [session.rcpt(f"{n:024d}@{DOMAIN}")[0] for n in range(11)]
            try:
                session.noop()
            except smtplib.SMTPServerDisconnected:
                return codes, True
            return codes, False

    assert await blocking(rcpts) == ([550] * 10 + [421], True)


async def test_the_greeting_names_the_product_not_the_library(
    receiver: SmtpReceiver,
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", receiver.port)
    greeting = await asyncio.wait_for(reader.readline(), timeout=5)
    writer.close()
    assert b"Checkorca-CE ESMTP" in greeting
    assert b"Python" not in greeting and b"1.4" not in greeting


async def test_the_sender_allowlist_refuses_with_550(
    receiver: SmtpReceiver, context: WorkerContext, db_engine: AsyncEngine
) -> None:
    guarded = await add_inbox(context, sender_allowlist=["@example.com"])
    open_inbox = await add_inbox(context)
    intruder = "intruder@attacker.test"

    def refused() -> int:
        try:
            send(receiver.port, [address(guarded)], message("x", sender=intruder))
        except smtplib.SMTPDataError as error:
            return error.smtp_code
        return 250

    assert await blocking(refused) == 550
    assert await rows(db_engine) == []
    # Another inbox of the same message without rules still takes it.
    to = [address(guarded), address(open_inbox)]
    raw = message("x", sender=intruder, message_id="<run-2@backup.example.com>")
    assert await blocking(lambda: send(receiver.port, to, raw)) == {}
    assert await rows(db_engine) == [(open_inbox.id, "<run-2@backup.example.com>")]
    raw = message("x", message_id="<run-3@backup.example.com>")
    assert await blocking(lambda: send(receiver.port, [address(guarded)], raw)) == {}
    assert len(await rows(db_engine)) == 2


async def test_a_store_failure_answers_451_and_keeps_nothing(
    receiver: SmtpReceiver,
    context: WorkerContext,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inbox = await add_inbox(context)

    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database gone")

    monkeypatch.setattr(smtp, "accept_message", broken)

    def attempt() -> int:
        try:
            send(receiver.port, [address(inbox)], message(address(inbox)))
        except smtplib.SMTPDataError as error:
            return error.smtp_code
        return 250

    assert await blocking(attempt) == 451
    assert await rows(db_engine) == []


async def test_a_failed_inbox_lookup_answers_451(
    receiver: SmtpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*args: object) -> None:
        raise RuntimeError("database gone")

    monkeypatch.setattr(receiver.handler, "_find", broken)

    def rcpt() -> int:
        with client(receiver.port) as session:
            session.mail(SENDER)
            return session.rcpt(f"{'a' * 24}@{DOMAIN}")[0]

    assert await blocking(rcpt) == 451


async def test_an_unexpected_error_does_not_reach_the_sender(
    receiver: SmtpReceiver,
) -> None:
    answer = await receiver.handler.handle_exception(RuntimeError("secret detail"))
    assert answer.startswith("451") and "secret" not in answer


async def test_the_rate_limit_key_is_the_source_address() -> None:
    session = Session(asyncio.get_running_loop())
    session.peer = ("192.0.2.10", 40000)
    assert source_address(session) == "192.0.2.10"
    session.peer = "unix-socket"
    assert source_address(session) == "unix-socket"


def certificate(directory: Path) -> tuple[str, str]:
    """A self-signed certificate for localhost and 127.0.0.1 (test only)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    names = x509.SubjectAlternativeName(
        [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    )
    built = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(names, critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = directory / "smtp.crt", directory / "smtp.key"
    cert_file.write_bytes(built.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(cert_file), str(key_file)


async def test_starttls_with_the_mounted_certificate(
    db_engine: AsyncEngine, clock: FakeClock, tmp_path: Path
) -> None:
    cert_file, key_file = certificate(tmp_path)
    settings = load_settings(smtp_tls_cert_file=cert_file, smtp_tls_key_file=key_file)
    context = build_context(settings, clock)
    receiver = await started(context)
    try:
        inbox = await add_inbox(context)
        trusted = ssl.create_default_context(cafile=cert_file)

        def secured() -> tuple[bool, Any]:
            with client(receiver.port) as session:
                session.ehlo()
                offered = session.has_extn("starttls")
                session.starttls(context=trusted)
                session.ehlo()
                to = [address(inbox)]
                return offered, session.sendmail(SENDER, to, message(to[0]))

        assert await blocking(secured) == (True, {})
        assert len(await rows(db_engine)) == 1
    finally:
        await receiver.stop()
        await context.engine.dispose()


async def test_without_certificate_files_no_starttls_is_offered(
    receiver: SmtpReceiver,
) -> None:
    def offered() -> bool:
        with client(receiver.port) as session:
            session.ehlo()
            return session.has_extn("starttls")

    assert await blocking(offered) is False


def test_the_certificate_settings_come_in_pairs() -> None:
    with pytest.raises(SettingsError, match="SMTP_TLS_CERT_FILE"):
        load_settings(smtp_tls_cert_file="/run/secrets/smtp.crt")
    with pytest.raises(SettingsError, match="SMTP_TLS_KEY_FILE"):
        load_settings(smtp_tls_key_file="/run/secrets/smtp.key")
    assert isinstance(load_settings(), Settings)


def test_the_worker_refuses_to_start_without_the_certificate_files(
    tmp_path: Path,
) -> None:
    missing = {
        "smtp_tls_cert_file": str(tmp_path / "missing.crt"),
        "smtp_tls_key_file": str(tmp_path / "missing.key"),
    }
    for role in ("all", "worker"):
        with pytest.raises(SettingsError, match="readable files"):
            load_settings(role=role, **missing)
    # The web role does not open port 2525.
    assert load_settings(role="web", **missing).smtp_tls_cert_file


async def test_logs_carry_counts_never_addresses_codes_or_content(
    receiver: SmtpReceiver,
    context: WorkerContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "Canary-" + "m" * 16
    inbox = await add_inbox(context)
    quiet_libraries()
    caplog.set_level(logging.DEBUG)
    raw = message(address(inbox), body=f"{canary}\r\n")
    assert await blocking(lambda: send(receiver.port, [address(inbox)], raw)) == {}
    messages = [record.getMessage() for record in caplog.records]
    assert "smtp message received" in messages
    for forbidden in (canary, SENDER, inbox.code, "Nightly server backup"):
        assert forbidden not in caplog.text
