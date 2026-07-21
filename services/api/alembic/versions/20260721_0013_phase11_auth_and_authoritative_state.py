"""phase 11 production auth and authoritative state

Revision ID: 20260721_0013
Revises: 20260720_0012
Create Date: 2026-07-21 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "20260721_0013"
down_revision: str | None = "20260720_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "default-tenant"
DEFAULT_PROJECT_ID = "default-project"


def upgrade() -> None:
    op.add_column(
        "action_items",
        sa.Column("tenant_id", sa.String(length=64), nullable=False, server_default=DEFAULT_TENANT_ID),
    )
    op.add_column(
        "action_items",
        sa.Column("project_id", sa.String(length=64), nullable=False, server_default=DEFAULT_PROJECT_ID),
    )
    op.create_index(op.f("ix_action_items_tenant_id"), "action_items", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_action_items_project_id"), "action_items", ["project_id"], unique=False)

    op.create_table(
        "requirements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_meeting_id", sa.String(length=36), nullable=True),
        sa.Column("source_summary_id", sa.String(length=36), nullable=True),
        sa.Column("source_json_field", sa.String(length=64), nullable=True),
        sa.Column("source_json_index", sa.Integer(), nullable=True),
        sa.Column("source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "source_summary_id",
            "source_json_field",
            "source_json_index",
            name="uq_requirements_source_json_ref",
        ),
    )
    op.create_index(op.f("ix_requirements_project_id"), "requirements", ["project_id"], unique=False)
    op.create_index(op.f("ix_requirements_source_meeting_id"), "requirements", ["source_meeting_id"], unique=False)
    op.create_index(op.f("ix_requirements_source_summary_id"), "requirements", ["source_summary_id"], unique=False)
    op.create_index(op.f("ix_requirements_status"), "requirements", ["status"], unique=False)
    op.create_index(op.f("ix_requirements_tenant_id"), "requirements", ["tenant_id"], unique=False)

    op.create_table(
        "risks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_meeting_id", sa.String(length=36), nullable=True),
        sa.Column("source_summary_id", sa.String(length=36), nullable=True),
        sa.Column("source_json_field", sa.String(length=64), nullable=True),
        sa.Column("source_json_index", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("probability", sa.String(length=32), nullable=True),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "source_summary_id",
            "source_json_field",
            "source_json_index",
            name="uq_risks_source_json_ref",
        ),
    )
    op.create_index(op.f("ix_risks_project_id"), "risks", ["project_id"], unique=False)
    op.create_index(op.f("ix_risks_source_meeting_id"), "risks", ["source_meeting_id"], unique=False)
    op.create_index(op.f("ix_risks_source_summary_id"), "risks", ["source_summary_id"], unique=False)
    op.create_index(op.f("ix_risks_status"), "risks", ["status"], unique=False)
    op.create_index(op.f("ix_risks_tenant_id"), "risks", ["tenant_id"], unique=False)

    op.create_table(
        "agent_users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("project_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("object_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_users_is_active"), "agent_users", ["is_active"], unique=False)
    op.create_index(op.f("ix_agent_users_tenant_id"), "agent_users", ["tenant_id"], unique=False)

    op.create_table(
        "agent_auth_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("authentication_source", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["agent_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_auth_sessions_expires_at"), "agent_auth_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_agent_auth_sessions_revoked_at"), "agent_auth_sessions", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_agent_auth_sessions_token_hash"), "agent_auth_sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_agent_auth_sessions_user_id"), "agent_auth_sessions", ["user_id"], unique=False)

    migrate_summary_json_candidates()


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_auth_sessions_user_id"), table_name="agent_auth_sessions")
    op.drop_index(op.f("ix_agent_auth_sessions_token_hash"), table_name="agent_auth_sessions")
    op.drop_index(op.f("ix_agent_auth_sessions_revoked_at"), table_name="agent_auth_sessions")
    op.drop_index(op.f("ix_agent_auth_sessions_expires_at"), table_name="agent_auth_sessions")
    op.drop_table("agent_auth_sessions")

    op.drop_index(op.f("ix_agent_users_tenant_id"), table_name="agent_users")
    op.drop_index(op.f("ix_agent_users_is_active"), table_name="agent_users")
    op.drop_table("agent_users")

    op.drop_index(op.f("ix_risks_tenant_id"), table_name="risks")
    op.drop_index(op.f("ix_risks_status"), table_name="risks")
    op.drop_index(op.f("ix_risks_source_summary_id"), table_name="risks")
    op.drop_index(op.f("ix_risks_source_meeting_id"), table_name="risks")
    op.drop_index(op.f("ix_risks_project_id"), table_name="risks")
    op.drop_table("risks")

    op.drop_index(op.f("ix_requirements_tenant_id"), table_name="requirements")
    op.drop_index(op.f("ix_requirements_status"), table_name="requirements")
    op.drop_index(op.f("ix_requirements_source_summary_id"), table_name="requirements")
    op.drop_index(op.f("ix_requirements_source_meeting_id"), table_name="requirements")
    op.drop_index(op.f("ix_requirements_project_id"), table_name="requirements")
    op.drop_table("requirements")

    op.drop_index(op.f("ix_action_items_project_id"), table_name="action_items")
    op.drop_index(op.f("ix_action_items_tenant_id"), table_name="action_items")
    op.drop_column("action_items", "project_id")
    op.drop_column("action_items", "tenant_id")


def migrate_summary_json_candidates() -> None:
    bind = op.get_bind()
    summaries = bind.execute(
        sa.text(
            """
            select id, meeting_id, meeting_agenda, key_conclusions, topics, risks, risks_and_focus, updated_at
            from meeting_summaries
            """
        )
    ).mappings()
    requirements = sa.table(
        "requirements",
        sa.column("id"),
        sa.column("tenant_id"),
        sa.column("project_id"),
        sa.column("title"),
        sa.column("description"),
        sa.column("status"),
        sa.column("owner"),
        sa.column("due_date"),
        sa.column("priority"),
        sa.column("version"),
        sa.column("source_meeting_id"),
        sa.column("source_summary_id"),
        sa.column("source_json_field"),
        sa.column("source_json_index"),
        sa.column("source_ref", postgresql.JSONB),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    risks = sa.table(
        "risks",
        sa.column("id"),
        sa.column("tenant_id"),
        sa.column("project_id"),
        sa.column("title"),
        sa.column("description"),
        sa.column("status"),
        sa.column("owner"),
        sa.column("due_date"),
        sa.column("priority"),
        sa.column("version"),
        sa.column("source_meeting_id"),
        sa.column("source_summary_id"),
        sa.column("source_json_field"),
        sa.column("source_json_index"),
        sa.column("level"),
        sa.column("category"),
        sa.column("impact"),
        sa.column("probability"),
        sa.column("mitigation"),
        sa.column("source_ref", postgresql.JSONB),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    for summary in summaries:
        for field in ("meeting_agenda", "key_conclusions", "topics"):
            for index, value in enumerate(_as_list(summary.get(field))):
                row = build_requirement_row(summary=summary, field=field, index=index, value=value)
                bind.execute(
                    pg_insert(requirements)
                    .values(row)
                    .on_conflict_do_nothing(constraint="uq_requirements_source_json_ref")
                )
        for field in ("risks_and_focus", "risks"):
            for index, value in enumerate(_as_list(summary.get(field))):
                row = build_risk_row(summary=summary, field=field, index=index, value=value)
                bind.execute(
                    pg_insert(risks)
                    .values(row)
                    .on_conflict_do_nothing(constraint="uq_risks_source_json_ref")
                )


def build_requirement_row(*, summary: dict[str, Any], field: str, index: int, value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {"value": value}
    tenant_id = _pick(raw, "tenant_id", "tenant") or DEFAULT_TENANT_ID
    project_id = _pick(raw, "project_id", "project", "scope_project_id") or DEFAULT_PROJECT_ID
    title = _pick(raw, "title", "requirement", "topic", "content", "text", "summary")
    description = _pick(raw, "description", "source_text", "content", "text", "summary") or title
    complete = bool(title and description and summary.get("meeting_id"))
    now = _timestamp(summary.get("updated_at"))
    object_id = _pick(raw, "requirement_id", "id", "target_object_id") or stable_id("req", summary["id"], field, index)
    return {
        "id": _truncate(object_id, 64),
        "tenant_id": _truncate(tenant_id, 64),
        "project_id": _truncate(project_id, 64),
        "title": _truncate(title or f"Review required: {field} #{index + 1}", 255),
        "description": description or "",
        "status": _truncate((_pick(raw, "status") or "open") if complete else "review", 32),
        "owner": _truncate_nullable(_pick(raw, "owner", "owner_name"), 255),
        "due_date": _truncate_nullable(_pick(raw, "due_date", "deadline"), 64),
        "priority": _truncate_nullable(_pick(raw, "priority"), 32),
        "version": 1,
        "source_meeting_id": summary.get("meeting_id"),
        "source_summary_id": summary.get("id"),
        "source_json_field": field,
        "source_json_index": index,
        "source_ref": {"raw": raw, "migration_status": "confirmed" if complete else "review"},
        "created_at": now,
        "updated_at": now,
    }


def build_risk_row(*, summary: dict[str, Any], field: str, index: int, value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {"value": value}
    tenant_id = _pick(raw, "tenant_id", "tenant") or DEFAULT_TENANT_ID
    project_id = _pick(raw, "project_id", "project", "scope_project_id") or DEFAULT_PROJECT_ID
    title = _pick(raw, "title", "risk", "content", "text", "summary")
    description = _pick(raw, "description", "source_text", "content", "text", "summary") or title
    complete = bool(title and description and summary.get("meeting_id"))
    now = _timestamp(summary.get("updated_at"))
    object_id = _pick(raw, "risk_id", "id", "target_object_id") or stable_id("risk", summary["id"], field, index)
    return {
        "id": _truncate(object_id, 64),
        "tenant_id": _truncate(tenant_id, 64),
        "project_id": _truncate(project_id, 64),
        "title": _truncate(title or f"Review required: {field} #{index + 1}", 255),
        "description": description or "",
        "status": _truncate((_pick(raw, "status") or "active") if complete else "review", 32),
        "owner": _truncate_nullable(_pick(raw, "owner", "owner_name"), 255),
        "due_date": _truncate_nullable(_pick(raw, "due_date", "deadline"), 64),
        "priority": _truncate_nullable(_pick(raw, "priority"), 32),
        "version": 1,
        "source_meeting_id": summary.get("meeting_id"),
        "source_summary_id": summary.get("id"),
        "source_json_field": field,
        "source_json_index": index,
        "level": _truncate_nullable(_pick(raw, "level", "risk_level"), 32),
        "category": _truncate_nullable(_pick(raw, "category"), 64),
        "impact": _pick(raw, "impact"),
        "probability": _truncate_nullable(_pick(raw, "probability"), 32),
        "mitigation": _pick(raw, "mitigation", "mitigation_plan"),
        "source_ref": {"raw": raw, "migration_status": "confirmed" if complete else "review"},
        "created_at": now,
        "updated_at": now,
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pick(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        item = value.get(key)
        if item is not None and str(item).strip():
            return str(item).strip()
    return ""


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.now(timezone.utc)


def stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}-{uuid5(NAMESPACE_URL, '|'.join(str(part or '') for part in parts))}"


def _truncate(value: str, length: int) -> str:
    return str(value)[:length]


def _truncate_nullable(value: str, length: int) -> str | None:
    return _truncate(value, length) if value else None
