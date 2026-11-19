"""The IMAP poller: alert mail the MSP already collects in a mailbox.

The poller runs while the worker holds its lock (app/worker/loop.py,
RECEIVERS). Every SCAN_SECONDS it polls each imap inbox whose poll_seconds
have passed since its last poll, one inbox at a time:

1. Decrypt the password (only here, rnd-report-2 5.3) into a MailboxAccount,
   whose repr hides it.
2. ImapConnector.fetch: the unseen messages of the folder, at most
   FETCH_LIMIT, read with BODY.PEEK so the server does not mark them Seen.
3. accept_message and commit, one message per transaction.
4. ImapConnector.acknowledge: mark Seen what was stored or refused by the
   inbox's sender rules. A message whose store failed stays unseen and comes
   again with the next poll; the duplicate keys keep one row. A crash between
   the commit and the acknowledgement does the same.

imaplib blocks, so the connector runs it in a thread with a 30 second socket
timeout. TLS (port 993) verifies the server's certificate and name; tls false
is plain IMAP for a mail server on the MSP's own network. A message larger
than 5 MB is never downloaded: it is marked Seen and counted in the log. A
failed login or a lost connection is logged with the inbox id and the error
class and tried again at the inbox's next poll.
"""

import asyncio
import contextlib
import imaplib
import logging
import re
import ssl
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from app.access import SYSTEM
from app.db.models import Inbox
from app.ext.ingest import FetchedMessage, MailboxAccount, MailboxConnector
from app.ingest.receive import MessageRefused, accept_message
from app.ingest.store import MAX_MESSAGE_BYTES, MessageTooLarge
from app.repos.inboxes import InboxRepository

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

TIMEOUT_SECONDS: Final = 30.0
FETCH_LIMIT: Final = 50
# How often the poller looks for inboxes that are due; a new inbox waits at
# most this long for its first poll.
SCAN_SECONDS: Final = 30.0
DEFAULT_POLL_SECONDS: Final = 300
PAGE_SIZE: Final = 200

_UID = re.compile(rb"\bUID (\d+)")
_SIZE = re.compile(rb"\bRFC822\.SIZE (\d+)")

logger = logging.getLogger(__name__)

type ClientFactory = Callable[[MailboxAccount], imaplib.IMAP4]


class ImapError(Exception):
    """The server refused a command; the text names the command only."""


def open_client(account: MailboxAccount) -> imaplib.IMAP4:
    """A connection to the account's server: TLS with a verified certificate,
    or plain IMAP when the inbox says tls false."""
    if account.tls:
        return imaplib.IMAP4_SSL(
            account.host,
            account.port,
            ssl_context=ssl.create_default_context(),
            timeout=TIMEOUT_SECONDS,
        )
    return imaplib.IMAP4(account.host, account.port, timeout=TIMEOUT_SECONDS)


def quote(value: str) -> str:
    """An IMAP quoted string (imaplib sends the user name and folder as is)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ok(result: tuple[str, list[Any]], command: str) -> list[Any]:
    status, data = result
    if status != "OK":
        raise ImapError(f"{command} was refused")
    return data


def _mark_seen(client: imaplib.IMAP4, uids: list[str]) -> None:
    _ok(client.uid("STORE", ",".join(uids), "+FLAGS", "(\\Seen)"), "STORE")


class ImapConnector:
    """MailboxConnector for IMAP (app/ext/ingest.py). A ref is the folder's
    UIDVALIDITY and the message UID, so an acknowledgement never marks a
    message of a rebuilt folder."""

    kind = "imap"

    def __init__(self, connect: ClientFactory = open_client) -> None:
        self._connect = connect

    async def fetch(
        self, account: MailboxAccount, *, limit: int
    ) -> Sequence[FetchedMessage]:
        return await asyncio.to_thread(self._fetch, account, limit)

    async def acknowledge(self, account: MailboxAccount, refs: Sequence[str]) -> None:
        if refs:
            await asyncio.to_thread(self._acknowledge, account, list(refs))

    @contextlib.contextmanager
    def _folder(self, account: MailboxAccount) -> Iterator[tuple[imaplib.IMAP4, str]]:
        """Signed in with the account's folder selected, and its UIDVALIDITY."""
        client = self._connect(account)
        try:
            _ok(client.login(quote(account.username), account.password), "LOGIN")
            _ok(client.select(quote(account.folder)), "SELECT")
            _, data = client.response("UIDVALIDITY")
            validity = data[0].decode("ascii") if data and data[0] else ""
            yield client, validity
        finally:
            with contextlib.suppress(imaplib.IMAP4.error, OSError):
                client.logout()

    def _fetch(self, account: MailboxAccount, limit: int) -> list[FetchedMessage]:
        with self._folder(account) as (client, validity):
            found = _ok(client.uid("SEARCH", "UNSEEN"), "SEARCH")
            uids = [uid.decode("ascii") for uid in (found[0] or b"").split()][:limit]
            if not uids:
                return []
            sizes = _ok(client.uid("FETCH", ",".join(uids), "(RFC822.SIZE)"), "FETCH")
            size_of: dict[str, int] = {}
            for item in sizes:
                line = item[0] if isinstance(item, tuple) else item
                uid_match = _UID.search(line or b"")
                size_match = _SIZE.search(line or b"")
                if uid_match and size_match:
                    uid = uid_match.group(1).decode("ascii")
                    size_of[uid] = int(size_match.group(1))
            fetched: list[FetchedMessage] = []
            oversize: list[str] = []
            for uid in uids:
                if uid not in size_of:
                    continue
                if size_of[uid] > MAX_MESSAGE_BYTES:
                    oversize.append(uid)
                    continue
                data = _ok(client.uid("FETCH", uid, "(BODY.PEEK[])"), "FETCH")
                raw = next((item[1] for item in data if isinstance(item, tuple)), None)
                if isinstance(raw, bytes):
                    fetched.append(FetchedMessage(raw=raw, ref=f"{validity}:{uid}"))
            if oversize:
                _mark_seen(client, oversize)
                logger.warning(
                    "imap messages over 5 MB skipped",
                    extra={"inbox_id": str(account.inbox_id), "count": len(oversize)},
                )
            return fetched

    def _acknowledge(self, account: MailboxAccount, refs: list[str]) -> None:
        with self._folder(account) as (client, validity):
            uids = [
                uid
                for ref_validity, _, uid in (ref.partition(":") for ref in refs)
                if ref_validity == validity
            ]
            if uids:
                _mark_seen(client, uids)


