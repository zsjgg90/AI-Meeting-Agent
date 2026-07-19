"""add meeting analyst pipeline fields

Revision ID: 20260702_0009
Revises: 20260702_0008
Create Date: 2026-07-02 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0009"
down_revision: str | None = "20260702_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transcript_segments", sa.Column("speaker_name", sa.String(length=255), nullable=True))
    op.add_column("transcript_segments", sa.Column("semantic_label", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_transcript_segments_semantic_label"), "transcript_segments", ["semantic_label"], unique=False)

    op.add_column(
        "meeting_summaries",
        sa.Column("meeting_agenda", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column("meeting_summaries", sa.Column("meeting_summary", sa.Text(), nullable=True))
    op.add_column(
        "meeting_summaries",
        sa.Column("key_conclusions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_summaries",
        sa.Column("unresolved_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_summaries",
        sa.Column("risks_and_focus", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column("meeting_summaries", sa.Column("model_name", sa.String(length=128), nullable=True))
    op.add_column("meeting_summaries", sa.Column("confidence_score", sa.Float(), nullable=True))

    op.add_column("action_items", sa.Column("owner_name", sa.String(length=255), nullable=True))
    op.add_column("action_items", sa.Column("deadline", sa.String(length=64), nullable=True))
    op.add_column("action_items", sa.Column("priority", sa.String(length=32), nullable=True))
    op.add_column("action_items", sa.Column("source_text", sa.Text(), nullable=True))
    op.add_column("action_items", sa.Column("source_segment_id", sa.String(length=36), nullable=True))
    op.add_column("action_items", sa.Column("confidence", sa.Float(), nullable=True))
    op.create_index(op.f("ix_action_items_source_segment_id"), "action_items", ["source_segment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_action_items_source_segment_id"), table_name="action_items")
    op.drop_column("action_items", "confidence")
    op.drop_column("action_items", "source_segment_id")
    op.drop_column("action_items", "source_text")
    op.drop_column("action_items", "priority")
    op.drop_column("action_items", "deadline")
    op.drop_column("action_items", "owner_name")

    op.drop_column("meeting_summaries", "confidence_score")
    op.drop_column("meeting_summaries", "model_name")
    op.drop_column("meeting_summaries", "risks_and_focus")
    op.drop_column("meeting_summaries", "unresolved_issues")
    op.drop_column("meeting_summaries", "key_conclusions")
    op.drop_column("meeting_summaries", "meeting_summary")
    op.drop_column("meeting_summaries", "meeting_agenda")

    op.drop_index(op.f("ix_transcript_segments_semantic_label"), table_name="transcript_segments")
    op.drop_column("transcript_segments", "semantic_label")
    op.drop_column("transcript_segments", "speaker_name")

