"""Baseline: empty schema; proves the async migration chain on PostgreSQL 16.

Revisions are named by phase (c1_auth, c3_jobs, ...) and stay compatible with
the previous release.

Revision ID: c0_baseline
Revises:
Create Date: 2026-11-18
"""

from collections.abc import Sequence

revision: str = "c0_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
