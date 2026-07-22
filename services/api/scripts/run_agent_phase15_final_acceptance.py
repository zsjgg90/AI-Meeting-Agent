from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

PHASE = "phase15_pg"
PREFIX = f"{PHASE}_"
TENANT_ID = "tenant-phase15"
PROJECT_ID = "project-phase15"
USER_ID = f"{PREFIX}user"
TOKEN = f"{PREFIX}token"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 15 final API/DB acceptance on synthetic data.")
    parser.add_argument("--database-url", default="", help="PostgreSQL URL. Defaults to API settings database_url.")
    args = parser.parse_args()

    configure_phase15_env()

    from app.agent_security import hash_agent_token  # noqa: WPS433
    from app.config import get_settings  # noqa: WPS433
    from app.database import get_db  # noqa: WPS433
    from app.main import create_app  # noqa: WPS433

    get_settings.cache_clear()
    database_url = args.database_url or get_settings().database_url
    if "postgresql" not in database_url:
        print("SKIP: configured database_url is not PostgreSQL.")
        return 2

    config = alembic_config()
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    app = create_app()

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    try:
        command.upgrade(config, "head")
        cleanup(SessionLocal)
        seed_data(SessionLocal, hash_agent_token(TOKEN))
        before = business_snapshot(engine)

        client = TestClient(app)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        proposal = create_proposal(client, headers)
        approval = post(client, f"/agent/action-proposals/{proposal['id']}/approve", headers, {"comment": "Phase 15 manual approval"})
        command_id = approval["command"]["id"]

        execution = post(client, f"/agent/commands/{command_id}/execute", headers, {"comment": "Phase 15 controlled execute"})
        duplicate = post(client, f"/agent/commands/{command_id}/execute", headers, {"comment": "Phase 15 duplicate execute"})
        rollback = post(client, f"/agent/commands/{command_id}/rollback/execute", headers, {"comment": "Phase 15 controlled rollback"})
        audits = get(client, f"/agent/ops/audits?command_id={command_id}", headers)
        metrics = get(client, "/agent/ops/metrics", headers)
        preflight = get(client, f"/agent/ops/preflight?tenant_id={TENANT_ID}&project_id={PROJECT_ID}", headers)
        after = business_snapshot(engine)

        assert proposal["status"] == "pending", proposal
        assert approval["status"] == "ready", approval
        assert execution["status"] == "succeeded" and execution["writes_performed"] is True, execution
        assert duplicate["status"] == "duplicate" and duplicate["writes_performed"] is True, duplicate
        assert rollback["status"] == "rolled_back" and rollback["writes_performed"] is True, rollback
        assert preflight["status"] == "passed", preflight
        assert audits["total"] >= 3, audits
        assert after["action_owner"] == before["action_owner"], after
        assert after["action_version"] == before["action_version"] + 2, after
        assert after["requirement"] == before["requirement"], "Requirement changed"
        assert after["risk"] == before["risk"], "Risk changed"
        assert after["summary"] == before["summary"], "Summary JSON changed"

        result = {
            "status": "passed",
            "proposal_id": proposal["id"],
            "command_id": command_id,
            "execute_status": execution["status"],
            "duplicate_execute_status": duplicate["status"],
            "rollback_status": rollback["status"],
            "action_version_before": before["action_version"],
            "action_version_after": after["action_version"],
            "audit_total_for_command": audits["total"],
            "metrics_totals": metrics["totals"],
            "preflight_status": preflight["status"],
            "preflight_hard_failures": preflight["hard_failures"],
            "business_isolation": {
                "requirement_unchanged": after["requirement"] == before["requirement"],
                "risk_unchanged": after["risk"] == before["risk"],
                "summary_unchanged": after["summary"] == before["summary"],
            },
            "scope": {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "user_id": USER_ID,
                "object": "AgentActionItem",
                "operation": "update",
                "fields": ["owner"],
                "risk": "medium",
            },
        }
        print("PASS: Phase 15 final acceptance passed.")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        command.upgrade(config, "head")
        cleanup(SessionLocal)
        app.dependency_overrides.clear()
        engine.dispose()


