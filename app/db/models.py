"""Tables of phases C1 (users, sessions, API tokens, audit events, settings)
and C3 (clients and jobs).

Revisions c1_auth and c3_jobs create them; later phases add their tables
here. Primary keys are UUIDs, timestamps UTC. No table stores a secret in clear
text: sessions and API tokens keep a SHA-256 hash, passwords an Argon2id hash,
and stored credentials (columns ending in _enc) Fernet ciphertext.
"""

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

USER_ROLES = ("admin", "technician")
TOKEN_SCOPES = ("ingest", "read")
JOB_KINDS = ("backup", "script", "other")
SCHEDULE_KINDS = ("cron", "interval", "daily")
ATTRIBUTION_BASES = ("started", "finished", "received")
WARNING_POLICIES = ("warning_is_attention", "warning_counts_ok")
NAME_LENGTH = 200


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
