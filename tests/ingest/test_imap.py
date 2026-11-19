"""The IMAP poller and connector: Seen only after the commit, a failed store
leaves the message unseen, poll seconds per inbox, oversize skipped, the
password only in the poller. Mailboxes and mail are synthetic (R-11)."""

import asyncio
import imaplib
import logging
import ssl
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.access import SYSTEM
from app.db.models import Inbox, RawMessage
from app.ext.ingest import FetchedMessage, MailboxAccount
from app.ingest import imap
from app.ingest.imap import ImapConnector, ImapError, ImapPoller, PollResult, quote
from app.ingest.receive import accept_message
from app.ingest.store import MAX_MESSAGE_BYTES
from app.repos.inboxes import InboxRepository
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import FakeClock

PASSWORD = "Synthetic-imap-" + "p" * 12


def mail(number: int, sender: str = "backup@example.com") -> bytes:
    return (
        f"From: Backup Server <{sender}>\r\n"
        f"Subject: [Success] Nightly server backup {number} (synthetic)\r\n"
        f"Date: Mon, 4 Jan 2027 0{number}:00:00 +0000\r\n"
        f"Message-ID: <imap-{number}@backup.example.com>\r\n\r\n"
        "Job finished.\r\n"
    ).encode()


def account(**fields: Any) -> MailboxAccount:
    values: dict[str, Any] = {
        "inbox_id": uuid.uuid4(),
        "host": "imap.example.com",
        "port": 993,
        "username": 'alerts "ops"@example.com',
        "password": PASSWORD,
        "folder": "Backup Alerts",
        "tls": True,
    }
    return MailboxAccount(**(values | fields))


class FakeImapClient:
    """Answers like imaplib.IMAP4 for a folder of messages (UID to bytes)."""

    def __init__(self, messages: dict[str, bytes], validity: bytes = b"7") -> None:
        self.messages = messages
        self.validity = validity
        self.seen: set[str] = set()
        self.commands: list[tuple[str, ...]] = []
        self.logged_out = False
        self.refuse_login = False
        self.refuse_select = False

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
        self.commands.append(("LOGIN", user))
        if self.refuse_login:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"Logged in"]

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        self.commands.append(("SELECT", mailbox))
        return ("NO", [b"no folder"]) if self.refuse_select else ("OK", [b"3"])

    def response(self, code: str) -> tuple[str, list[bytes]]:
        return code, [self.validity]

    def uid(self, command: str, *args: str) -> tuple[str, list[Any]]:
        self.commands.append((command, *args))
        if command == "SEARCH":
            unseen = [uid for uid in self.messages if uid not in self.seen]
            return "OK", [" ".join(unseen).encode()]
        if command == "STORE":
            self.seen.update(args[0].split(","))
            return "OK", []
        if args[1] == "(RFC822.SIZE)":
            sizes = [
                f"{n} (UID {uid} RFC822.SIZE {len(self.messages[uid])})".encode()
                for n, uid in enumerate(args[0].split(","), start=1)
            ]
            return "OK", sizes
        raw = self.messages[args[0]]
        return "OK", [(f"1 (UID {args[0]} BODY[] {{{len(raw)}}}".encode(), raw), b")"]

    def logout(self) -> tuple[str, list[bytes]]:
        self.logged_out = True
        return "BYE", []


async def test_fetch_peeks_at_unseen_mail_and_skips_oversize() -> None:
    folder = FakeImapClient(
        {"11": mail(1), "12": b"x" * (MAX_MESSAGE_BYTES + 1), "13": mail(3)}
    )
    connector = ImapConnector(lambda account: folder)
    fetched = await connector.fetch(account(), limit=50)
    assert [(message.ref, message.raw) for message in fetched] == [
        ("7:11", mail(1)),
        ("7:13", mail(3)),
    ]
    # The user name and folder are quoted; bodies are read with BODY.PEEK.
    assert ("LOGIN", '"alerts \\"ops\\"@example.com"') in folder.commands
    assert ("SELECT", '"Backup Alerts"') in folder.commands
    assert ("FETCH", "11", "(BODY.PEEK[])") in folder.commands
    assert ("FETCH", "12", "(BODY.PEEK[])") not in folder.commands
    # Nothing is Seen but the message that is never downloaded.
    assert folder.seen == {"12"} and folder.logged_out


async def test_fetch_takes_at_most_the_limit() -> None:
    folder = FakeImapClient({str(uid): mail(uid) for uid in range(1, 6)})
    fetched = await ImapConnector(lambda account: folder).fetch(account(), limit=2)
    assert [message.ref for message in fetched] == ["7:1", "7:2"]


