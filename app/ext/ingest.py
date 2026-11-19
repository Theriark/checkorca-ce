"""Ingest seams (rnd-report-2 5.3): MailboxConnector and ResultSource.

MailboxConnector reads a mailbox the MSP already has. CE ships IMAP (phase
C4-I); EE adds the Microsoft 365 Graph connector. The worker stores each
fetched message with store_raw, commits, and only then acknowledges it, so a
crash between the two fetches the message again and the store keeps it once.

ResultSource delivers runs that do not arrive as e-mail. In CE the results API
and the ping URLs write results directly; EE adds vendor API pollers. The
worker records each result with record_result.

Both seams are frozen with the rest in phase C12 (EXTENSION_API_LEVEL 1).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.ingest.results import ParsedResult


@dataclass(frozen=True, slots=True)
class MailboxAccount:
    """Where a connector reads: an inbox's settings, password decrypted.

    Built by the worker for one poll and never logged or returned by the API.
    """

    inbox_id: uuid.UUID
    host: str
    port: int
    username: str
    password: str
    folder: str
    tls: bool

    def __repr__(self) -> str:
        # The password must not reach a log through a repr.
        return f"MailboxAccount(inbox_id={self.inbox_id}, host={self.host!r})"


@dataclass(frozen=True, slots=True)
class FetchedMessage:
    """One message as fetched: its bytes and the connector's reference to it
    (an IMAP UID), used to acknowledge it after the store committed."""

    raw: bytes
    ref: str


class MailboxConnector(Protocol):
    """Fetches new mail from one mailbox; kind is the inbox kind it serves."""

    kind: str

    async def fetch(
        self, account: MailboxAccount, *, limit: int
    ) -> Sequence[FetchedMessage]:
        """At most limit messages not yet acknowledged."""
        ...

    async def acknowledge(self, account: MailboxAccount, refs: Sequence[str]) -> None:
        """Mark the messages as handled (IMAP: Seen), after the commit."""
        ...


@dataclass(frozen=True, slots=True)
class SourcedResult:
    """A run from a ResultSource: the result and, when the source knows it,
    the job it belongs to."""

    result: ParsedResult
    job_id: uuid.UUID | None = None


class ResultSource(Protocol):
    """Delivers runs that do not arrive as e-mail; name identifies it in logs."""

    name: str

    async def poll(self, now: datetime) -> Sequence[SourcedResult]:
        """The runs reported since the previous poll."""
        ...
