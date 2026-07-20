"""add agent proposal confirmation loop

Revision ID: 20260720_0012
Revises: 20260715_0011
Create Date: 2026-07-20 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0012"
down_revision: str | None = "20260715_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_action_proposals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("target_object_type", sa.String(length=64), nullable=False),
        sa.Column("target_object_id", sa.String(length=128), nullable=True),
        sa.Column("expected_object_version", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("proposed_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_action_proposals_action_type"), "agent_action_proposals", ["action_type"], unique=False)
    op.create_index(op.f("ix_agent_action_proposals_expires_at"), "agent_action_proposals", ["expires_at"], unique=False)
    op.create_index(op.f("ix_agent_action_proposals_status"), "agent_action_proposals", ["status"], unique=False)
    op.create_index(
        op.f("ix_agent_action_proposals_target_object_id"),
        "agent_action_proposals",
        ["target_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_action_proposals_target_object_type"),
        "agent_action_proposals",
        ["target_object_type"],
        unique=False,
    )

    op.create_table(
        "agent_proposal_confirmations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("expected_object_version", sa.String(length=128), nullable=True),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["agent_action_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_proposal_confirmations_decision"),
        "agent_proposal_confirmations",
        ["decision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_proposal_confirmations_proposal_id"),
        "agent_proposal_confirmations",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_proposal_confirmations_reviewed_at"),
        "agent_proposal_confirmations",
        ["reviewed_at"],
        unique=False,
    )

    op.create_table(
        "controlled_write_commands",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("target_object_type", sa.String(length=64), nullable=False),
        sa.Column("target_object_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("expected_version", sa.String(length=128), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("confirmation_id", sa.String(length=64), nullable=False),
        sa.Column("audit_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rollback_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["confirmation_id"], ["agent_proposal_confirmations.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["agent_action_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_controlled_write_commands_idempotency_key"),
    )
    op.create_index(op.f("ix_controlled_write_commands_confirmation_id"), "controlled_write_commands", ["confirmation_id"], unique=False)
    op.create_index(op.f("ix_controlled_write_commands_operation"), "controlled_write_commands", ["operation"], unique=False)
    op.create_index(op.f("ix_controlled_write_commands_proposal_id"), "controlled_write_commands", ["proposal_id"], unique=False)
    op.create_index(op.f("ix_controlled_write_commands_status"), "controlled_write_commands", ["status"], unique=False)
    op.create_index(
        op.f("ix_controlled_write_commands_target_object_id"),
        "controlled_write_commands",
        ["target_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_controlled_write_commands_target_object_type"),
        "controlled_write_commands",
        ["target_object_type"],
        unique=False,
    )

    op.create_table(
        "agent_audit_records",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("confirmation_id", sa.String(length=64), nullable=True),
        sa.Column("command_id", sa.String(length=64), nullable=True),
        sa.Column("target_object_type", sa.String(length=64), nullable=False),
        sa.Column("target_object_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("authoritative_source", sa.String(length=255), nullable=False),
        sa.Column("authoritative_version", sa.String(length=128), nullable=True),
        sa.Column("audit_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["command_id"], ["controlled_write_commands.id"]),
        sa.ForeignKeyConstraint(["confirmation_id"], ["agent_proposal_confirmations.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["agent_action_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_audit_records_command_id"), "agent_audit_records", ["command_id"], unique=False)
    op.create_index(op.f("ix_agent_audit_records_confirmation_id"), "agent_audit_records", ["confirmation_id"], unique=False)
    op.create_index(op.f("ix_agent_audit_records_operation"), "agent_audit_records", ["operation"], unique=False)
    op.create_index(op.f("ix_agent_audit_records_proposal_id"), "agent_audit_records", ["proposal_id"], unique=False)
    op.create_index(op.f("ix_agent_audit_records_result"), "agent_audit_records", ["result"], unique=False)
    op.create_index(op.f("ix_agent_audit_records_target_object_id"), "agent_audit_records", ["target_object_id"], unique=False)
    op.create_index(
        op.f("ix_agent_audit_records_target_object_type"),
        "agent_audit_records",
        ["target_object_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_audit_records_target_object_type"), table_name="agent_audit_records")
    op.drop_index(op.f("ix_agent_audit_records_target_object_id"), table_name="agent_audit_records")
    op.drop_index(op.f("ix_agent_audit_records_result"), table_name="agent_audit_records")
    op.drop_index(op.f("ix_agent_audit_records_proposal_id"), table_name="agent_audit_records")
    op.drop_index(op.f("ix_agent_audit_records_operation"), table_name="agent_audit_records")
    op.drop_index(op.f("ix_agent_audit_records_confirmation_id"), table_name="agent_audit_records")
    op.drop_index(op.f("ix_agent_audit_records_command_id"), table_name="agent_audit_records")
    op.drop_table("agent_audit_records")

    op.drop_index(op.f("ix_controlled_write_commands_target_object_type"), table_name="controlled_write_commands")
    op.drop_index(op.f("ix_controlled_write_commands_target_object_id"), table_name="controlled_write_commands")
    op.drop_index(op.f("ix_controlled_write_commands_status"), table_name="controlled_write_commands")
    op.drop_index(op.f("ix_controlled_write_commands_proposal_id"), table_name="controlled_write_commands")
    op.drop_index(op.f("ix_controlled_write_commands_operation"), table_name="controlled_write_commands")
    op.drop_index(op.f("ix_controlled_write_commands_confirmation_id"), table_name="controlled_write_commands")
    op.drop_table("controlled_write_commands")

    op.drop_index(op.f("ix_agent_proposal_confirmations_reviewed_at"), table_name="agent_proposal_confirmations")
    op.drop_index(op.f("ix_agent_proposal_confirmations_proposal_id"), table_name="agent_proposal_confirmations")
    op.drop_index(op.f("ix_agent_proposal_confirmations_decision"), table_name="agent_proposal_confirmations")
    op.drop_table("agent_proposal_confirmations")

    op.drop_index(op.f("ix_agent_action_proposals_target_object_type"), table_name="agent_action_proposals")
    op.drop_index(op.f("ix_agent_action_proposals_target_object_id"), table_name="agent_action_proposals")
    op.drop_index(op.f("ix_agent_action_proposals_status"), table_name="agent_action_proposals")
    op.drop_index(op.f("ix_agent_action_proposals_expires_at"), table_name="agent_action_proposals")
    op.drop_index(op.f("ix_agent_action_proposals_action_type"), table_name="agent_action_proposals")
    op.drop_table("agent_action_proposals")
