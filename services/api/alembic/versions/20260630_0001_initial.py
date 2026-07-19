"""initial meeting schema

Revision ID: 20260630_0001
Revises:
Create Date: 2026-06-30 16:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260630_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meetings_status"), "meetings", ["status"], unique=False)

    op.create_table(
        "audio_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audio_files_meeting_id"), "audio_files", ["meeting_id"], unique=False)

    op.create_table(
        "meeting_outputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("raw_transcript", sa.Text(), nullable=False),
        sa.Column("speaker_segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("action_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id"),
    )
    op.create_index(op.f("ix_meeting_outputs_meeting_id"), "meeting_outputs", ["meeting_id"], unique=False)

    op.create_table(
        "meeting_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("speaker", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meeting_chunks_meeting_id"), "meeting_chunks", ["meeting_id"], unique=False)

    op.create_table(
        "transcription_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcription_tasks_meeting_id"), "transcription_tasks", ["meeting_id"], unique=False)
    op.create_index(op.f("ix_transcription_tasks_status"), "transcription_tasks", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transcription_tasks_status"), table_name="transcription_tasks")
    op.drop_index(op.f("ix_transcription_tasks_meeting_id"), table_name="transcription_tasks")
    op.drop_table("transcription_tasks")
    op.drop_index(op.f("ix_meeting_chunks_meeting_id"), table_name="meeting_chunks")
    op.drop_table("meeting_chunks")
    op.drop_index(op.f("ix_meeting_outputs_meeting_id"), table_name="meeting_outputs")
    op.drop_table("meeting_outputs")
    op.drop_index(op.f("ix_audio_files_meeting_id"), table_name="audio_files")
    op.drop_table("audio_files")
    op.drop_index(op.f("ix_meetings_status"), table_name="meetings")
    op.drop_table("meetings")
