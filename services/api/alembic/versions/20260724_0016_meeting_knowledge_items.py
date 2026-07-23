"""meeting knowledge items

Revision ID: 20260724_0016
Revises: 20260721_0015
Create Date: 2026-07-24 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0016"
down_revision: str | None = "20260721_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_knowledge_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("source_item_key", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("source_segment_id", sa.String(length=36), nullable=True),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=True),
        sa.Column("end_time", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "content_type", "source_item_key", name="uq_meeting_knowledge_source_item"),
    )
    op.create_index(op.f("ix_meeting_knowledge_items_content_hash"), "meeting_knowledge_items", ["content_hash"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_content_type"), "meeting_knowledge_items", ["content_type"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_deleted_at"), "meeting_knowledge_items", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_meeting_id"), "meeting_knowledge_items", ["meeting_id"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_project_id"), "meeting_knowledge_items", ["project_id"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_source_segment_id"), "meeting_knowledge_items", ["source_segment_id"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_source_version"), "meeting_knowledge_items", ["source_version"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_status"), "meeting_knowledge_items", ["status"], unique=False)
    op.create_index(op.f("ix_meeting_knowledge_items_tenant_id"), "meeting_knowledge_items", ["tenant_id"], unique=False)

    op.create_table(
        "meeting_knowledge_syncs",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("meeting_id"),
    )
    op.create_index(op.f("ix_meeting_knowledge_syncs_status"), "meeting_knowledge_syncs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_knowledge_syncs_status"), table_name="meeting_knowledge_syncs")
    op.drop_table("meeting_knowledge_syncs")

    op.drop_index(op.f("ix_meeting_knowledge_items_tenant_id"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_status"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_source_version"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_source_segment_id"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_project_id"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_meeting_id"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_deleted_at"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_content_type"), table_name="meeting_knowledge_items")
    op.drop_index(op.f("ix_meeting_knowledge_items_content_hash"), table_name="meeting_knowledge_items")
    op.drop_table("meeting_knowledge_items")
