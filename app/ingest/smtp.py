"""The SMTP listener on container port 2525 (rnd-report-2 5.7).

aiosmtpd 1.4.6 serves on the worker's event loop while the worker holds its
lock (app/worker/loop.py, RECEIVERS), so one listener runs per installation.
It only receives: it never relays, never sends a bounce and needs no
authentication, because an inbox address is its secret (code@MAIL_DOMAIN,
24 random characters).

Limits, every one answered with an SMTP code the sender understands:
- RCPT: an address that is not code@MAIL_DOMAIN of an smtp inbox gets 550;
  past 20 recipients a message gets 452; the 11th unknown address of a
  connection gets 421 and the connection is closed.
- MAIL: 60 messages a minute per source address (451 above that).
- DATA: 5 MB, advertised as SIZE and checked again in handle_DATA, and at
  most 256 KB of headers (552); the inbox's sender rules
  (app/ingest/receive.py) answer 550.
- 30 seconds without a command closes the connection; at most 20 connections
  at a time and 3 per source address (421 for the next one).
- STARTTLS when SMTP_TLS_CERT_FILE and SMTP_TLS_KEY_FILE name mounted PEM
  files; plain SMTP otherwise.

A message for several inboxes is stored once per inbox in one transaction,
and 250 is answered only after the commit. A database error answers 451, so
the sender retries and the duplicate keys keep one row. Logs carry counts,
never an address, a code or the message.
"""

import asyncio
import logging
import re
import ssl
import uuid
from typing import TYPE_CHECKING, Any, Final

from aiosmtpd.smtp import SMTP, Envelope, Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import SYSTEM
from app.db.models import Inbox
from app.ingest.receive import MessageRefused, accept_message, check_size
from app.ingest.store import MAX_MESSAGE_BYTES, MessageTooLarge
from app.repos.inboxes import InboxRepository
from app.security.ratelimit import RateLimiter
from app.settings import Settings

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

TIMEOUT_SECONDS: Final = 30.0
MAX_RECIPIENTS: Final = 20
# Messages a minute per source address.
SOURCE_RATE: Final = (60, 60.0)
MAX_SESSIONS: Final = 20
# One source address may not hold every session.
MAX_SESSIONS_PER_SOURCE: Final = 3
# Unknown recipients a connection may try before it is closed.
MAX_UNKNOWN_RECIPIENTS: Final = 10
# The greeting names the product, not the library and its version.
IDENT: Final = "Checkorca-CE ESMTP"
STOP_SECONDS: Final = 5.0
# An inbox code is 24 letters and digits; anything else is never looked up.
_CODE = re.compile(r"[a-z0-9]{1,64}")

logger = logging.getLogger(__name__)


def tls_context(settings: Settings) -> ssl.SSLContext | None:
    """The STARTTLS context from the mounted certificate files, or None."""
    if not settings.smtp_tls_cert_file:
        return None
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(settings.smtp_tls_cert_file, settings.smtp_tls_key_file)
    return context


def source_address(session: Session) -> str:
    """The sender's IP address, the key of its rate limit."""
    peer: object = session.peer
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return str(peer)


class InboxHandler:
    """The aiosmtpd hooks: the rate limit at MAIL, inbox codes at RCPT, the
    store at DATA."""

    def __init__(self, context: "WorkerContext", limiter: RateLimiter) -> None:
        self.context = context
        self.limiter = limiter
        self.domain = context.settings.inbox_domain.lower()

    async def _find(self, db: AsyncSession, address: str) -> Inbox | None:
        local, _, domain = address.rpartition("@")
        local = local.lower()
        if domain.lower() != self.domain or not _CODE.fullmatch(local):
            return None
        inboxes = InboxRepository(db, self.context.policy)
        return await inboxes.find_by_code(SYSTEM, local, kinds=("smtp",))

    async def handle_MAIL(
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
        address: str,
        mail_options: list[str],
    ) -> str:
        if self.limiter.hit(f"smtp:{source_address(session)}") > 0:
            return "451 4.7.1 Too many messages from this address, try again later"
        envelope.mail_from = address
        envelope.mail_options.extend(mail_options)
        return "250 OK"

    async def handle_RCPT(
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
        address: str,
        rcpt_options: list[str],
    ) -> str:
        if len(envelope.rcpt_tos) >= MAX_RECIPIENTS:
            return "452 4.5.3 Too many recipients"
        try:
            async with self.context.sessionmaker() as db:
                inbox = await self._find(db, address)
        except Exception as error:
            logger.error("smtp inbox lookup failed", exc_info=error)
            return "451 4.3.0 Temporary failure, try again later"
        if inbox is None:
            if isinstance(server, _Session) and server.unknown_recipient():
                return "421 4.7.0 Too many unknown recipients, closing connection"
            return "550 5.1.1 No such inbox"
        envelope.rcpt_tos.append(address)
        envelope.rcpt_options.extend(rcpt_options)
        return "250 OK"

    async def handle_DATA(
        self, server: SMTP, session: Session, envelope: Envelope
    ) -> str:
        raw = envelope.original_content or b""
        try:
            check_size(raw)
        except MessageTooLarge:
            return "552 5.3.4 Message too big"
        received_at = self.context.clock.now()
        counts = {"stored": 0, "duplicates": 0, "refused": 0}
        found: dict[uuid.UUID, Inbox] = {}
        try:
            async with self.context.sessionmaker() as db:
                for address in envelope.rcpt_tos:
                    inbox = await self._find(db, address)
                    if inbox is not None:
                        found.setdefault(inbox.id, inbox)
                for inbox in found.values():
                    try:
                        stored = await accept_message(
                            db,
                            self.context.policy,
                            SYSTEM,
                            inbox=inbox,
                            raw=raw,
                            received_at=received_at,
                        )
                    except MessageRefused:
                        counts["refused"] += 1
                        continue
                    counts["duplicates" if stored.duplicate else "stored"] += 1
                await db.commit()
        except Exception as error:
            logger.error("smtp message not stored", exc_info=error)
            return "451 4.3.0 Temporary failure, try again later"
        if not found:
            return "550 5.1.1 No such inbox"
        logger.info("smtp message received", extra=counts)
        if counts["refused"] == len(found):
            return "550 5.7.1 Refused by the inbox's sender rules"
        return "250 2.0.0 Message accepted"

    async def handle_exception(self, error: Exception) -> str:
        # aiosmtpd's default answer repeats the exception text to the sender.
        logger.error("smtp session failed", exc_info=error)
        return "451 4.3.0 Temporary failure, try again later"


