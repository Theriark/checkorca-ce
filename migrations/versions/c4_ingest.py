"""Ingest: inbox, raw_message (plus client_id), job_result, worker_heartbeat
(rnd-report-2 5.4).

Phase C4-B (dev-work-plan rev 35). Four new tables and nothing changed in the
C1 and C3 tables, so the previous release keeps running on this schema (one
release back). raw_message and job_result hold client data: both are in the
client delete map (app/repos/client_delete.py); no foreign key to client or
job cascades.

Revision ID: c4_ingest
Revises: c3_jobs
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4_ingest"
down_revision: str | None = "c3_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "inbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=True),
        sa.Column("imap_host", sa.String(253), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=True),
        sa.Column("imap_username", sa.String(320), nullable=True),
        sa.Column("imap_password_enc", sa.Text(), nullable=True),
        sa.Column("imap_folder", sa.String(200), nullable=True),
        sa.Column("imap_poll_seconds", sa.Integer(), nullable=True),
        sa.Column("imap_tls", sa.Boolean(), nullable=True),
        sa.Column(
            "sender_allowlist",
            postgresql.ARRAY(sa.String(254)),
            server_default=sa.text("'{}'::character varying[]"),
            nullable=False,
        ),
        sa.Column(
            "require_auth_results",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.Column("last_message_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            "kind IN ('smtp', 'imap', 'webhook', 'upload')", name=op.f("ck_inbox_kind")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox")),
        sa.UniqueConstraint("code", name=op.f("uq_inbox_code")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_inbox_token_sha256")),
    )
    op.create_table(
        "raw_message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inbox_id", sa.Uuid(), nullable=True),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column("received_at", TIMESTAMP, nullable=False),
        sa.Column("message_id", sa.String(998), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("body_zlib", sa.LargeBinary(), nullable=False),
        sa.Column(
            "parse_state",
            sa.String(16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("purge_after", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            "parse_state IN ('pending', 'parsed', 'unmatched', 'error')",
            name=op.f("ck_raw_message_parse_state"),
        ),
        sa.ForeignKeyConstraint(
            ["inbox_id"],
            ["inbox.id"],
            name=op.f("fk_raw_message_inbox_id_inbox"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["client.id"], name=op.f("fk_raw_message_client_id_client")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_message")),
        sa.UniqueConstraint(
            "inbox_id", "message_id", name=op.f("uq_raw_message_inbox_id_message_id")
        ),
        sa.UniqueConstraint(
            "inbox_id", "body_sha256", name=op.f("uq_raw_message_inbox_id_body_sha256")
        ),
    )
    op.create_index(
        op.f("ix_raw_message_client_id"), "raw_message", ["client_id"], unique=False
    )
    op.create_index(
        op.f("ix_raw_message_received_at"), "raw_message", ["received_at"], unique=False
    )
    op.create_index(
        op.f("ix_raw_message_purge_after"), "raw_message", ["purge_after"], unique=False
    )
    op.create_index(
        "ix_raw_message_parse_state_received_at",
        "raw_message",
        ["parse_state", "received_at"],
        unique=False,
    )
    op.create_table(
        "job_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("client_hint", sa.String(200), nullable=True),
        sa.Column("job_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.Column("received_at", TIMESTAMP, nullable=False),
        sa.Column("raw_message_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.String(200), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('success', 'warning', 'failed', 'started', 'unknown')",
            name=op.f("ck_job_result_status"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_job_result_job_id_job")
        ),
        sa.ForeignKeyConstraint(
            ["raw_message_id"],
            ["raw_message.id"],
            name=op.f("fk_job_result_raw_message_id_raw_message"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_result")),
    )
    op.create_index(
        op.f("ix_job_result_received_at"), "job_result", ["received_at"], unique=False
    )
    op.create_index(
        op.f("ix_job_result_raw_message_id"),
        "job_result",
        ["raw_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_result_job_id_received_at",
        "job_result",
        ["job_id", "received_at"],
        unique=False,
    )
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("beat_at", TIMESTAMP, nullable=False),
        sa.Column("holder", sa.String(200), nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_worker_heartbeat_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_heartbeat")),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeat")
    op.drop_index("ix_job_result_job_id_received_at", table_name="job_result")
    op.drop_index(op.f("ix_job_result_raw_message_id"), table_name="job_result")
    op.drop_index(op.f("ix_job_result_received_at"), table_name="job_result")
    op.drop_table("job_result")
    op.drop_index("ix_raw_message_parse_state_received_at", table_name="raw_message")
    op.drop_index(op.f("ix_raw_message_purge_after"), table_name="raw_message")
    op.drop_index(op.f("ix_raw_message_received_at"), table_name="raw_message")
    op.drop_index(op.f("ix_raw_message_client_id"), table_name="raw_message")
    op.drop_table("raw_message")
    op.drop_table("inbox")
