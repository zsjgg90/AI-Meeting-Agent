"""create meeting summaries and action items

Revision ID: 20260630_0004
Revises: 20260630_0003
Create Date: 2026-06-30 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260630_0004"
down_revision: Union[str, None] = "20260630_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("overview", sa.Text(), nullable=False),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("open_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id"),
    )
    op.create_index(op.f("ix_meeting_summaries_meeting_id"), "meeting_summaries", ["meeting_id"], unique=False)

    op.create_table(
        "action_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("summary_id", sa.String(length=36), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.ForeignKeyConstraint(["summary_id"], ["meeting_summaries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_action_items_meeting_id"), "action_items", ["meeting_id"], unique=False)
    op.create_index(op.f("ix_action_items_summary_id"), "action_items", ["summary_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_action_items_summary_id"), table_name="action_items")
    op.drop_index(op.f("ix_action_items_meeting_id"), table_name="action_items")
    op.drop_table("action_items")
    op.drop_index(op.f("ix_meeting_summaries_meeting_id"), table_name="meeting_summaries")
    op.drop_table("meeting_summaries")
