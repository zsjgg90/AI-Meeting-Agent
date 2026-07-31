"""task detail editing and attachments

Revision ID: 20260729_0017
Revises: 20260724_0016
Create Date: 2026-07-29 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0017"
down_revision: str | None = "20260724_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("action_items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("action_items", sa.Column("reminder_offset_minutes", sa.Integer(), nullable=True))
    op.add_column("action_items", sa.Column("reminder_channel", sa.String(length=32), nullable=True))

    op.create_table(
        "task_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["action_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_attachments_task_id"), "task_attachments", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_attachments_task_id"), table_name="task_attachments")
    op.drop_table("task_attachments")

    op.drop_column("action_items", "reminder_channel")
    op.drop_column("action_items", "reminder_offset_minutes")
    op.drop_column("action_items", "description")
