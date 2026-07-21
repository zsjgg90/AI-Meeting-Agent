from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.agent_command_executor import dry_run_command, rollback_dry_run_command  # noqa: E402
from app.agent_confirmation_service import approve_proposal, create_proposal  # noqa: E402
from app.agent_security import (  # noqa: E402
    AgentPrincipal,
    require_agent_permission,
    write_control_permissions_for,
)
from app.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import (  # noqa: E402
    ActionItem,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
    Meeting,
    MeetingSummary,
)


PREFIX = "phase10_pg_"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 10 PostgreSQL safety acceptance checks.")
    parser.add_argument("--database-url", default="", help="PostgreSQL URL. Defaults to API settings database_url.")
    args = parser.parse_args()

    database_url = args.database_url or get_settings().database_url
    if "postgresql" not in database_url:
        print("SKIP: configured database_url is not PostgreSQL.")
        return 2

    run_alembic_upgrade()
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    try:
        cleanup(SessionLocal)
        seed_business_state(SessionLocal)
        run_unauthenticated_and_header_checks()
        run_permission_checks()
        command_id = run_approval_and_idempotency_checks(SessionLocal)
        run_dry_run_and_rollback_checks(SessionLocal, command_id)
        assert_business_state_unchanged(SessionLocal)
        print(
            "PASS: Phase 10 PostgreSQL safety checks passed: auth fail-closed, scope/risk denial, "
            "idempotent dry-run, rollback dry-run, conflict rejection, and business isolation."
        )
        return 0
    finally:
        cleanup(SessionLocal)
        engine.dispose()


def run_alembic_upgrade() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one Alembic head, got {heads}"
    command.upgrade(config, "head")


def run_unauthenticated_and_header_checks() -> None:
    app = create_app()
    client = TestClient(app)
    unauthenticated = client.get("/agent/action-proposals")
    forged_headers = client.get(
        "/agent/action-proposals",
        headers={"X-Agent-Reviewer": "admin", "X-Agent-Permissions": "*"},
    )
    assert unauthenticated.status_code == 401, unauthenticated.text
    assert forged_headers.status_code == 401, forged_headers.text


def run_permission_checks() -> None:
    ordinary_reviewer = AgentPrincipal(
        user_id="phase10-user",
        reviewer_identity="phase10-reviewer",
        roles=("reviewer",),
        permissions=("proposal_view", "proposal_review", "command_dry_run", "audit_view", "rollback_execute"),
        tenant_id="tenant-1",
        project_ids=("project-1",),
    )
    assert_denied(
        ordinary_reviewer,
        "proposal_review",
        tenant_id="tenant-1",
        project_id="project-1",
        object_type="AgentActionItem",
        object_id=f"{PREFIX}action",
        risk_level="high",
        operation="cancel",
    )
    assert_denied(
        ordinary_reviewer,
        "proposal_view",
        tenant_id="tenant-1",
        project_id="other-project",
        object_type="AgentActionItem",
        object_id=f"{PREFIX}action",
        risk_level="medium",
        operation="update",
    )
    assert_denied(
        ordinary_reviewer,
        "proposal_view",
        tenant_id="other-tenant",
        project_id="project-1",
        object_type="AgentActionItem",
        object_id=f"{PREFIX}action",
        risk_level="medium",
        operation="update",
    )
    assert_denied(
        AgentPrincipal(
            user_id="phase10-user",
            reviewer_identity="phase10-reviewer",
            permissions=("proposal_view",),
            tenant_id="tenant-1",
            project_ids=("project-1",),
            object_scopes={"AgentActionItem": ("other-action",)},
        ),
        "proposal_view",
        tenant_id="tenant-1",
        project_id="project-1",
        object_type="AgentActionItem",
        object_id=f"{PREFIX}action",
        risk_level="medium",
        operation="update",
    )


def run_approval_and_idempotency_checks(SessionLocal: sessionmaker[Session]) -> str:
    create_phase10_proposal(SessionLocal)
    principal = elevated_principal()
    with SessionLocal() as db:
        proposal, confirmation, result = approve_proposal(
            db,
            proposal_id=f"{PREFIX}proposal",
            reviewer=principal.reviewer_identity,
            permissions=write_control_permissions_for(principal, "AgentActionItem"),
            comment="approve",
        )
        duplicate_proposal, duplicate_confirmation, duplicate_result = approve_proposal(
            db,
            proposal_id=f"{PREFIX}proposal",
            reviewer=principal.reviewer_identity,
            permissions=write_control_permissions_for(principal, "AgentActionItem"),
            comment="approve again",
        )
        command_row = db.scalars(
            select(ControlledWriteCommandRecord).where(ControlledWriteCommandRecord.proposal_id == f"{PREFIX}proposal")
        ).one()
        confirmations = db.scalars(
            select(AgentProposalConfirmationRecord).where(AgentProposalConfirmationRecord.proposal_id == f"{PREFIX}proposal")
        ).all()
        assert proposal.status == "approved"
        assert confirmation.id == duplicate_confirmation.id
        assert duplicate_proposal.status == "approved"
        assert result.status == "ready"
        assert duplicate_result.status == "duplicate"
        assert len(confirmations) == 1
        return command_row.id


