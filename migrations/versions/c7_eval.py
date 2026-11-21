"""Evaluator: occurrence, job_state and flip (rnd-report-2 5.4 and 5.5).

Phase C7-B (dev-work-plan rev 35). Three new tables and nothing changed in the
earlier ones, so the previous release keeps running on this schema (one
release back). All three hold client data and are in the client delete map
(app/repos/client_delete.py); no foreign key to client or job cascades.
occurrence.result_id is set to NULL when its result is deleted.

Revision ID: c7_eval
Revises: c5_packs
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7_eval"
down_revision: str | None = "c5_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
OCCURRENCE_STATES = (
    "pending",
    "running",
    "verified",
    "warning",
    "failed",
    "overdue",
    "missed",
    "maintenance",
)
JOB_STATES = ("ok", "warning", "failing", "missed", "unknown", "paused", "maintenance")


def one_of(column: str, values: tuple[str, ...]) -> str:
    """The check of app/db/models.py: column IN ('a', 'b')."""
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def upgrade() -> None:
    op.create_table(
        "occurrence",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", TIMESTAMP, nullable=False),
        sa.Column("deadline", TIMESTAMP, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("evaluated_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            one_of("state", OCCURRENCE_STATES), name=op.f("ck_occurrence_state")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_occurrence_job_id_job")
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["job_result.id"],
            name=op.f("fk_occurrence_result_id_job_result"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("job_id", "scheduled_for", name=op.f("pk_occurrence")),
    )
    op.create_index(
        op.f("ix_occurrence_result_id"), "occurrence", ["result_id"], unique=False
    )
    op.create_table(
        "job_state",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("since", TIMESTAMP, nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_success_at", TIMESTAMP, nullable=True),
        sa.Column("eval_from", TIMESTAMP, nullable=True),
        sa.Column(
            "suppressed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("evaluated_at", TIMESTAMP, nullable=False),
        sa.Column("due_at", TIMESTAMP, nullable=True),
        sa.Column("job_updated_at", TIMESTAMP, nullable=False),
        sa.Column(
            "result_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("result_last_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            one_of("state", JOB_STATES), name=op.f("ck_job_state_state")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_job_state_job_id_job")
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_job_state")),
    )
    op.create_table(
        "flip",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(16), nullable=False),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("at", TIMESTAMP, nullable=False),
        sa.Column("scheduled_for", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            one_of("from_state", JOB_STATES), name=op.f("ck_flip_from_state")
        ),
        sa.CheckConstraint(
            one_of("to_state", JOB_STATES), name=op.f("ck_flip_to_state")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_flip_job_id_job")
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["client.id"], name=op.f("fk_flip_client_id_client")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flip")),
    )
    op.create_index(op.f("ix_flip_at"), "flip", ["at"], unique=False)
    op.create_index("ix_flip_job_id_at", "flip", ["job_id", "at"], unique=False)
    op.create_index("ix_flip_client_id_at", "flip", ["client_id", "at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_flip_client_id_at", table_name="flip")
    op.drop_index("ix_flip_job_id_at", table_name="flip")
    op.drop_index(op.f("ix_flip_at"), table_name="flip")
    op.drop_table("flip")
    op.drop_table("job_state")
    op.drop_index(op.f("ix_occurrence_result_id"), table_name="occurrence")
    op.drop_table("occurrence")