def configure_phase15_env() -> None:
    values = {
        "AGENT_COMMAND_EXECUTION_ENABLED": "true",
        "AGENT_COMMAND_DRY_RUN_ONLY": "false",
        "AGENT_COMMAND_PILOT_ENABLED": "true",
        "AGENT_COMMAND_PILOT_TENANTS": TENANT_ID,
        "AGENT_COMMAND_PILOT_PROJECTS": PROJECT_ID,
        "AGENT_ROLLBACK_EXECUTION_ENABLED": "true",
        "AGENT_GLOBAL_KILL_SWITCH": "false",
        "AGENT_GREY_ENABLED": "true",
        "AGENT_GREY_TENANTS": TENANT_ID,
        "AGENT_GREY_PROJECTS": PROJECT_ID,
        "AGENT_GREY_USERS": USER_ID,
        "AGENT_GREY_PERCENTAGE": "100",
        "AGENT_GREY_PROJECT_DAILY_LIMIT": "50",
        "AGENT_GREY_USER_DAILY_LIMIT": "50",
        "AGENT_GREY_CONCURRENCY_LIMIT": "5",
        "AGENT_GREY_MANUAL_PAUSED": "false",
        "AGENT_PAUSED_TENANTS": "",
        "AGENT_PAUSED_PROJECTS": "",
        "AGENT_CIRCUIT_CONSECUTIVE_FAILURES": "10",
        "AGENT_CIRCUIT_VERSION_CONFLICT_RATE": "0",
        "AGENT_CIRCUIT_ROLLBACK_FAILURES": "10",
    }
    for key, value in values.items():
        os.environ[key] = value


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def cleanup(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        for statement in (
            "delete from agent_audit_records where id like :prefix or command_id like :prefix or proposal_id like :prefix",
            "delete from controlled_write_commands where id like :prefix or proposal_id like :prefix",
            "delete from agent_proposal_confirmations where id like :prefix or proposal_id like :prefix",
            "delete from agent_action_proposals where id like :prefix or target_object_id like :prefix",
            "delete from agent_auth_sessions where id like :prefix or user_id like :prefix",
            "delete from agent_users where id like :prefix",
            "delete from action_items where id like :prefix",
            "delete from requirements where id like :prefix",
            "delete from risks where id like :prefix",
            "delete from meeting_summaries where id like :prefix",
            "delete from meetings where id like :prefix",
        ):
            db.execute(text(statement), {"prefix": f"{PREFIX}%"})
        db.commit()


def seed_data(SessionLocal: sessionmaker[Session], token_hash: str) -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.execute(
            text(
                """
                insert into meetings (id, title, status, created_at, updated_at)
                values (:meeting, 'Phase 15 final acceptance meeting', 'completed', :now, :now)
                """
            ),
            {"meeting": f"{PREFIX}meeting", "now": now},
        )
        db.execute(
            text(
                """
                insert into meeting_summaries (
                    id, meeting_id, overview, agenda, topics, speaker_summaries, decisions, risks,
                    open_questions, next_steps, meeting_agenda, meeting_summary, key_conclusions,
                    unresolved_issues, risks_and_focus, model_name, prompt_version, rag_chunk_ids,
                    rag_collection_name, created_at, updated_at
                )
                values (
                    :summary, :meeting, 'Phase 15 summary', '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    cast(:agenda as jsonb), 'Qwen3 + RAG accepted summary', '[]'::jsonb,
                    '[]'::jsonb, '[]'::jsonb, 'qwen3:14b', 'meeting-analyst-v1', '[]'::jsonb,
                    'meeting_analyst_rules', :now, :now
                )
                """
            ),
            {
                "summary": f"{PREFIX}summary",
                "meeting": f"{PREFIX}meeting",
                "agenda": json.dumps([{"requirement_id": f"{PREFIX}requirement", "title": "Phase 15 internal scope"}]),
                "now": now,
            },
        )
        db.execute(
            text(
                """
                insert into action_items (
                    id, tenant_id, project_id, meeting_id, summary_id, task, owner, due_date, priority,
                    status, source_text, version, created_at, updated_at
                )
                values (
                    :action, :tenant, :project, :meeting, :summary, 'Phase 15 guarded action',
                    'Alice', '2026-07-30', 'medium', 'open',
                    'Bob will take over the guarded action after review.', 1, :now, :now
                )
                """
            ),
            {"action": f"{PREFIX}action", "tenant": TENANT_ID, "project": PROJECT_ID, "meeting": f"{PREFIX}meeting", "summary": f"{PREFIX}summary", "now": now},
        )
        db.execute(
            text(
                """
                insert into requirements (
                    id, tenant_id, project_id, title, description, status, owner, priority, version,
                    source_meeting_id, source_summary_id, source_json_field, source_json_index, source_ref,
                    created_at, updated_at
                )
                values (
                    :id, :tenant, :project, 'Phase 15 requirement', 'Isolation evidence',
                    'confirmed', 'Alice', 'medium', 1, :meeting, :summary, 'meeting_agenda', 0,
                    cast(:source_ref as jsonb), :now, :now
                )
                """
            ),
            {"id": f"{PREFIX}requirement", "tenant": TENANT_ID, "project": PROJECT_ID, "meeting": f"{PREFIX}meeting", "summary": f"{PREFIX}summary", "source_ref": json.dumps({"source": "phase15"}), "now": now},
        )
        db.execute(
            text(
                """
                insert into risks (
                    id, tenant_id, project_id, title, description, status, owner, priority, version,
                    source_meeting_id, source_summary_id, source_json_field, source_json_index, source_ref,
                    level, created_at, updated_at
                )
                values (
                    :id, :tenant, :project, 'Phase 15 risk', 'Isolation evidence',
                    'active', 'Alice', 'medium', 1, :meeting, :summary, 'risks', 0,
                    cast(:source_ref as jsonb), 'medium', :now, :now
                )
                """
            ),
            {"id": f"{PREFIX}risk", "tenant": TENANT_ID, "project": PROJECT_ID, "meeting": f"{PREFIX}meeting", "summary": f"{PREFIX}summary", "source_ref": json.dumps({"source": "phase15"}), "now": now},
        )
        db.execute(
            text(
                """
                insert into agent_users (
                    id, tenant_id, display_name, roles, permissions, project_scope, object_scope,
                    is_active, created_at, updated_at
                )
                values (
                    :user_id, :tenant, 'Phase 15 Reviewer', cast(:roles as jsonb), cast(:permissions as jsonb),
                    cast(:project_scope as jsonb), '{}'::jsonb, true, :now, :now
                )
                """
            ),
            {
                "user_id": USER_ID,
                "tenant": TENANT_ID,
                "roles": json.dumps(["agent_high_risk_approver"]),
                "permissions": json.dumps(["proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute"]),
                "project_scope": json.dumps([PROJECT_ID]),
                "now": now,
            },
        )
        db.execute(
            text(
                """
                insert into agent_auth_sessions (
                    id, user_id, token_hash, authentication_source, expires_at, created_at
                )
                values (:id, :user_id, :token_hash, 'phase15_bearer_test', :expires_at, :now)
                """
            ),
            {"id": f"{PREFIX}session", "user_id": USER_ID, "token_hash": token_hash, "expires_at": datetime(2026, 7, 30, tzinfo=timezone.utc), "now": now},
        )
        db.commit()


def create_proposal(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    payload = {
        "proposal_id": f"{PREFIX}proposal",
        "action_type": "update",
        "target_object_type": "AgentActionItem",
        "target_object_id": f"{PREFIX}action",
        "title": "Phase 15 guarded owner update",
        "description": "Controlled internal grey acceptance write.",
        "proposed_changes": {"owner": {"from": "Alice", "to": "Bob"}},
        "evidence": [
            {
                "source_type": "transcript",
                "source_meeting_id": f"{PREFIX}meeting",
                "source_text": "Bob will take over the guarded action after review.",
            }
        ],
        "confidence": 0.91,
        "risk_level": "medium",
        "requires_confirmation": True,
        "reason": "Phase 15 final acceptance evidence",
        "metadata": {
            "schema_version": "agent-state-tracker-v1",
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
        },
    }
    response = client.post("/agent/action-proposals", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def post(client: TestClient, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200, f"{url}: {response.status_code} {response.text}"
    return response.json()


def get(client: TestClient, url: str, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get(url, headers=headers)
    assert response.status_code == 200, f"{url}: {response.status_code} {response.text}"
    return response.json()


def business_snapshot(engine) -> dict[str, Any]:  # noqa: ANN001
    with engine.connect() as conn:
        action = conn.execute(
            text("select owner, status, priority, version from action_items where id = :id"),
            {"id": f"{PREFIX}action"},
        ).mappings().first()
        requirement = conn.execute(
            text("select title, status, owner, priority, version from requirements where id = :id"),
            {"id": f"{PREFIX}requirement"},
        ).mappings().first()
        risk = conn.execute(
            text("select title, status, owner, priority, version from risks where id = :id"),
            {"id": f"{PREFIX}risk"},
        ).mappings().first()
        summary = conn.execute(
            text("select meeting_agenda, model_name, prompt_version, rag_collection_name from meeting_summaries where id = :id"),
            {"id": f"{PREFIX}summary"},
        ).mappings().first()
        return {
            "action_owner": action["owner"],
            "action_status": action["status"],
            "action_priority": action["priority"],
            "action_version": action["version"],
            "requirement": dict(requirement),
            "risk": dict(risk),
            "summary": dict(summary),
        }


if __name__ == "__main__":
    raise SystemExit(main())