async def test_acknowledge_marks_seen_only_refs_of_the_same_folder() -> None:
    folder = FakeImapClient({"11": mail(1), "12": mail(2)})
    connector = ImapConnector(lambda account: folder)
    # 6:12 was fetched before the folder was rebuilt (another UIDVALIDITY).
    await connector.acknowledge(account(), ["7:11", "6:12"])
    assert folder.seen == {"11"}
    commands = len(folder.commands)
    await connector.acknowledge(account(), [])
    assert len(folder.commands) == commands


async def test_a_refused_login_or_folder_raises_and_signs_out() -> None:
    folder = FakeImapClient({"11": mail(1)})
    folder.refuse_login = True
    with pytest.raises(imaplib.IMAP4.error):
        await ImapConnector(lambda account: folder).fetch(account(), limit=50)
    assert folder.logged_out
    folder = FakeImapClient({"11": mail(1)})
    folder.refuse_select = True
    with pytest.raises(ImapError, match="SELECT"):
        await ImapConnector(lambda account: folder).fetch(account(), limit=50)


def test_open_client_verifies_tls_unless_the_inbox_says_plain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def recorder(kind: str) -> Callable[..., str]:
        def build(*args: Any, **kwargs: Any) -> str:
            opened.append((kind, args, kwargs))
            return kind

        return build

    monkeypatch.setattr(imaplib, "IMAP4_SSL", recorder("tls"))
    monkeypatch.setattr(imaplib, "IMAP4", recorder("plain"))
    assert imap.open_client(account()) == "tls"
    assert imap.open_client(account(tls=False, port=143)) == "plain"
    tls, plain = opened
    assert tls[1] == ("imap.example.com", 993)
    context = tls[2]["ssl_context"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert tls[2]["timeout"] == plain[2]["timeout"] == 30
    assert plain[1] == ("imap.example.com", 143)


def test_quote_escapes_backslashes_and_quotes() -> None:
    assert quote('a"b\\c') == '"a\\"b\\\\c"'


def test_the_account_repr_hides_the_password() -> None:
    assert PASSWORD not in repr(account())


class FakeMailbox:
    """A MailboxConnector over a dict of unseen messages (ref to bytes)."""

    kind = "imap"

    def __init__(
        self,
        messages: dict[str, bytes],
        on_acknowledge: Callable[[Sequence[str]], Awaitable[None]] | None = None,
    ) -> None:
        self.messages = messages
        self.seen: list[str] = []
        self.accounts: list[MailboxAccount] = []
        self.on_acknowledge = on_acknowledge

    async def fetch(
        self, account: MailboxAccount, *, limit: int
    ) -> Sequence[FetchedMessage]:
        self.accounts.append(account)
        unseen = [ref for ref in self.messages if ref not in self.seen]
        return [FetchedMessage(raw=self.messages[ref], ref=ref) for ref in unseen]

    async def acknowledge(self, account: MailboxAccount, refs: Sequence[str]) -> None:
        if self.on_acknowledge is not None:
            await self.on_acknowledge(refs)
        self.seen.extend(refs)


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


async def add_imap_inbox(context: WorkerContext, **fields: Any) -> Inbox:
    settings: dict[str, Any] = {
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "imap_username": "alerts@example.com",
        "imap_password_enc": context.secret_box.encrypt(PASSWORD),
        "imap_folder": "INBOX",
        "imap_poll_seconds": 60,
        "imap_tls": True,
    }
    async with context.sessionmaker() as db:
        inbox, _ = await InboxRepository(db, context.policy).create(
            SYSTEM,
            kind="imap",
            label="Vendor mailbox",
            now=context.clock.now(),
            **(settings | fields),
        )
        await db.commit()
    return inbox


async def stored_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        count = await connection.scalar(select(func.count()).select_from(RawMessage))
    return int(count or 0)


async def test_seen_only_after_the_commit_and_a_failure_stays_unseen(
    context: WorkerContext, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = await add_imap_inbox(context)
    committed_at_acknowledge: list[int] = []

    async def check(refs: Sequence[str]) -> None:
        # Another connection sees the rows: they were committed first.
        committed_at_acknowledge.append(await stored_count(db_engine))

    mailbox = FakeMailbox({"7:1": mail(1), "7:2": mail(2)}, check)
    poller = ImapPoller(context, connector=mailbox)

    async def failing(*args: Any, raw: bytes, **kwargs: Any) -> Any:
        if raw == mail(2):
            raise RuntimeError("database gone")
        return await accept_message(*args, raw=raw, **kwargs)

    monkeypatch.setattr(imap, "accept_message", failing)
    result = await poller.poll_inbox(inbox)
    assert result == PollResult(stored=1, failed=1)
    assert committed_at_acknowledge == [1]
    assert mailbox.seen == ["7:1"]

    # The next poll fetches the unseen message again and stores it.
    monkeypatch.setattr(imap, "accept_message", accept_message)
    assert await poller.poll_inbox(inbox) == PollResult(stored=1)
    assert mailbox.seen == ["7:1", "7:2"]
    assert await stored_count(db_engine) == 2


async def test_duplicates_and_refused_senders_are_marked_seen(
    context: WorkerContext, db_engine: AsyncEngine
) -> None:
    inbox = await add_imap_inbox(context, sender_allowlist=["@example.com"])
    mailbox = FakeMailbox(
        {
            "7:1": mail(1),
            "7:2": mail(1),
            "7:3": mail(3, sender="intruder@attacker.test"),
        }
    )
    result = await ImapPoller(context, connector=mailbox).poll_inbox(inbox)
    assert result == PollResult(stored=1, duplicates=1, refused=1)
    assert mailbox.seen == ["7:1", "7:2", "7:3"]
    assert await stored_count(db_engine) == 1


async def test_the_poller_decrypts_the_password_into_the_account(
    context: WorkerContext,
) -> None:
    inbox = await add_imap_inbox(context, imap_folder="Alerts", imap_tls=False)
    mailbox = FakeMailbox({})
    await ImapPoller(context, connector=mailbox).poll_inbox(inbox)
    (used,) = mailbox.accounts
    assert used.password == PASSWORD
    expected = ("imap.example.com", 993, "Alerts", False)
    assert (used.host, used.port, used.folder, used.tls) == expected


async def test_an_inbox_without_complete_settings_is_not_polled(
    context: WorkerContext,
) -> None:
    inbox = await add_imap_inbox(context, imap_password_enc=None)
    mailbox = FakeMailbox({"7:1": mail(1)})
    poller = ImapPoller(context, connector=mailbox)
    assert await poller.poll_inbox(inbox) == PollResult()
    assert mailbox.accounts == []


async def test_each_inbox_is_polled_after_its_poll_seconds(
    context: WorkerContext, clock: FakeClock
) -> None:
    fast = await add_imap_inbox(context, imap_poll_seconds=60)
    slow = await add_imap_inbox(context, imap_poll_seconds=600)
    mailbox = FakeMailbox({})
    poller = ImapPoller(context, connector=mailbox)

    async def polled() -> list[uuid.UUID]:
        mailbox.accounts.clear()
        await poller.poll_due()
        return [used.inbox_id for used in mailbox.accounts]

    assert sorted(await polled()) == sorted([fast.id, slow.id])
    assert await polled() == []
    clock.advance(seconds=60)
    assert await polled() == [fast.id]
    clock.advance(seconds=540)
    assert sorted(await polled()) == sorted([fast.id, slow.id])
    # A deleted inbox is forgotten.
    async with context.sessionmaker() as db:
        inboxes = InboxRepository(db, context.policy)
        found = await inboxes.get(SYSTEM, slow.id)
        assert found is not None
        await inboxes.delete(SYSTEM, found)
        await db.commit()
    clock.advance(seconds=600)
    assert await polled() == [fast.id]


async def test_a_failing_inbox_does_not_stop_the_others(
    context: WorkerContext, caplog: pytest.LogCaptureFixture
) -> None:
    broken = await add_imap_inbox(context, imap_password_enc="not-fernet-ciphertext")
    working = await add_imap_inbox(context)
    mailbox = FakeMailbox({})
    with caplog.at_level(logging.ERROR, logger="app.ingest.imap"):
        await ImapPoller(context, connector=mailbox).poll_due()
    assert [used.inbox_id for used in mailbox.accounts] == [working.id]
    failures = [r for r in caplog.records if r.getMessage() == "imap poll failed"]
    assert [getattr(r, "inbox_id", None) for r in failures] == [str(broken.id)]


async def test_the_receiver_polls_until_stopped(
    context: WorkerContext, caplog: pytest.LogCaptureFixture
) -> None:
    await add_imap_inbox(context)
    mailbox = FakeMailbox({"7:1": mail(1)})
    poller = ImapPoller(context, connector=mailbox, scan_seconds=0.01)
    caplog.set_level(logging.DEBUG)
    await poller.start(context)
    try:
        async with asyncio.timeout(5):
            while not mailbox.seen:
                await asyncio.sleep(0.01)
    finally:
        await poller.stop()
    await poller.stop()
    assert mailbox.seen == ["7:1"]
    # The password never reaches a log line.
    assert PASSWORD not in caplog.text
