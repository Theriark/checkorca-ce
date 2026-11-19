"""Clients and jobs: client, job (rnd-report-2 5.4 plus acknowledged_by and
acknowledged_at).

Phase C3-B (dev-work-plan rev 35). Two new tables and nothing changed in the
C1 tables, so the previous release keeps running on this schema (one release
back). Deleting a client goes through app/repos/client_delete.py; no foreign
key to client cascades.

Revision ID: c3_jobs
Revises: c1_auth
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3_jobs"
down_revision: str | None = "c1_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "client",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_key", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.String(200)),
            server_default=sa.text("'{}'::character varying[]"),
            nullable=False,
        ),
        sa.Column(
            "archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client")),
        sa.UniqueConstraint("name_key", name=op.f("uq_client_name_key")),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("parser_pack_id", sa.String(100), nullable=True),
        sa.Column("match_key", sa.String(200), nullable=True),
        sa.Column("schedule_kind", sa.String(16), nullable=False),
        sa.Column("schedule_expr", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column(
            "max_runtime_minutes",
            sa.Integer(),
            server_default=sa.text("360"),
            nullable=False,
        ),
        sa.Column(
            "grace_minutes", sa.Integer(), server_default=sa.text("120"), nullable=False
        ),
        sa.Column(
            "escalate_minutes",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "attribution_basis",
            sa.String(16),
            server_default=sa.text("'finished'"),
            nullable=False,
        ),
        sa.Column(
            "warning_policy",
            sa.String(32),
            server_default=sa.text("'warning_is_attention'"),
            nullable=False,
        ),
        sa.Column(
            "consecutive_failures_to_alert",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("ping_token", sa.String(24), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("paused_until", TIMESTAMP, nullable=True),
        sa.Column(
            "archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            "kind IN ('backup', 'script', 'other')", name=op.f("ck_job_kind")
        ),
        sa.CheckConstraint(
            "schedule_kind IN ('cron', 'interval', 'daily')",
            name=op.f("ck_job_schedule_kind"),
        ),
        sa.CheckConstraint(
            "attribution_basis IN ('started', 'finished', 'received')",
            name=op.f("ck_job_attribution_basis"),
        ),
        sa.CheckConstraint(
            "warning_policy IN ('warning_is_attention', 'warning_counts_ok')",
            name=op.f("ck_job_warning_policy"),
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["client.id"], name=op.f("fk_job_client_id_client")
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["app_user.id"],
            name=op.f("fk_job_acknowledged_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
        sa.UniqueConstraint(
            "client_id", "name_key", name=op.f("uq_job_client_id_name_key")
        ),
        sa.UniqueConstraint("ping_token", name=op.f("uq_job_ping_token")),
    )


def downgrade() -> None:
    op.drop_table("job")
    op.drop_table("client")
