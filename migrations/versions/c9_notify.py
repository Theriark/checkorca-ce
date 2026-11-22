"""Notifications: channel, channel_rule, notification (rnd-report-2 5.4).

Phase C9-B (dev-work-plan rev 35). Three new tables and nothing changed in the
earlier ones, so the previous release keeps running on this schema (one
release back). notification references flip and channel_rule names clients
and jobs by scope_id: both are in the client delete map
(app/repos/client_delete.py). channel holds no client data. Deleting a channel
deletes its rules and notifications, and deleting a flip its notifications,
so the previous release, whose delete map does not know the notification
table, can still delete a client. The kinds slack, teams and webhook are
allowed already, so phase C9-I adds them without a schema change.

Revision ID: c9_notify
Revises: c7_eval
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9_notify"
down_revision: str | None = "c7_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
CHANNEL_KINDS = ("email", "slack", "teams", "webhook")
RULE_EVENTS = ("failing", "missed", "warning", "recovered", "digest")
NOTIFICATION_EVENTS = (
    "failing",
    "missed",
    "warning",
    "recovered",
    "reminder",
    "digest",
)


def one_of(column: str, values: tuple[str, ...]) -> str:
    """The check of app/db/models.py: column IN ('a', 'b')."""
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def all_of(column: str, values: tuple[str, ...]) -> str:
    """The array check of app/db/models.py: not empty, only these values."""
    listed = ", ".join(repr(value) for value in values)
    array = f"ARRAY[{listed}]::character varying[]"
    return f"cardinality({column}) > 0 AND {column} <@ {array}"


def upgrade() -> None:
    op.create_table(
        "channel",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_status_at", TIMESTAMP, nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(one_of("kind", CHANNEL_KINDS), name=op.f("ck_channel_kind")),
        sa.CheckConstraint(
            one_of("last_status", ("sent", "failed")),
            name=op.f("ck_channel_last_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel")),
    )
    op.create_table(
        "channel_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("events", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            one_of("scope", ("all", "client", "job")),
            name=op.f("ck_channel_rule_scope"),
        ),
        sa.CheckConstraint(
            "(scope = 'all') = (scope_id IS NULL)",
            name=op.f("ck_channel_rule_scope_id"),
        ),
        sa.CheckConstraint(
            all_of("events", RULE_EVENTS), name=op.f("ck_channel_rule_events")
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channel.id"],
            name=op.f("fk_channel_rule_channel_id_channel"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_rule")),
    )
    op.create_index(
        op.f("ix_channel_rule_channel_id"), "channel_rule", ["channel_id"], unique=False
    )
    op.create_index(
        "ix_channel_rule_scope_scope_id",
        "channel_rule",
        ["scope", "scope_id"],
        unique=False,
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("flip_id", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("digest_day", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("next_attempt_at", TIMESTAMP, nullable=True),
        sa.Column("last_attempt_at", TIMESTAMP, nullable=True),
        sa.Column("sent_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            one_of("event", NOTIFICATION_EVENTS), name=op.f("ck_notification_event")
        ),
        sa.CheckConstraint(
            one_of("status", ("queued", "sent", "retrying", "failed")),
            name=op.f("ck_notification_status"),
        ),
        sa.CheckConstraint(
            "(event = 'digest') = (flip_id IS NULL) "
            "AND (event = 'digest') = (digest_day IS NOT NULL)",
            name=op.f("ck_notification_subject"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channel.id"],
            name=op.f("fk_notification_channel_id_channel"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["flip_id"],
            ["flip.id"],
            name=op.f("fk_notification_flip_id_flip"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
        sa.UniqueConstraint(
            "flip_id",
            "channel_id",
            "event",
            name=op.f("uq_notification_flip_id_channel_id_event"),
        ),
        sa.UniqueConstraint(
            "channel_id",
            "digest_day",
            name=op.f("uq_notification_channel_id_digest_day"),
        ),
    )
    op.create_index(
        op.f("ix_notification_created_at"), "notification", ["created_at"], unique=False
    )
    op.create_index(
        "ix_notification_status_next_attempt_at",
        "notification",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_status_next_attempt_at", table_name="notification")
    op.drop_index(op.f("ix_notification_created_at"), table_name="notification")
    op.drop_table("notification")
    op.drop_index("ix_channel_rule_scope_scope_id", table_name="channel_rule")
    op.drop_index(op.f("ix_channel_rule_channel_id"), table_name="channel_rule")
    op.drop_table("channel_rule")
    op.drop_table("channel")
