"""Sign-in and access: app_user, app_session, api_token, audit_event, settings.

Phase C1-B (dev-work-plan rev 35). Creates the five tables and the single
settings row with the defaults of the Settings chapter.

Revision ID: c1_auth
Revises: c0_baseline
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1_auth"
down_revision: str | None = "c0_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "failed_logins", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("locked_until", TIMESTAMP, nullable=True),
        sa.Column(
            "disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'technician')", name=op.f("ck_app_user_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("email", name=op.f("uq_app_user_email")),
    )
    op.create_table(
        "app_session",
        sa.Column("id_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("last_seen_at", TIMESTAMP, nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_app_session_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_hash", name=op.f("pk_app_session")),
    )
    op.create_index(
        op.f("ix_app_session_user_id"), "app_session", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_app_session_expires_at"), "app_session", ["expires_at"], unique=False
    )
    op.create_table(
        "api_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("last_used_at", TIMESTAMP, nullable=True),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            "scope IN ('ingest', 'read')", name=op.f("ck_api_token_scope")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_api_token_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_token")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_api_token_token_sha256")),
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("at", TIMESTAMP, nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
    )
    op.create_index(op.f("ix_audit_event_at"), "audit_event", ["at"], unique=False)
    settings = op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column(
            "digest_time_local",
            sa.Time(),
            server_default=sa.text("'07:30'"),
            nullable=False,
        ),
        sa.Column(
            "digest_timezone",
            sa.String(64),
            server_default=sa.text("'Europe/Lisbon'"),
            nullable=False,
        ),
        sa.Column(
            "retention_raw_days",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "retention_results_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
        ),
        sa.Column(
            "retention_audit_days",
            sa.Integer(),
            server_default=sa.text("365"),
            nullable=False,
        ),
        sa.Column("external_heartbeat_url_enc", sa.Text(), nullable=True),
        sa.Column(
            "reminder_24h",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "demo_seeded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_settings_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
    )
    assert settings is not None
    # The one row; every other column takes its server default.
    op.bulk_insert(settings, [{"id": 1}])


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index(op.f("ix_audit_event_at"), table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_table("api_token")
    op.drop_index(op.f("ix_app_session_expires_at"), table_name="app_session")
    op.drop_index(op.f("ix_app_session_user_id"), table_name="app_session")
    op.drop_table("app_session")
    op.drop_table("app_user")
