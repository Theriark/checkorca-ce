"""Tables of phases C1 (users, sessions, API tokens, audit events, settings),
C3 (clients and jobs), C4 (inboxes, raw messages, results, the worker
heartbeat), C5 (parser packs) and C7 (occurrences, job states, flips).

Revisions c1_auth, c3_jobs, c4_ingest, c5_packs and c7_eval create them;
later phases add their tables here. Primary keys are UUIDs, timestamps UTC.
No table stores a secret in clear text: sessions, API tokens and webhook
inbox tokens keep a SHA-256 hash, passwords an Argon2id hash, and stored
credentials (columns ending in _enc) Fernet ciphertext.
"""

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.evaluator.model import JOB_STATES, OCCURRENCE_STATES
from app.ingest.mime import MESSAGE_ID_LENGTH

USER_ROLES = ("admin", "technician")
TOKEN_SCOPES = ("ingest", "read")
JOB_KINDS = ("backup", "script", "other")
SCHEDULE_KINDS = ("cron", "interval", "daily")
ATTRIBUTION_BASES = ("started", "finished", "received")
WARNING_POLICIES = ("warning_is_attention", "warning_counts_ok")
INBOX_KINDS = ("smtp", "imap", "webhook", "upload")
PARSE_STATES = ("pending", "parsed", "unmatched", "error")
RESULT_STATUSES = ("success", "warning", "failed", "started", "unknown")
PACK_STATUSES = ("verified", "unverified-synthetic")
PACK_SOURCES = ("builtin", "custom")
NAME_LENGTH = 200
# A pack id (^[a-z0-9][a-z0-9._-]*$, at most 100) and a JSON Pointer into a pack.
PACK_ID_LENGTH = 100
PACK_PATH_LENGTH = 300
# The evaluator's notes and flip reasons (app/evaluator/machine.py).
NOTE_LENGTH = 200
REASON_LENGTH = 300


def name_key(name: str) -> str:
    """The form names are compared in: inner spaces collapsed, case folded."""
    return " ".join(name.split()).casefold()


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class AppUser(Base):
    """A local account. E-mail addresses are stored in lower case."""

    __tablename__ = "app_user"
    __table_args__ = (CheckConstraint("role IN ('admin', 'technician')", name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    failed_logins: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None]
    disabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime]


class AppSession(Base):
    """A signed-in browser. The cookie holds a secret; the row keeps its hash."""

    __tablename__ = "app_session"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    last_seen_at: Mapped[datetime]
    ip: Mapped[str | None] = mapped_column(String(45))


class ApiToken(Base):
    """An API token for scripts. Only the SHA-256 of the token is stored."""

    __tablename__ = "api_token"
    __table_args__ = (CheckConstraint("scope IN ('ingest', 'read')", name="scope"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(String(16))
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime]
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class AuditEvent(Base):
    """Who did what to which id, from where. Ids and names, never content."""

    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    at: Mapped[datetime] = mapped_column(index=True)
    # "user:<id>", "token:<id>", "system" or "anonymous".
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_kind: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )


class AppSettings(Base):
    """The single settings row (id 1) of the Settings chapter."""

    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, autoincrement=False, default=1
    )
    digest_time_local: Mapped[time] = mapped_column(
        Time, default=time(7, 30), server_default=text("'07:30'")
    )
    digest_timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Lisbon", server_default=text("'Europe/Lisbon'")
    )
    retention_raw_days: Mapped[int] = mapped_column(
        default=30, server_default=text("30")
    )
    retention_results_days: Mapped[int] = mapped_column(
        default=90, server_default=text("90")
    )
    retention_audit_days: Mapped[int] = mapped_column(
        default=365, server_default=text("365")
    )
    # Fernet ciphertext: a heartbeat URL usually carries its own secret.
    external_heartbeat_url_enc: Mapped[str | None] = mapped_column(Text)
    reminder_24h: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    demo_seeded: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )


class Client(Base):
    """A customer of the MSP (rnd-report-2 5.4). Names are unique by name_key."""

    __tablename__ = "client"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    name_key: Mapped[str] = mapped_column(String(NAME_LENGTH), unique=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    # Other names the matcher accepts for this client (phase C5).
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(NAME_LENGTH)),
        default=list,
        server_default=text("'{}'::character varying[]"),
    )
    archived: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime]


