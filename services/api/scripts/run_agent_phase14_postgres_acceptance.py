from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.agent_command_executor import execute_command_in_transaction, rollback_command_in_transaction  # noqa: E402
from app.agent_phase14_guardrails import circuit_rejection_reasons, evaluate_execution_guardrails  # noqa: E402
from app.agent_security import AgentPrincipal  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.models import ActionItem, AgentAuditRecord, ControlledWriteCommandRecord, MeetingSummary, Requirement, Risk  # noqa: E402
from services.api.scripts import run_agent_phase13_postgres_acceptance as phase13  # noqa: E402

PREFIX = "phase14_pg_"
TENANT_ID = "tenant-phase14"
PROJECT_ID = "project-phase14"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 14 PostgreSQL grey acceptance on synthetic data.")
    parser.add_argument("--database-url", default="", help="PostgreSQL URL. Defaults to API settings database_url.")
    args = parser.parse_args()
    database_url = args.database_url or get_settings().database_url
    if "postgresql" not in database_url:
        print("SKIP: configured database_url is not PostgreSQL.")
        return 2

    phase13.PREFIX = PREFIX
    phase13.TENANT_ID = TENANT_ID
    phase13.PROJECT_ID = PROJECT_ID

    config = phase13.alembic_config()
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    try:
        command.upgrade(config, "head")
        phase13.cleanup(SessionLocal)
        phase13.seed_data(engine)
        before = non_agent_snapshot(engine)

        run_default_grey_reject(SessionLocal)
        run_non_whitelisted_user_reject(SessionLocal)
        run_quota_reject(SessionLocal)
        run_kill_switch_and_pause_reject(SessionLocal)
        run_consecutive_failure_circuit(SessionLocal)
        run_version_conflict_circuit(SessionLocal)
        run_rollback_after_kill_switch(SessionLocal)
        assert_audit_tenant_isolation(SessionLocal)
        assert before == non_agent_snapshot(engine), "Requirement/Risk/summary JSON changed during Phase 14 acceptance"
        print(
            "PASS: Phase 14 PostgreSQL grey checks passed: default reject, non-whitelisted user reject, "
            "daily quota and concurrency guardrails, consecutive-failure circuit, version-conflict circuit, "
            "global kill switch, tenant/project pause, restart-persistent audit-based circuit state, audit "
            "tenant isolation, controlled rollback after emergency close, and unchanged Requirement/Risk/summary JSON."
        )
        return 0
    finally:
        command.upgrade(config, "head")
        phase13.cleanup(SessionLocal)
        engine.dispose()


