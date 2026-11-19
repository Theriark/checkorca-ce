"""Request and response bodies of the inbox, message, result and system
routes (C4). Field names follow the Interfaces chapter of the dev-work-plan.

Secrets are write-only (legal D-6): the IMAP password goes in, and only
secret_set and a masked hint come out. A webhook inbox's token is made by the
server and returned once (InboxCreated, InboxToken), like an API token.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Final, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.api.v1.job_schemas import clean_name
from app.api.v1.schemas import Body
from app.db.models import NAME_LENGTH
from app.ingest.results import ResultStatus

InboxKind = Literal["smtp", "imap", "webhook", "upload"]
ParseState = Literal["pending", "parsed", "unmatched", "error"]

MAX_SENDERS: Final = 100
_SENDER = re.compile(
    r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
)


def sender_entry(value: str) -> str:
    """An address (alerts@example.com) or a whole domain (@example.com)."""
    entry = value.strip().lower()
    if not _SENDER.fullmatch(entry):
        raise ValueError(
            "must be an address such as alerts@example.com or a domain such as"
            " @example.com"
        )
    return entry


def unique_entries(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def no_control(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("must not contain control characters")
    return value


InboxLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(clean_name),
]
Sender = Annotated[str, Field(max_length=254), AfterValidator(sender_entry)]
Senders = Annotated[
    list[Sender], Field(max_length=MAX_SENDERS), AfterValidator(unique_entries)
]
# A host name, IPv4 address or IPv6 address; the MSP's own mail server.
Host = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=253,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]
Port = Annotated[int, Field(ge=1, le=65535)]
Username = Annotated[
    str, StringConstraints(min_length=1, max_length=320), AfterValidator(no_control)
]
# Write-only. IMAP sends it as one quoted string or literal: no line breaks.
Password = Annotated[
    str, StringConstraints(min_length=1, max_length=1024), AfterValidator(no_control)
]
Folder = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(no_control),
]
PollSeconds = Annotated[int, Field(ge=60, le=86400)]


class ImapSettings(Body):
    """A mailbox the MSP already collects alert mail in."""

    host: Host
    port: Port = 993
    username: Username
    password: Password
    folder: Folder = "INBOX"
    poll_seconds: PollSeconds = 300
    tls: bool = True


class ImapPatch(Body):
    """Only the fields sent change; a password replaces the stored one."""

    host: Host | None = None
    port: Port | None = None
    username: Username | None = None
    password: Password | None = None
    folder: Folder | None = None
    poll_seconds: PollSeconds | None = None
    tls: bool | None = None


class NewInbox(Body):
    kind: InboxKind
    label: InboxLabel
    # Required for kind imap, refused for the other kinds.
    imap: ImapSettings | None = None
    sender_allowlist: Senders = []
    require_auth_results: bool = False

    @model_validator(mode="after")
    def _imap_only_for_imap(self) -> Self:
        if self.kind == "imap" and self.imap is None:
            raise ValueError("an imap inbox needs its imap settings")
        if self.kind != "imap" and self.imap is not None:
            raise ValueError("only an imap inbox has imap settings")
        return self


class InboxPatch(Body):
    """Only the fields sent change. The kind and the code never change."""

    label: InboxLabel | None = None
    imap: ImapPatch | None = None
    sender_allowlist: Senders | None = None
    require_auth_results: bool | None = None


class ImapOut(BaseModel):
    host: str | None
    port: int | None
    username: str | None
    folder: str | None
    poll_seconds: int | None
    tls: bool | None
    # The password itself is never returned (D-6).
    secret_set: bool
    secret_hint: str | None


class InboxOut(BaseModel):
    id: uuid.UUID
    kind: InboxKind
    label: str
    # smtp: code@MAIL_DOMAIN; null for the other kinds.
    address: str | None
    # smtp and webhook: where POST ingest/email takes raw RFC 822 mail.
    ingest_url: str | None
    imap: ImapOut | None
    # webhook: whether a token exists (its value was shown once).
    webhook_token_set: bool
    sender_allowlist: list[str]
    require_auth_results: bool
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


class InboxCreated(InboxOut):
    """The new inbox; webhook_token is in this answer only (webhook inboxes)."""

    webhook_token: str | None


class InboxToken(BaseModel):
    """A webhook inbox's new token, shown this once; the old one stops working."""

    webhook_token: str


class InboxPage(BaseModel):
    items: list[InboxOut]
    next_cursor: str | None


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID | None
    client_hint: str | None
    job_name: str | None
    status: ResultStatus
    started_at: datetime | None
    finished_at: datetime | None
    received_at: datetime
    raw_message_id: uuid.UUID | None
    run_id: str | None
    details: dict[str, Any]


class ResultPage(BaseModel):
    items: list[ResultOut]
    next_cursor: str | None


# A job's ping token: letters and digits (24 when made by Checkorca-CE).
PingToken = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9]+$")
]
ResultText = Annotated[str, StringConstraints(max_length=NAME_LENGTH)]


class NewResult(Body):
    """A run reported by a script (POST results). The job is named by job_id,
    by ping_token, or by client_hint and job_name for the matcher."""

    status: ResultStatus
    job_id: uuid.UUID | None = None
    ping_token: PingToken | None = None
    job_name: ResultText | None = None
    client_hint: ResultText | None = None
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    run_id: ResultText | None = None
    details: dict[str, Any] = {}

    @model_validator(mode="after")
    def _one_job_reference(self) -> Self:
        if self.job_id is not None and self.ping_token is not None:
            raise ValueError("send job_id or ping_token, not both")
        named = bool(self.client_hint and self.job_name)
        if self.job_id is None and self.ping_token is None and not named:
            raise ValueError("send job_id, ping_token, or client_hint and job_name")
        return self


class ResultAccepted(BaseModel):
    """The stored result; job_id is null until the matcher binds it."""

    result_id: uuid.UUID
    job_id: uuid.UUID | None


class MessageAccepted(BaseModel):
    """The stored message, or for a duplicate the earlier one; the worker
    parses it (parse_state pending)."""

    message_id: uuid.UUID
    duplicate: bool


class MessageOut(BaseModel):
    id: uuid.UUID
    inbox_id: uuid.UUID | None
    client_id: uuid.UUID | None
    received_at: datetime
    message_id: str | None
    size: int
    parse_state: ParseState
    # From the headers, decoded; shown as text, never as HTML.
    subject: str | None
    sender: str | None


class HeaderOut(BaseModel):
    name: str
    value: str


class MessageDetail(MessageOut):
    headers: list[HeaderOut]
    # The readable text of the message, at most 256 KB; never HTML to render.
    text: str
    text_truncated: bool
    results: list[ResultOut]


class MessagePage(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None


class WorkerStatus(BaseModel):
    heartbeat_at: datetime | None
    age_seconds: float | None
    # True when the heartbeat is older than 3 minutes or missing.
    stale: bool
    # Host name and process id of the worker that holds the lock.
    holder: str | None
    started_at: datetime | None


class InboxActivity(BaseModel):
    id: uuid.UUID
    kind: InboxKind
    label: str
    last_message_at: datetime | None


class QueueStatus(BaseModel):
    pending_messages: int


class SystemStatus(BaseModel):
    worker: WorkerStatus
    inboxes: list[InboxActivity]
    queue: QueueStatus
    version: str
    revision: str | None