class _Session(SMTP):
    """One SMTP connection; past max_sessions in all, or max_per_source from
    its address, a new one gets 421 and is closed."""

    def __init__(
        self,
        handler: InboxHandler,
        *,
        sessions: set["_Session"],
        max_sessions: int,
        max_per_source: int,
        **options: Any,
    ) -> None:
        super().__init__(handler, **options)
        self._sessions = sessions
        self._max_sessions = max_sessions
        self._max_per_source = max_per_source
        self._refused = False
        self.source_ip = ""
        self.unknown_recipients = 0

    def _full(self) -> bool:
        same_source = sum(
            1 for other in self._sessions if other.source_ip == self.source_ip
        )
        return (
            len(self._sessions) >= self._max_sessions
            or same_source >= self._max_per_source
        )

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        # STARTTLS calls this again for the same session.
        if self not in self._sessions:
            peer = transport.get_extra_info("peername")
            self.source_ip = str(peer[0]) if isinstance(peer, tuple) and peer else ""
            if self._full():
                self._refused = True
                if isinstance(transport, asyncio.WriteTransport):
                    transport.write(
                        b"421 4.7.0 Too many connections, try again later\r\n"
                    )
                transport.close()
                return
            self._sessions.add(self)
        super().connection_made(transport)

    def unknown_recipient(self) -> bool:
        """Count a refused RCPT; True (and the connection closes after the
        answer) once there were more than MAX_UNKNOWN_RECIPIENTS."""
        self.unknown_recipients += 1
        if self.unknown_recipients <= MAX_UNKNOWN_RECIPIENTS:
            return False
        # Runs after aiosmtpd has written the 421: close() sends it first.
        asyncio.get_running_loop().call_soon(self.close)
        return True

    def connection_lost(self, error: Exception | None) -> None:
        self._sessions.discard(self)
        if not self._refused:
            super().connection_lost(error)

    def eof_received(self) -> bool | None:
        if self._refused:
            return False
        return super().eof_received()

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()


class SmtpReceiver:
    """The SMTP listener as a worker receiver (app/worker/loop.py)."""

    name = "smtp"

    def __init__(
        self,
        context: "WorkerContext",
        *,
        host: str = "0.0.0.0",
        port: int | None = None,
        timeout: float = TIMEOUT_SECONDS,
        max_sessions: int = MAX_SESSIONS,
        max_per_source: int = MAX_SESSIONS_PER_SOURCE,
    ) -> None:
        self.host = host
        self.port = context.settings.smtp_port if port is None else port
        self.timeout = timeout
        self.max_sessions = max_sessions
        self.max_per_source = max_per_source
        limiter = RateLimiter(*SOURCE_RATE, clock=context.clock)
        self.handler = InboxHandler(context, limiter)
        self._server: asyncio.Server | None = None
        self._sessions: set[_Session] = set()

    async def start(self, context: "WorkerContext") -> None:
        tls = tls_context(context.settings)
        loop = asyncio.get_running_loop()

        def session() -> _Session:
            return _Session(
                self.handler,
                sessions=self._sessions,
                max_sessions=self.max_sessions,
                max_per_source=self.max_per_source,
                data_size_limit=MAX_MESSAGE_BYTES,
                hostname=context.settings.inbox_domain,
                ident=IDENT,
                tls_context=tls,
                timeout=self.timeout,
                loop=loop,
            )

        self._server = await loop.create_server(session, self.host, self.port)
        self.port = int(self._server.sockets[0].getsockname()[1])
        logger.info(
            "smtp listener started",
            extra={"port": self.port, "starttls": tls is not None},
        )

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        server.close()
        for session in list(self._sessions):
            session.close()
        try:
            await asyncio.wait_for(server.wait_closed(), timeout=STOP_SECONDS)
        except TimeoutError:
            logger.warning("smtp listener stopped with connections still open")
