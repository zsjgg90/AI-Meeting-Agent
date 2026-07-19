"""add prompt and rag metadata to meeting summaries

Revision ID: 20260715_0011
Revises: 20260714_0010
Create Date: 2026-07-15 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0011"
down_revision: str | None = "20260714_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("meeting_summaries", sa.Column("prompt_version", sa.String(length=128), nullable=True))
    op.add_column(
        "meeting_summaries",
        sa.Column("rag_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column("meeting_summaries", sa.Column("rag_dataset_version", sa.String(length=128), nullable=True))
    op.add_column("meeting_summaries", sa.Column("rag_chunk_schema_version", sa.String(length=64), nullable=True))
    op.add_column("meeting_summaries", sa.Column("rag_collection_name", sa.String(length=128), nullable=True))
    op.add_column("meeting_summaries", sa.Column("rag_embedding_model", sa.String(length=255), nullable=True))
    op.alter_column("meeting_summaries", "rag_chunk_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("meeting_summaries", "rag_embedding_model")
    op.drop_column("meeting_summaries", "rag_collection_name")
    op.drop_column("meeting_summaries", "rag_chunk_schema_version")
    op.drop_column("meeting_summaries", "rag_dataset_version")
    op.drop_column("meeting_summaries", "rag_chunk_ids")
    op.drop_column("meeting_summaries", "prompt_version")
