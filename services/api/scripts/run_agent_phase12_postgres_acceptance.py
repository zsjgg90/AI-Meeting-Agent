from __future__ import annotations

import argparse
import json
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

from app.action_item_scope_backfill import backfill_action_item_scopes, rollback_action_item_scope_backfill  # noqa: E402
from app.agent_command_executor import dry_run_command, rehearse_command_transaction, rollback_dry_run_command  # noqa: E402
from app.agent_security import AgentPrincipal  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.models import (  # noqa: E402
    ActionItem,
    ActionItemScopeBackfillAudit,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
    MeetingSummary,
    Requirement,
    Risk,
)

PREFIX = "phase12_pg_"
TENANT_ID = "tenant-phase12"
PROJECT_ID = "project-phase12"
PHASE11_REVISION = "20260721_0013"
PHASE12_HEAD = "head"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 12 PostgreSQL safety acceptance on synthetic data.")
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
        command.upgrade(config, PHASE12_HEAD)
        cleanup(SessionLocal)
        seed_data(engine)
        before = business_snapshot(engine)
        run_backfill_checks(SessionLocal)
        command.downgrade(config, PHASE11_REVISION)
        assert_phase12_rollback(engine)
        command.upgrade(config, PHASE12_HEAD)
        cleanup(SessionLocal)
        seed_data(engine)
        command_id = seed_ready_command(SessionLocal)
        run_transaction_rehearsal_checks(SessionLocal, command_id)
        run_rollback_conflict_check(SessionLocal, command_id)
        after = business_snapshot(engine)
        assert before == after, "formal business data changed during Phase 12 acceptance"
        print(
            "PASS: Phase 12 PostgreSQL checks passed: action item scope backfill success/review/idempotency/"
            "rollback/existing-preserve, migration rollback, transaction rehearsal rollback, concurrent "
            "idempotency, audit-failure rollback, restart idempotency, rollback conflict rejection, "
            "tenant/project isolation, and unchanged formal business data."
        )
        return 0
    finally:
        command.upgrade(config, PHASE12_HEAD)
        cleanup(SessionLocal)
        engine.dispose()


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def seed_data(engine) -> None:  # noqa: ANN001
    now = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into meetings (id, title, status, created_at, updated_at)
                values
                (:id, 'Phase 12 PostgreSQL check', 'completed', :now, :now),
                (:review_id, 'Phase 12 review check', 'completed', :now, :now)
                """
            ),
            {"id": f"{PREFIX}meeting", "review_id": f"{PREFIX}review_meeting", "now": now},
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
                    :id, :meeting_id, 'summary', '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, cast(:meeting_agenda as jsonb), 'summary',
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now, :now
                )
                """
            ),
            {"id": f"{PREFIX}summary", "meeting_id": f"{PREFIX}meeting", "meeting_agenda": json.dumps([{"owner": "Alice"}]), "now": now},
        )
        conn.execute(
            text(
                """
                insert into action_items (
                    id, tenant_id, project_id, meeting_id, summary_id, task, owner, due_date, priority,
                    status, source_text, created_at, updated_at
                )
                values
                (:a1, 'default-tenant', 'default-project', :meeting, :summary, 'Backfill action', 'Alice',
                 '2026-07-30', 'medium', 'open', 'source', :now, :now),
                (:a2, 'default-tenant', 'default-project', :review_meeting, null, 'Review action', 'Alice',
                 '2026-07-30', 'medium', 'open', 'source', :now, :now),
                (:a3, :tenant, :project, :meeting, :summary, 'Existing scoped action', 'Alice',
                 '2026-07-30', 'medium', 'open', 'source', :now, :now)
                """
            ),
            {
                "a1": f"{PREFIX}action",
                "a2": f"{PREFIX}review_action",
                "a3": f"{PREFIX}existing_action",
                "meeting": f"{PREFIX}meeting",
                "review_meeting": f"{PREFIX}review_meeting",
                "summary": f"{PREFIX}summary",
                "tenant": TENANT_ID,
                "project": PROJECT_ID,
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
                values (:id, :tenant, :project, 'Requirement', 'Requirement', 'confirmed', 'Alice', null,
                        'medium', 1, :meeting, :summary, 'meeting_agenda', 0, '{}'::jsonb, :now, :now)
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


def run_backfill_checks(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        dry = backfill_action_item_scopes(db, run_id=f"{PREFIX}dry", dry_run=True, action_item_id_prefix=PREFIX)
        assert dry.applied == 1 and dry.review == 1 and dry.skipped_existing == 1, dry
        action = db.get(ActionItem, f"{PREFIX}action")
        assert action.tenant_id == "default-tenant"
        stats = backfill_action_item_scopes(db, run_id=f"{PREFIX}apply", dry_run=False, action_item_id_prefix=PREFIX)
        repeat = backfill_action_item_scopes(db, run_id=f"{PREFIX}apply", dry_run=False, action_item_id_prefix=PREFIX)
        assert stats.applied == 1 and stats.review == 1 and stats.skipped_existing == 1, stats
        assert repeat.skipped_idempotent == 3, repeat
        action = db.get(ActionItem, f"{PREFIX}action")
        review = db.get(ActionItem, f"{PREFIX}review_action")
        existing = db.get(ActionItem, f"{PREFIX}existing_action")
        assert (action.tenant_id, action.project_id) == (TENANT_ID, PROJECT_ID)
        assert (review.tenant_id, review.project_id) == ("default-tenant", "default-project")
        assert (existing.tenant_id, existing.project_id) == (TENANT_ID, PROJECT_ID)
        rollback = rollback_action_item_scope_backfill(db, run_id=f"{PREFIX}apply")
        assert rollback.rolled_back == 1, rollback
        action = db.get(ActionItem, f"{PREFIX}action")
        assert (action.tenant_id, action.project_id) == ("default-tenant", "default-project")
        review_audit = db.scalars(
            select(ActionItemScopeBackfillAudit).where(ActionItemScopeBackfillAudit.action_item_id == f"{PREFIX}review_action")
        ).first()
        assert review_audit is not None and review_audit.status == "review"


def seed_ready_command(SessionLocal: sessionmaker[Session]) -> str:
    now = datetime(2026, 7, 21, 16, 5, tzinfo=timezone.utc)
    with SessionLocal() as db:
        action = db.get(ActionItem, f"{PREFIX}existing_action")
        proposal = AgentActionProposalRecord(
            id=f"{PREFIX}proposal",
            action_type="update",
            target_object_type="AgentActionItem",
            target_object_id=action.id,
            expected_object_version=action.updated_at.isoformat(),
            title="Update owner",
            description="rehearsal only",
            proposed_changes={"owner": {"from": "Alice", "to": "Bob"}},
            evidence=[{"source_text": "Bob takes over."}],
            confidence=0.9,
            risk_level="medium",
            requires_confirmation=True,
            status="approved",
            reason="phase12 rehearsal",
            metadata_={"tenant_id": TENANT_ID, "project_id": PROJECT_ID},
            created_at=now,
            updated_at=now,
        )
        confirmation = AgentProposalConfirmationRecord(
            id=f"{PREFIX}confirmation",
            proposal_id=proposal.id,
            decision="approved",
            reviewer="Phase 12 Reviewer",
            reviewed_at=now,
            comment="approved",
            expected_object_version=action.updated_at.isoformat(),
            permissions=["agent_write:AgentActionItem"],
            metadata_={},
        )
        command_row = ControlledWriteCommandRecord(
            id=f"{PREFIX}command",
            proposal_id=proposal.id,
            target_object_type="AgentActionItem",
            target_object_id=action.id,
            operation="update",
            expected_version=action.updated_at.isoformat(),
            changes={"owner": "Bob"},
            idempotency_key=f"{PREFIX}idempotency",
            confirmation_id=confirmation.id,
            audit_context={"writes_performed": False},
            rollback_plan={"restore_changes": {"owner": "Alice"}},
            status="ready",
            created_at=now,
        )
        db.add_all([proposal, confirmation, command_row])
        db.commit()
        return command_row.id


def run_transaction_rehearsal_checks(SessionLocal: sessionmaker[Session], command_id: str) -> None:
    agent_principal = principal()
    with SessionLocal() as db:
        try:
            rehearse_command_transaction(db, command_id=command_id, principal=agent_principal, fail_stage="after_audit")
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected rehearsal failure")
        assert db.query(AgentAuditRecord).filter(AgentAuditRecord.result == "execution_rehearsal").count() == 0

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_rehearsal_once(SessionLocal, command_id, agent_principal), range(2)))
    assert sorted(results) == ["duplicate", "execution_rehearsal"], results
    with SessionLocal() as db:
        assert db.query(AgentAuditRecord).filter(AgentAuditRecord.result == "execution_rehearsal").count() == 1
        action = db.get(ActionItem, f"{PREFIX}existing_action")
        assert action.owner == "Alice" and action.status == "open"
    with SessionLocal() as db:
        restarted = rehearse_command_transaction(db, command_id=command_id, principal=agent_principal)
        assert restarted.status == "duplicate"


def run_rollback_conflict_check(SessionLocal: sessionmaker[Session], command_id: str) -> None:
    with SessionLocal() as db:
        dry_run_command(
            db,
            command_id=command_id,
            principal=principal(),
            settings=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        )
        command_row = db.get(ControlledWriteCommandRecord, command_id)
        command_row.expected_version = "stale-version-for-rollback-conflict"
        db.commit()
    with SessionLocal() as db:
        try:
            rollback_dry_run_command(db, command_id=command_id, principal=principal())
        except HTTPException as exc:
            assert exc.status_code == 409, exc.detail
            assert "rollback_version_conflict" in exc.detail["reasons"], exc.detail
            return
    raise AssertionError("rollback conflict was not rejected")


def run_rehearsal_once(SessionLocal: sessionmaker[Session], command_id: str, agent_principal: AgentPrincipal) -> str:
    with SessionLocal() as db:
        return rehearse_command_transaction(db, command_id=command_id, principal=agent_principal).status


def principal() -> AgentPrincipal:
    return AgentPrincipal(
        user_id=f"{PREFIX}user",
        reviewer_identity="Phase 12 Reviewer",
        roles=("agent_high_risk_approver",),
        permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute"),
        tenant_id=TENANT_ID,
        project_ids=(PROJECT_ID,),
    )


def assert_phase12_rollback(engine) -> None:  # noqa: ANN001
    inspector = inspect(engine)
    assert "action_item_scope_backfill_audits" not in inspector.get_table_names()


def business_snapshot(engine) -> dict[str, Any]:  # noqa: ANN001
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select id, tenant_id, project_id, owner, status, updated_at
                from action_items
                where id like :prefix
                order by id
                """
            ),
            {"prefix": f"{PREFIX}%"},
        ).mappings().all()
        summary = conn.execute(
            text("select meeting_agenda from meeting_summaries where id = :id"),
            {"id": f"{PREFIX}summary"},
        ).scalar()
        req = conn.execute(text("select version, status from requirements where id = :id"), {"id": f"{PREFIX}req"}).mappings().first()
        risk = conn.execute(text("select version, status from risks where id = :id"), {"id": f"{PREFIX}risk"}).mappings().first()
        return {"actions": [dict(row) for row in rows], "summary": summary, "requirement": dict(req), "risk": dict(risk)}


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
        if table_exists(db, "action_item_scope_backfill_audits"):
            db.query(ActionItemScopeBackfillAudit).filter(ActionItemScopeBackfillAudit.run_id.like(f"{PREFIX}%")).delete(synchronize_session=False)
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
