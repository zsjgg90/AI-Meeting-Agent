"""create transcript segments

Revision ID: 20260630_0003
Revises: 20260630_0002
Create Date: 2026-06-30 17:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260630_0003"
down_revision: Union[str, None] = "20260630_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("audio_file_id", sa.String(length=36), nullable=True),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["audio_file_id"], ["audio_files.id"]),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcript_segments_audio_file_id"), "transcript_segments", ["audio_file_id"], unique=False)
    op.create_index(op.f("ix_transcript_segments_meeting_id"), "transcript_segments", ["meeting_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transcript_segments_meeting_id"), table_name="transcript_segments")
    op.drop_index(op.f("ix_transcript_segments_audio_file_id"), table_name="transcript_segments")
    op.drop_table("transcript_segments")
