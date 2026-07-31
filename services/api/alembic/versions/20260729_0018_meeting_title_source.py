"""add meeting title source

Revision ID: 20260729_0018
Revises: 20260729_0017
Create Date: 2026-07-29 15:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0018"
down_revision: str | None = "20260729_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("title_source", sa.String(length=32), nullable=False, server_default="fallback"),
    )
    op.create_index(op.f("ix_meetings_title_source"), "meetings", ["title_source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_meetings_title_source"), table_name="meetings")
    op.drop_column("meetings", "title_source")
