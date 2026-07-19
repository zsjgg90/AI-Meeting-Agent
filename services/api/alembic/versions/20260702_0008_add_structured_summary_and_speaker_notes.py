"""add structured summary fields and speaker notes

Revision ID: 20260702_0008
Revises: 20260701_0007
Create Date: 2026-07-02 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0008"
down_revision: str | None = "20260701_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meeting_summaries",
        sa.Column("agenda", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_summaries",
        sa.Column("speaker_summaries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_summaries",
        sa.Column("next_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column("speaker_mappings", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("speaker_mappings", "note")
    op.drop_column("meeting_summaries", "next_steps")
    op.drop_column("meeting_summaries", "speaker_summaries")
    op.drop_column("meeting_summaries", "agenda")
