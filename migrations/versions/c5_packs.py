"""Parser packs: parser_pack, and the parse outcome columns of raw_message.

Phase C5-B (dev-work-plan rev 35). One new table and four nullable columns on
raw_message, so the previous release keeps running on this schema (one release
back). parser_pack holds no client data and is not in the client delete map.

Revision ID: c5_packs
Revises: c4_ingest
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5_packs"
down_revision: str | None = "c4_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "parser_pack",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("yaml", sa.Text(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            "status IN ('verified', 'unverified-synthetic')",
            name=op.f("ck_parser_pack_status"),
        ),
        sa.CheckConstraint(
            "source IN ('builtin', 'custom')", name=op.f("ck_parser_pack_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parser_pack")),
    )
    op.add_column("raw_message", sa.Column("parsed_at", TIMESTAMP, nullable=True))
    op.add_column(
        "raw_message", sa.Column("parse_pack_id", sa.String(100), nullable=True)
    )
    op.add_column(
        "raw_message", sa.Column("parse_reason", sa.String(32), nullable=True)
    )
    op.add_column("raw_message", sa.Column("parse_path", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_message", "parse_path")
    op.drop_column("raw_message", "parse_reason")
    op.drop_column("raw_message", "parse_pack_id")
    op.drop_column("raw_message", "parsed_at")
    op.drop_table("parser_pack")