@dataclass(frozen=True, slots=True)
class PollResult:
    """What one poll of one inbox did."""

    stored: int = 0
    duplicates: int = 0
    refused: int = 0
    failed: int = 0


class ImapPoller:
    """Polls the imap inboxes as a worker receiver (app/worker/loop.py)."""

    name = "imap"

    def __init__(
        self,
        context: "WorkerContext",
        *,
        connector: MailboxConnector | None = None,
        scan_seconds: float = SCAN_SECONDS,
    ) -> None:
        self.context = context
        self.connector: MailboxConnector = connector or ImapConnector()
        self.scan_seconds = scan_seconds
        # Inbox id to the monotonic time of its next poll.
        self._due: dict[uuid.UUID, float] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self, context: "WorkerContext") -> None:
        self._task = asyncio.create_task(self._run(), name="imap poller")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_due()
            except Exception as error:
                logger.error("imap poll round failed", exc_info=error)
            await asyncio.sleep(self.scan_seconds)

    async def _inboxes(self) -> list[Inbox]:
        found: list[Inbox] = []
        after: tuple[datetime, uuid.UUID] | None = None
        async with self.context.sessionmaker() as db:
            inboxes = InboxRepository(db, self.context.policy)
            while True:
                page = await inboxes.page(
                    SYSTEM, kind="imap", after=after, limit=PAGE_SIZE
                )
                found += page
                if len(page) < PAGE_SIZE:
                    return found
                after = (page[-1].created_at, page[-1].id)

    async def poll_due(self) -> None:
        """Poll every imap inbox that is due, then forget deleted inboxes."""
        now = self.context.clock.monotonic()
        inboxes = await self._inboxes()
        for inbox in inboxes:
            if self._due.get(inbox.id, now) > now:
                continue
            poll_seconds = inbox.imap_poll_seconds or DEFAULT_POLL_SECONDS
            self._due[inbox.id] = now + poll_seconds
            try:
                await self.poll_inbox(inbox)
            except Exception as error:
                logger.error(
                    "imap poll failed",
                    exc_info=error,
                    extra={"inbox_id": str(inbox.id)},
                )
        for gone in set(self._due) - {inbox.id for inbox in inboxes}:
            del self._due[gone]

    def account(self, inbox: Inbox) -> MailboxAccount | None:
        """The inbox's mailbox with the password decrypted; None when its
        settings are incomplete."""
        if not (inbox.imap_host and inbox.imap_username and inbox.imap_password_enc):
            return None
        return MailboxAccount(
            inbox_id=inbox.id,
            host=inbox.imap_host,
            port=inbox.imap_port or 993,
            username=inbox.imap_username,
            password=self.context.secret_box.decrypt(inbox.imap_password_enc),
            folder=inbox.imap_folder or "INBOX",
            tls=inbox.imap_tls is not False,
        )

    async def poll_inbox(self, inbox: Inbox) -> PollResult:
        """Fetch, store and acknowledge the inbox's unseen messages."""
        account = self.account(inbox)
        if account is None:
            return PollResult()
        fetched = await self.connector.fetch(account, limit=FETCH_LIMIT)
        counts = {"stored": 0, "duplicates": 0, "refused": 0, "failed": 0}
        handled: list[str] = []
        for message in fetched:
            try:
                async with self.context.sessionmaker() as db:
                    stored = await accept_message(
                        db,
                        self.context.policy,
                        SYSTEM,
                        inbox=inbox,
                        raw=message.raw,
                        received_at=self.context.clock.now(),
                    )
                    await db.commit()
            except (MessageRefused, MessageTooLarge):
                counts["refused"] += 1
            except Exception as error:
                # Left unseen: the next poll fetches it again.
                counts["failed"] += 1
                logger.error(
                    "imap message not stored",
                    exc_info=error,
                    extra={"inbox_id": str(inbox.id)},
                )
                continue
            else:
                counts["duplicates" if stored.duplicate else "stored"] += 1
            handled.append(message.ref)
        await self.connector.acknowledge(account, handled)
        if fetched:
            logger.info(
                "imap messages received", extra={"inbox_id": str(inbox.id), **counts}
            )
        return PollResult(**counts)