class Job(Base):
    """A job that should report on a schedule (rnd-report-2 5.4).

    No foreign key here cascades from client: deleting a client goes through
    the delete map of app/repos/client_delete.py, so a table missing from the
    map makes the delete fail instead of leaving rows behind.
    """

    __tablename__ = "job"
    __table_args__ = (
        UniqueConstraint("client_id", "name_key"),
        CheckConstraint(_one_of("kind", JOB_KINDS), name="kind"),
        CheckConstraint(_one_of("schedule_kind", SCHEDULE_KINDS), name="schedule_kind"),
        CheckConstraint(
            _one_of("attribution_basis", ATTRIBUTION_BASES), name="attribution_basis"
        ),
        CheckConstraint(
            _one_of("warning_policy", WARNING_POLICIES), name="warning_policy"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("client.id"))
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    name_key: Mapped[str] = mapped_column(String(NAME_LENGTH))
    kind: Mapped[str] = mapped_column(String(16))
    parser_pack_id: Mapped[str | None] = mapped_column(String(100))
    match_key: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    schedule_kind: Mapped[str] = mapped_column(String(16))
    schedule_expr: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64))
    max_runtime_minutes: Mapped[int] = mapped_column(
        default=360, server_default=text("360")
    )
    grace_minutes: Mapped[int] = mapped_column(default=120, server_default=text("120"))
    escalate_minutes: Mapped[int] = mapped_column(default=30, server_default=text("30"))
    attribution_basis: Mapped[str] = mapped_column(
        String(16), default="finished", server_default=text("'finished'")
    )
    warning_policy: Mapped[str] = mapped_column(
        String(32),
        default="warning_is_attention",
        server_default=text("'warning_is_attention'"),
    )
    consecutive_failures_to_alert: Mapped[int] = mapped_column(
        default=1, server_default=text("1")
    )
    # 24 random letters and digits: the job's ping URL (phase C4).
    ping_token: Mapped[str] = mapped_column(String(24), unique=True)
    # False: paused until resumed. paused_until: paused until that time.
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    paused_until: Mapped[datetime | None]
    archived: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # The anchor of an interval schedule.
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None]