def run_default_grey_reject(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        try:
            execute_command_in_transaction(db, command_id=f"{PREFIX}command", principal=principal(), settings=phase13_settings_only())
        except HTTPException as exc:
            assert exc.status_code == 403, exc.detail
            assert "grey_disabled" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("Phase 14 grey defaults did not reject real execution")
        assert db.get(ActionItem, f"{PREFIX}action").owner == "Alice"


def run_non_whitelisted_user_reject(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        try:
            execute_command_in_transaction(db, command_id=f"{PREFIX}command", principal=other_user_principal(), settings=grey_settings())
        except HTTPException as exc:
            assert exc.status_code == 403, exc.detail
            assert "grey_user_not_whitelisted" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("non-whitelisted user was not rejected")


def run_quota_reject(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        result = execute_command_in_transaction(db, command_id=f"{PREFIX}command", principal=principal(), settings=grey_settings(project_limit=1, user_limit=1))
        assert result.status == "succeeded"
    with SessionLocal() as db:
        try:
            execute_command_in_transaction(db, command_id=f"{PREFIX}fail_command", principal=principal(), settings=grey_settings(project_limit=1, user_limit=1))
        except HTTPException as exc:
            assert exc.status_code == 429, exc.detail
            assert "project_daily_limit_exceeded" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("daily quota did not reject second execution")
    with SessionLocal() as db:
        running = db.get(ControlledWriteCommandRecord, f"{PREFIX}fail_command")
        running.status = "running"
        db.commit()
        try:
            execute_command_in_transaction(db, command_id=f"{PREFIX}conflict_command", principal=principal(), settings=grey_settings(concurrency=1))
        except HTTPException as exc:
            assert exc.status_code == 429, exc.detail
            assert "concurrency_limit_exceeded" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("concurrency limit did not reject")
        running.status = "ready"
        db.commit()


def run_kill_switch_and_pause_reject(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        item = db.get(ActionItem, f"{PREFIX}fail_action")
        command_row = db.get(ControlledWriteCommandRecord, f"{PREFIX}fail_command")
        decision = evaluate_execution_guardrails(
            db,
            command=command_row,
            item=item,
            principal=principal(),
            settings=grey_settings(kill=True, paused_tenants=TENANT_ID, paused_projects=PROJECT_ID),
        )
        assert not decision.allowed
        assert "global_kill_switch_enabled" in decision.reasons
        assert "tenant_paused" in decision.reasons
        assert "project_paused" in decision.reasons


def run_consecutive_failure_circuit(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        for index in range(2):
            audit = AgentAuditRecord(
                id=f"{PREFIX}failure_audit_{index}",
                proposal_id=f"{PREFIX}fail_proposal",
                confirmation_id=f"{PREFIX}fail_confirmation",
                command_id=f"{PREFIX}fail_command",
                target_object_type="AgentActionItem",
                target_object_id=f"{PREFIX}fail_action",
                operation="update",
                reviewer=principal().reviewer_identity,
                decision="execute",
                result="rejected",
                reasons=["synthetic_failure"],
                authoritative_source="postgresql.action_items",
                authoritative_version="1",
                audit_context={"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "writes_performed": False},
                created_at=datetime.now(timezone.utc),
            )
            db.merge(audit)
        db.commit()
        reasons = circuit_rejection_reasons(db, settings=grey_settings(consecutive_failures=2), tenant_id=TENANT_ID, project_id=PROJECT_ID)
        assert "circuit_consecutive_failures_open" in reasons, reasons


def run_version_conflict_circuit(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        audit = AgentAuditRecord(
            id=f"{PREFIX}version_conflict_audit",
            proposal_id=f"{PREFIX}conflict_proposal",
            confirmation_id=f"{PREFIX}conflict_confirmation",
            command_id=f"{PREFIX}conflict_command",
            target_object_type="AgentActionItem",
            target_object_id=f"{PREFIX}conflict_action",
            operation="update",
            reviewer=principal().reviewer_identity,
            decision="execute",
            result="rejected",
            reasons=["version_conflict"],
            authoritative_source="postgresql.action_items",
            authoritative_version="1",
            audit_context={"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "writes_performed": False},
            created_at=datetime.now(timezone.utc),
        )
        db.merge(audit)
        db.commit()
        reasons = circuit_rejection_reasons(db, settings=grey_settings(version_rate=0.01), tenant_id=TENANT_ID, project_id=PROJECT_ID)
        assert "circuit_version_conflict_rate_open" in reasons, reasons


def run_rollback_after_kill_switch(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        command_row = db.get(ControlledWriteCommandRecord, f"{PREFIX}command")
        if command_row.status != "succeeded":
            return
        result = rollback_command_in_transaction(db, command_id=f"{PREFIX}command", principal=principal(), confirmation_comment="emergency rollback", settings=grey_settings(rollback=True, kill=True))
        assert result.status == "rolled_back", result.status
        assert db.get(ActionItem, f"{PREFIX}action").owner == "Alice"


def assert_audit_tenant_isolation(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        tenant_audits = [
            row for row in db.scalars(select(AgentAuditRecord).where(AgentAuditRecord.id.like(f"{PREFIX}%"))).all()
            if (row.audit_context or {}).get("tenant_id") == TENANT_ID
            or ((row.audit_context or {}).get("after_state") or {}).get("data", {}).get("tenant_id") == TENANT_ID
            or ((row.audit_context or {}).get("before_state") or {}).get("data", {}).get("tenant_id") == TENANT_ID
        ]
        assert tenant_audits, "expected tenant-scoped audit evidence"


def non_agent_snapshot(engine) -> dict[str, Any]:  # noqa: ANN001
    with engine.connect() as conn:
        summary = conn.execute(phase13.text("select meeting_agenda from meeting_summaries where id = :id"), {"id": f"{PREFIX}summary"}).scalar()
        req = conn.execute(phase13.text("select version, status, owner from requirements where id = :id"), {"id": f"{PREFIX}req"}).mappings().first()
        risk = conn.execute(phase13.text("select version, status, owner from risks where id = :id"), {"id": f"{PREFIX}risk"}).mappings().first()
        return {"summary": summary, "requirement": dict(req), "risk": dict(risk)}


def principal() -> AgentPrincipal:
    return AgentPrincipal(
        user_id=f"{PREFIX}user",
        reviewer_identity=f"{PREFIX}user",
        roles=("agent_high_risk_approver",),
        permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute"),
        tenant_id=TENANT_ID,
        project_ids=(PROJECT_ID,),
    )


def other_user_principal() -> AgentPrincipal:
    return AgentPrincipal(
        user_id=f"{PREFIX}other_user",
        reviewer_identity=f"{PREFIX}other_user",
        roles=("agent_high_risk_approver",),
        permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute"),
        tenant_id=TENANT_ID,
        project_ids=(PROJECT_ID,),
    )


def phase13_settings_only() -> Settings:
    return Settings(
        agent_command_execution_enabled=True,
        agent_command_dry_run_only=False,
        agent_command_pilot_enabled=True,
        agent_command_pilot_tenants=TENANT_ID,
        agent_command_pilot_projects=PROJECT_ID,
    )


def grey_settings(
    *,
    project_limit: int = 100,
    user_limit: int = 100,
    concurrency: int = 10,
    consecutive_failures: int = 0,
    version_rate: float = 0.0,
    rollback: bool = False,
    kill: bool = False,
    paused_tenants: str = "",
    paused_projects: str = "",
) -> Settings:
    return Settings(
        agent_command_execution_enabled=True,
        agent_command_dry_run_only=False,
        agent_command_pilot_enabled=True,
        agent_command_pilot_tenants=TENANT_ID,
        agent_command_pilot_projects=PROJECT_ID,
        agent_rollback_execution_enabled=rollback,
        agent_global_kill_switch=kill,
        agent_grey_enabled=True,
        agent_grey_tenants=TENANT_ID,
        agent_grey_projects=PROJECT_ID,
        agent_grey_users=f"{PREFIX}user",
        agent_grey_percentage=100,
        agent_grey_project_daily_limit=project_limit,
        agent_grey_user_daily_limit=user_limit,
        agent_grey_concurrency_limit=concurrency,
        agent_paused_tenants=paused_tenants,
        agent_paused_projects=paused_projects,
        agent_circuit_consecutive_failures=consecutive_failures,
        agent_circuit_version_conflict_rate=version_rate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
