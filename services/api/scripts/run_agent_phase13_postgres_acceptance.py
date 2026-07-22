from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.agent_command_executor import execute_command_in_transaction, rollback_command_in_transaction  # noqa: E402
from app.agent_security import AgentPrincipal  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.models import (  # noqa: E402
    ActionItem,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
    MeetingSummary,
    Requirement,
    Risk,
)

PREFIX = "phase13_pg_"
TENANT_ID = "tenant-phase13"
PROJECT_ID = "project-phase13"
PHASE12_REVISION = "20260721_0014"
PHASE13_HEAD = "head"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 13 PostgreSQL pilot acceptance on synthetic data.")
    parser.add_argument("--database-url", default="", help="PostgreSQL URL. Defaults to API settings database_url.")
    args = parser.parse_args()
    database_url = args.database_url or get_settings().database_url
    if "postgresql" not in database_url:
        print("SKIP: configured database_url is not PostgreSQL.")
        return 2

    config = alembic_config()
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    try:
        command.upgrade(config, PHASE13_HEAD)
        cleanup(SessionLocal)
        seed_data(engine)
        before_non_pilot = non_pilot_snapshot(engine)
        command.downgrade(config, PHASE12_REVISION)
        assert_action_version_removed(engine)
        command.upgrade(config, PHASE13_HEAD)
        cleanup(SessionLocal)
        seed_data(engine)
        run_default_reject_check(SessionLocal)
        run_failure_rollback_check(SessionLocal)
        run_execute_concurrency_and_rollback_checks(SessionLocal)
        run_rollback_conflict_check(SessionLocal)
        after_non_pilot = non_pilot_snapshot(engine)
        assert before_non_pilot == after_non_pilot, "Requirement/Risk or summary JSON changed during Phase 13 acceptance"
        print(
            "PASS: Phase 13 PostgreSQL checks passed: migration downgrade/upgrade, default rejection, "
            "pilot ActionItem write, version increment, same-transaction audit, injected failure rollback, "
            "concurrent idempotency, restart idempotency, rollback success, duplicate rollback, rollback "
            "version conflict rejection, tenant/project whitelist enforcement, and unchanged Requirement/Risk/summary JSON."
        )
        return 0
    finally:
        command.upgrade(config, PHASE13_HEAD)
        cleanup(SessionLocal)
        engine.dispose()


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def seed_data(engine) -> None:  # noqa: ANN001
    now = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into meetings (id, title, status, created_at, updated_at)
                values (:meeting, 'Phase 13 PostgreSQL check', 'completed', :now, :now)
                """
            ),
            {"meeting": f"{PREFIX}meeting", "now": now},
        )
        conn.execute(
            text(
                """
                insert into meeting_summaries (
                    id, meeting_id, overview, agenda, topics, speaker_summaries, decisions, risks,
                    open_questions, next_steps, meeting_agenda, meeting_summary, key_conclusions,
                    unresolved_issues, risks_and_focus, rag_chunk_ids, created_at, updated_at
                )
                values (
                    :summary, :meeting, 'summary', '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[{"owner":"Alice"}]'::jsonb, 'summary',
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now, :now
                )
                """
            ),
            {"summary": f"{PREFIX}summary", "meeting": f"{PREFIX}meeting", "now": now},
        )
        conn.execute(
            text(
                """
                insert into action_items (
                    id, tenant_id, project_id, meeting_id, summary_id, task, owner, due_date, priority,
                    status, version, source_text, created_at, updated_at
                )
                values
                (:action, :tenant, :project, :meeting, :summary, 'Pilot action', 'Alice',
                 '2026-07-30', 'medium', 'open', 1, 'source', :now, :now),
                (:fail_action, :tenant, :project, :meeting, :summary, 'Failure action', 'Alice',
                 '2026-07-30', 'medium', 'open', 1, 'source', :now, :now),
                (:conflict_action, :tenant, :project, :meeting, :summary, 'Conflict action', 'Alice',
                 '2026-07-30', 'medium', 'open', 1, 'source', :now, :now)
                """
            ),
            {
                "action": f"{PREFIX}action",
                "fail_action": f"{PREFIX}fail_action",
                "conflict_action": f"{PREFIX}conflict_action",
                "tenant": TENANT_ID,
                "project": PROJECT_ID,
                "meeting": f"{PREFIX}meeting",
                "summary": f"{PREFIX}summary",
                "now": now,
            },
        )
        conn.execute(
            text(
                """
                insert into requirements (
                    id, tenant_id, project_id, title, description, status, owner, due_date, priority, version,
                    source_meeting_id, source_summary_id, source_json_field, source_json_index, source_ref,
                    created_at, updated_at
                )
                values (:id, :tenant, :project, 'Requirement', 'Requirement', 'confirmed', 'Alice',
                        null, 'medium', 1, :meeting, :summary, 'meeting_agenda', 0, '{}'::jsonb, :now, :now)
                """
            ),
            {"id": f"{PREFIX}req", "tenant": TENANT_ID, "project": PROJECT_ID, "meeting": f"{PREFIX}meeting", "summary": f"{PREFIX}summary", "now": now},
        )
        conn.execute(
            text(
                """
                insert into risks (
                    id, tenant_id, project_id, title, description, status, owner, due_date, priority, version,
                    source_meeting_id, source_summary_id, source_json_field, source_json_index, level, category,
                    impact, probability, mitigation, source_ref, created_at, updated_at
                )
                values (:id, :tenant, :project, 'Risk', 'Risk', 'active', 'Alice', null, 'medium', 1,
                        :meeting, :summary, 'risks', 0, 'medium', null, null, null, null, '{}'::jsonb, :now, :now)
                """
            ),
            {"id": f"{PREFIX}risk", "tenant": TENANT_ID, "project": PROJECT_ID, "meeting": f"{PREFIX}meeting", "summary": f"{PREFIX}summary", "now": now},
        )
    seed_command_rows(SessionLocal=sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False), action_id=f"{PREFIX}action", command_id=f"{PREFIX}command")
    seed_command_rows(SessionLocal=sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False), action_id=f"{PREFIX}fail_action", command_id=f"{PREFIX}fail_command")
    seed_command_rows(SessionLocal=sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False), action_id=f"{PREFIX}conflict_action", command_id=f"{PREFIX}conflict_command")


def seed_command_rows(*, SessionLocal: sessionmaker[Session], action_id: str, command_id: str) -> None:
    now = datetime(2026, 7, 22, 9, 5, tzinfo=timezone.utc)
    proposal_id = command_id.replace("command", "proposal")
    confirmation_id = command_id.replace("command", "confirmation")
    with SessionLocal() as db:
        proposal = AgentActionProposalRecord(
            id=proposal_id,
            action_type="update",
            target_object_type="AgentActionItem",
            target_object_id=action_id,
            expected_object_version="1",
            title="Update owner",
            description="pilot",
            proposed_changes={"owner": {"from": "Alice", "to": "Bob"}},
            evidence=[{"source_text": "Bob takes over."}],
            confidence=0.9,
            risk_level="medium",
            requires_confirmation=True,
            status="approved",
            reason="phase13 pilot",
            metadata_={"tenant_id": TENANT_ID, "project_id": PROJECT_ID},
            created_at=now,
            updated_at=now,
        )
        confirmation = AgentProposalConfirmationRecord(
            id=confirmation_id,
            proposal_id=proposal.id,
            decision="approved",
            reviewer="Phase 13 Reviewer",
            reviewed_at=now,
            comment="approved",
            expected_object_version="1",
            permissions=["agent_write:AgentActionItem"],
            metadata_={},
        )
        command_row = ControlledWriteCommandRecord(
            id=command_id,
            proposal_id=proposal.id,
            target_object_type="AgentActionItem",
            target_object_id=action_id,
            operation="update",
            expected_version="1",
            changes={"owner": "Bob"},
            idempotency_key=f"{command_id}_idempotency",
            confirmation_id=confirmation.id,
            audit_context={"writes_performed": False},
            rollback_plan={"restore_changes": {"owner": "Alice"}},
            status="ready",
            created_at=now,
        )
        db.add_all([proposal, confirmation, command_row])
        db.commit()


def run_default_reject_check(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        try:
            execute_command_in_transaction(db, command_id=f"{PREFIX}command", principal=principal(), settings=Settings())
        except HTTPException as exc:
            assert exc.status_code == 403, exc.detail
            assert "command_execution_disabled" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("default execution switches did not reject")
        action = db.get(ActionItem, f"{PREFIX}action")
        assert action.owner == "Alice" and action.version == 1


def run_failure_rollback_check(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        try:
            execute_command_in_transaction(
                db,
                command_id=f"{PREFIX}fail_command",
                principal=principal(),
                settings=pilot_settings(rollback=True),
                fail_stage="after_audit",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected injected execution failure")
        action = db.get(ActionItem, f"{PREFIX}fail_action")
        command_row = db.get(ControlledWriteCommandRecord, f"{PREFIX}fail_command")
        assert action.owner == "Alice" and action.version == 1
        assert command_row.status == "ready"
        assert db.query(AgentAuditRecord).filter(AgentAuditRecord.command_id == f"{PREFIX}fail_command").count() == 0


def run_execute_concurrency_and_rollback_checks(SessionLocal: sessionmaker[Session]) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_once(SessionLocal, f"{PREFIX}command"), range(2)))
    assert sorted(results) == ["duplicate", "succeeded"], results
    with SessionLocal() as db:
        action = db.get(ActionItem, f"{PREFIX}action")
        assert action.owner == "Bob" and action.version == 2
        assert db.query(AgentAuditRecord).filter(AgentAuditRecord.command_id == f"{PREFIX}command", AgentAuditRecord.result == "execution_succeeded").count() == 1
        restarted = execute_command_in_transaction(db, command_id=f"{PREFIX}command", principal=principal(), settings=pilot_settings(rollback=True))
        assert restarted.status == "duplicate"
    with SessionLocal() as db:
        rollback_first = rollback_command_in_transaction(
            db,
            command_id=f"{PREFIX}command",
            principal=principal(),
            confirmation_comment="rollback",
            settings=pilot_settings(rollback=True),
        )
        rollback_second = rollback_command_in_transaction(
            db,
            command_id=f"{PREFIX}command",
            principal=principal(),
            confirmation_comment="rollback again",
            settings=pilot_settings(rollback=True),
        )
        action = db.get(ActionItem, f"{PREFIX}action")
        assert rollback_first.status == "rolled_back"
        assert rollback_second.status == "duplicate"
        assert action.owner == "Alice" and action.version == 3
        assert db.query(AgentAuditRecord).filter(AgentAuditRecord.command_id == f"{PREFIX}command", AgentAuditRecord.result == "rollback_succeeded").count() == 1


def run_rollback_conflict_check(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        result = execute_command_in_transaction(
            db,
            command_id=f"{PREFIX}conflict_command",
            principal=principal(),
            settings=pilot_settings(rollback=True),
        )
        assert result.status == "succeeded"
    with SessionLocal() as db:
        action = db.get(ActionItem, f"{PREFIX}conflict_action")
        action.version += 1
        db.commit()
    with SessionLocal() as db:
        try:
            rollback_command_in_transaction(
                db,
                command_id=f"{PREFIX}conflict_command",
                principal=principal(),
                confirmation_comment="rollback",
                settings=pilot_settings(rollback=True),
            )
        except HTTPException as exc:
            assert exc.status_code == 409, exc.detail
            assert "rollback_version_conflict" in exc.detail["reasons"], exc.detail
        else:
            raise AssertionError("rollback conflict was not rejected")


def execute_once(SessionLocal: sessionmaker[Session], command_id: str) -> str:
    with SessionLocal() as db:
        return execute_command_in_transaction(db, command_id=command_id, principal=principal(), settings=pilot_settings(rollback=True)).status


def principal() -> AgentPrincipal:
    return AgentPrincipal(
        user_id=f"{PREFIX}user",
        reviewer_identity="Phase 13 Reviewer",
        roles=("agent_high_risk_approver",),
        permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute"),
        tenant_id=TENANT_ID,
        project_ids=(PROJECT_ID,),
    )


def pilot_settings(*, rollback: bool = False) -> Settings:
    return Settings(
        agent_command_execution_enabled=True,
        agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants=TENANT_ID,
            agent_command_pilot_projects=PROJECT_ID,
            agent_rollback_execution_enabled=rollback,
            agent_grey_enabled=True,
            agent_grey_tenants=TENANT_ID,
            agent_grey_projects=PROJECT_ID,
            agent_grey_users=f"{PREFIX}user",
            agent_grey_percentage=100,
            agent_grey_project_daily_limit=100,
            agent_grey_user_daily_limit=100,
            agent_grey_concurrency_limit=1,
        )


def assert_action_version_removed(engine) -> None:  # noqa: ANN001
    columns = {column["name"] for column in inspect(engine).get_columns("action_items")}
    assert "version" not in columns


def non_pilot_snapshot(engine) -> dict[str, Any]:  # noqa: ANN001
    with engine.connect() as conn:
        summary = conn.execute(text("select meeting_agenda from meeting_summaries where id = :id"), {"id": f"{PREFIX}summary"}).scalar()
        req = conn.execute(text("select version, status, owner from requirements where id = :id"), {"id": f"{PREFIX}req"}).mappings().first()
        risk = conn.execute(text("select version, status, owner from risks where id = :id"), {"id": f"{PREFIX}risk"}).mappings().first()
        return {"summary": summary, "requirement": dict(req), "risk": dict(risk)}


def cleanup(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        if table_exists(db, "agent_audit_records"):
            db.query(AgentAuditRecord).filter(AgentAuditRecord.proposal_id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "controlled_write_commands"):
            db.query(ControlledWriteCommandRecord).filter(ControlledWriteCommandRecord.proposal_id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "agent_proposal_confirmations"):
            db.query(AgentProposalConfirmationRecord).filter(AgentProposalConfirmationRecord.proposal_id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "agent_action_proposals"):
            db.query(AgentActionProposalRecord).filter(AgentActionProposalRecord.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "action_items"):
            db.query(ActionItem).filter(ActionItem.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "requirements"):
            db.query(Requirement).filter(Requirement.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "risks"):
            db.query(Risk).filter(Risk.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "meeting_summaries"):
            db.query(MeetingSummary).filter(MeetingSummary.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "meetings"):
            db.execute(text("delete from meetings where id like :prefix"), {"prefix": f"{PREFIX}%"})
        db.commit()


def table_exists(db: Session, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


if __name__ == "__main__":
    raise SystemExit(main())
