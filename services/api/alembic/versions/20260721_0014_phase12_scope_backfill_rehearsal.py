"""phase 12 action item scope backfill audit

Revision ID: 20260721_0014
Revises: 20260721_0013
Create Date: 2026-07-21 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0014"
down_revision: str | None = "20260721_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_item_scope_backfill_audits",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("action_item_id", sa.String(length=36), nullable=False),
        sa.Column("old_tenant_id", sa.String(length=64), nullable=True),
        sa.Column("old_project_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_tenant_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_project_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["action_item_id"], ["action_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "action_item_id", name="uq_action_item_scope_backfill_run_item"),
    )
    op.create_index(op.f("ix_action_item_scope_backfill_audits_action_item_id"), "action_item_scope_backfill_audits", ["action_item_id"], unique=False)
    op.create_index(op.f("ix_action_item_scope_backfill_audits_dry_run"), "action_item_scope_backfill_audits", ["dry_run"], unique=False)
    op.create_index(op.f("ix_action_item_scope_backfill_audits_run_id"), "action_item_scope_backfill_audits", ["run_id"], unique=False)
    op.create_index(op.f("ix_action_item_scope_backfill_audits_status"), "action_item_scope_backfill_audits", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_action_item_scope_backfill_audits_status"), table_name="action_item_scope_backfill_audits")
    op.drop_index(op.f("ix_action_item_scope_backfill_audits_run_id"), table_name="action_item_scope_backfill_audits")
    op.drop_index(op.f("ix_action_item_scope_backfill_audits_dry_run"), table_name="action_item_scope_backfill_audits")
    op.drop_index(op.f("ix_action_item_scope_backfill_audits_action_item_id"), table_name="action_item_scope_backfill_audits")
    op.drop_table("action_item_scope_backfill_audits")
