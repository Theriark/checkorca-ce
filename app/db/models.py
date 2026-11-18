"""Tables of phase C1: users, sessions, API tokens, audit events, settings.

Revision c1_auth creates them; later phases add their tables here. Primary keys
are UUIDs, timestamps UTC. No table stores a secret in clear text: sessions and
API tokens keep a SHA-256 hash, passwords an Argon2id hash, and stored
credentials (columns ending in _enc) Fernet ciphertext.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

USER_ROLES = ("admin", "technician")
TOKEN_SCOPES = ("ingest", "read")


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