class Inbox(Base):
    """Where alert mail and webhooks arrive (rnd-report-2 5.4 and 5.7).

    code is 24 random lower-case letters and digits: the local part of an smtp
    inbox's address and the last part of a webhook inbox's ingest URL. It is
    stored plain because the SMTP listener looks it up at RCPT time. A webhook
    inbox also has a token, shown once and stored as SHA-256. The IMAP
    password is Fernet ciphertext and never leaves the server (D-6).
    """

    __tablename__ = "inbox"
    __table_args__ = (CheckConstraint(_one_of("kind", INBOX_KINDS), name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(24), unique=True)
    token_sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    imap_host: Mapped[str | None] = mapped_column(String(253))
    imap_port: Mapped[int | None]
    imap_username: Mapped[str | None] = mapped_column(String(320))
    imap_password_enc: Mapped[str | None] = mapped_column(Text)
    imap_folder: Mapped[str | None] = mapped_column(String(200))
    imap_poll_seconds: Mapped[int | None]
    imap_tls: Mapped[bool | None]
    # Addresses (alerts@example.com) or whole domains (@example.com), lower case.
    sender_allowlist: Mapped[list[str]] = mapped_column(
        ARRAY(String(254)),
        default=list,
        server_default=text("'{}'::character varying[]"),
    )
    require_auth_results: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    last_message_at: Mapped[datetime | None]


class RawMessage(Base):
    """One received message, compressed, kept until purge_after (5.4).

    A message is stored once per inbox: the same Message-ID, or the same
    content hash (app/ingest/mime.py), is a duplicate. inbox_id becomes NULL
    when the inbox is deleted, so job history keeps its evidence until the
    purge. client_id is set by the matcher (phase C5) when every result of the
    message belongs to one client, so deleting that client deletes the message.
    """

    __tablename__ = "raw_message"
    __table_args__ = (
        CheckConstraint(_one_of("parse_state", PARSE_STATES), name="parse_state"),
        UniqueConstraint("inbox_id", "message_id"),
        UniqueConstraint("inbox_id", "body_sha256"),
        Index("ix_raw_message_parse_state_received_at", "parse_state", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    inbox_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inbox.id", ondelete="SET NULL")
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client.id"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(index=True)
    message_id: Mapped[str | None] = mapped_column(String(MESSAGE_ID_LENGTH))
    # SHA-256 of the message as received; body_sha256 is the duplicate key.
    sha256: Mapped[str] = mapped_column(String(64))
    body_sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    # [[name, value], ...] in the order received, decoded to text.
    headers: Mapped[list[list[str]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    body_zlib: Mapped[bytes] = mapped_column(LargeBinary)
    parse_state: Mapped[str] = mapped_column(
        String(16), default="pending", server_default=text("'pending'")
    )
    purge_after: Mapped[datetime] = mapped_column(index=True)
    # Written by the worker's parse hook (phase C5): when it parsed the
    # message, the pack that claimed it, and for unmatched or error the reason
    # (no-pack, tie, no-records; timeout, deadline, too-many-records, memory,
    # rejected) and the JSON Pointer of the pattern that failed.
    parsed_at: Mapped[datetime | None]
    parse_pack_id: Mapped[str | None] = mapped_column(String(PACK_ID_LENGTH))
    parse_reason: Mapped[str | None] = mapped_column(String(32))
    parse_path: Mapped[str | None] = mapped_column(String(PACK_PATH_LENGTH))


class JobResult(Base):
    """One run reported by a parsed message, a ping or the results API (5.4).

    job_id is NULL until the matcher binds the result to a job (Unmatched).
    """

    __tablename__ = "job_result"
    __table_args__ = (
        CheckConstraint(_one_of("status", RESULT_STATUSES), name="status"),
        Index("ix_job_result_job_id_received_at", "job_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id"))
    client_hint: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    job_name: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(index=True)
    raw_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_message.id"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    details: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )


class ParserPack(Base):
    """A parser pack (phase C5): its Pack YAML and whether it parses mail.

    Built-in packs (app/parsers/packs) are written here at start and stay
    read-only; a custom pack is stored by an admin or technician. enabled is
    the user's choice for both and survives the sync. No client data: the
    table is not in the client delete map.
    """

    __tablename__ = "parser_pack"
    __table_args__ = (
        CheckConstraint(_one_of("status", PACK_STATUSES), name="status"),
        CheckConstraint(_one_of("source", PACK_SOURCES), name="source"),
    )

    id: Mapped[str] = mapped_column(String(PACK_ID_LENGTH), primary_key=True)
    version: Mapped[int]
    vendor: Mapped[str] = mapped_column(String(NAME_LENGTH))
    status: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))
    yaml: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class WorkerHeartbeat(Base):
    """The single heartbeat row (id 1), written by the worker that holds the
    lock on every tick. /readyz and System status read it."""

    __tablename__ = "worker_heartbeat"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, autoincrement=False, default=1
    )
    beat_at: Mapped[datetime]
    # Host name and process id of the worker that holds the lock.
    holder: Mapped[str] = mapped_column(String(200))
    # When that worker took the lock.
    started_at: Mapped[datetime]


class Occurrence(Base):
    """One expected run of a job (phase C7, rnd-report-2 5.5).

    Written lazily by the evaluator for the last 14 days and up to 10 minutes
    ahead; the state is one of app/evaluator/model.py. result_id is the result
    that decided the state; it becomes NULL when that result is purged and
    the next evaluation decides again.
    """

    __tablename__ = "occurrence"
    __table_args__ = (
        CheckConstraint(_one_of("state", OCCURRENCE_STATES), name="state"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"), primary_key=True)
    scheduled_for: Mapped[datetime] = mapped_column(primary_key=True)
    deadline: Mapped[datetime]
    state: Mapped[str] = mapped_column(String(16))
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_result.id", ondelete="SET NULL"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(NOTE_LENGTH))
    evaluated_at: Mapped[datetime]


class JobStateRecord(Base):
    """What the evaluator keeps about a job between ticks (phase C7).

    state, since and last_success_at are the job's state, state_since and
    last_success_at in the API (paused is derived from the job itself).
    eval_from and suppressed carry pauses and archives (app/evaluator).
    evaluated_at, due_at, job_updated_at, result_count and result_last_at
    tell the worker whether the job needs another evaluation.
    """

    __tablename__ = "job_state"
    __table_args__ = (CheckConstraint(_one_of("state", JOB_STATES), name="state"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    since: Mapped[datetime | None]
    consecutive_failures: Mapped[int] = mapped_column(
        default=0, server_default=text("0")
    )
    last_success_at: Mapped[datetime | None]
    eval_from: Mapped[datetime | None]
    suppressed: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    evaluated_at: Mapped[datetime]
    due_at: Mapped[datetime | None]
    job_updated_at: Mapped[datetime]
    result_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    result_last_at: Mapped[datetime | None]


class Flip(Base):
    """One change of a job's state (phase C7): the single source of alerts.

    client_id is the job's client when the state changed. scheduled_for is the
    occurrence that caused it (C9 puts it in the webhook payload).
    """

    __tablename__ = "flip"
    __table_args__ = (
        CheckConstraint(_one_of("from_state", JOB_STATES), name="from_state"),
        CheckConstraint(_one_of("to_state", JOB_STATES), name="to_state"),
        Index("ix_flip_job_id_at", "job_id", "at"),
        Index("ix_flip_client_id_at", "client_id", "at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"))
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("client.id"))
    from_state: Mapped[str] = mapped_column(String(16))
    to_state: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(REASON_LENGTH))
    at: Mapped[datetime] = mapped_column(index=True)
    scheduled_for: Mapped[datetime | None]