def run_dry_run_and_rollback_checks(SessionLocal: sessionmaker[Session], command_id: str) -> None:
    principal = elevated_principal()
    settings = Settings(
        agent_command_execution_enabled=True,
        agent_command_dry_run_only=True,
        agent_rollback_execution_enabled=False,
    )
    with SessionLocal() as db:
        first = dry_run_command(db, command_id=command_id, principal=principal, settings=settings)
        second = dry_run_command(db, command_id=command_id, principal=principal, settings=settings)
        rollback_first = rollback_dry_run_command(db, command_id=command_id, principal=principal, settings=settings)
        rollback_second = rollback_dry_run_command(db, command_id=command_id, principal=principal, settings=settings)

        assert first.status == "dry_run"
        assert second.status == "duplicate"
        assert rollback_first.status == "rollback_dry_run"
        assert rollback_second.status == "duplicate"
        assert first.writes_performed is False
        assert rollback_first.writes_performed is False
        assert rollback_first.rollback_command["dry_run"] is True

        action = db.get(ActionItem, f"{PREFIX}action")
        assert action is not None
        action.updated_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
        db.commit()

    with SessionLocal() as db:
        try:
            rollback_dry_run_command(db, command_id=command_id, principal=principal, settings=settings)
        except HTTPException as exc:
            assert exc.status_code == 409, exc.detail
            assert "rollback_version_conflict" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("rollback conflict was not rejected")


def create_phase10_proposal(SessionLocal: sessionmaker[Session]) -> AgentActionProposalRecord:
    with SessionLocal() as db:
        return create_proposal(
            db,
            {
                "proposal_id": f"{PREFIX}proposal",
                "action_type": "update",
                "target_object_type": "AgentActionItem",
                "target_object_id": f"{PREFIX}action",
                "title": "Phase 10 controlled write safety check",
                "description": "owner update",
                "proposed_changes": {"owner": {"from": "Alice", "to": "Bob"}},
                "evidence": [
                    {
                        "source_type": "transcript",
                        "source_meeting_id": f"{PREFIX}meeting",
                        "source_text": "Bob takes over this synthetic action.",
                    }
                ],
                "confidence": 0.91,
                "risk_level": "medium",
                "requires_confirmation": True,
                "reason": "synthetic Phase 10 safety check",
                "metadata": {"schema_version": "agent-state-tracker-v1", "project_id": "project-1", "tenant_id": "tenant-1"},
            },
        )


def seed_business_state(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        meeting = Meeting(id=f"{PREFIX}meeting", title="Phase 10 PostgreSQL check", status="completed")
        summary = MeetingSummary(
            id=f"{PREFIX}summary",
            meeting_id=meeting.id,
            overview="summary",
            agenda=[],
            topics=[],
            speaker_summaries=[],
            decisions=[],
            risks=[],
            open_questions=[],
            next_steps=[],
            meeting_agenda=[],
            meeting_summary="summary",
            key_conclusions=[],
            unresolved_issues=[],
            risks_and_focus=[],
            updated_at=now,
        )
        action = ActionItem(
            id=f"{PREFIX}action",
            meeting_id=meeting.id,
            summary_id=summary.id,
            task="Phase 10 controlled write check",
            owner="Alice",
            due_date="2026-07-30",
            priority="medium",
            status="open",
            source_text="Bob takes over this synthetic action.",
            updated_at=now,
        )
        db.add_all([meeting, summary, action])
        db.commit()


def cleanup(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        db.execute(delete(AgentAuditRecord).where(AgentAuditRecord.proposal_id.like(f"{PREFIX}%")))
        db.execute(delete(ControlledWriteCommandRecord).where(ControlledWriteCommandRecord.proposal_id.like(f"{PREFIX}%")))
        db.execute(delete(AgentProposalConfirmationRecord).where(AgentProposalConfirmationRecord.proposal_id.like(f"{PREFIX}%")))
        db.execute(delete(AgentActionProposalRecord).where(AgentActionProposalRecord.id.like(f"{PREFIX}%")))
        db.execute(delete(ActionItem).where(ActionItem.id == f"{PREFIX}action"))
        db.execute(delete(MeetingSummary).where(MeetingSummary.id == f"{PREFIX}summary"))
        db.execute(delete(Meeting).where(Meeting.id == f"{PREFIX}meeting"))
        db.commit()


def assert_business_state_unchanged(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        action = db.get(ActionItem, f"{PREFIX}action")
        assert action is not None
        assert action.owner == "Alice", "formal ActionItem row was modified"


def elevated_principal() -> AgentPrincipal:
    return AgentPrincipal(
        user_id="phase10-admin",
        reviewer_identity="phase10-admin",
        roles=("agent_high_risk_approver",),
        permissions=(
            "proposal_view",
            "proposal_review",
            "command_dry_run",
            "audit_view",
            "rollback_execute",
        ),
        tenant_id="tenant-1",
        project_ids=("project-1",),
    )


def assert_denied(principal: AgentPrincipal, permission: str, **scope: Any) -> None:
    try:
        require_agent_permission(principal, permission, **scope)
    except HTTPException as exc:
        assert exc.status_code in {401, 403}, exc.detail
        return
    raise AssertionError(f"permission {permission} unexpectedly allowed for {scope}")


if __name__ == "__main__":
    raise SystemExit(main())
