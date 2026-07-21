from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
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

from app.agent_security import AgentPrincipal, hash_agent_token, principal_from_bearer_token  # noqa: E402
from app.authoritative_state import DatabaseAuthoritativeStateProvider  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import (  # noqa: E402
    ActionItem,
    AgentAuthSession,
    AgentUser,
    MeetingSummary,
    Requirement,
    Risk,
)

PREFIX = "phase11_pg_"
TENANT_ID = "tenant-phase11"
PROJECT_ID = "project-phase11"
TOKEN = "phase11-postgres-token"
PHASE10_REVISION = "20260720_0012"
PHASE11_HEAD = "head"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 11 PostgreSQL migration and isolation checks.")
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
        command.downgrade(config, PHASE10_REVISION)
        seed_phase10_shape_data(engine)
        before_summary = read_summary_json(engine)
        command.upgrade(config, PHASE11_HEAD)
        first_counts = authoritative_counts(SessionLocal)
        command.upgrade(config, PHASE11_HEAD)
        second_counts = authoritative_counts(SessionLocal)
        assert first_counts == second_counts, f"migration was not idempotent: {first_counts} != {second_counts}"
        run_auth_checks(SessionLocal)
        run_provider_checks(SessionLocal)
        assert_summary_json_unchanged(engine, before_summary)
        assert_business_state_unchanged(SessionLocal)
        command.downgrade(config, PHASE10_REVISION)
        assert_phase11_rollback(engine)
        command.upgrade(config, PHASE11_HEAD)
        print(
            "PASS: Phase 11 PostgreSQL checks passed: production token auth, expired/revoked denial, "
            "Requirement/Risk table migration, review fallback, idempotency, rollback, tenant/project/object "
            "isolation, summary JSON retention, and no Agent business writes."
        )
        return 0
    finally:
        command.upgrade(config, PHASE11_HEAD)
        cleanup(SessionLocal)
        engine.dispose()


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def seed_phase10_shape_data(engine) -> None:  # noqa: ANN001
    now = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("delete from action_items where id = :id"), {"id": f"{PREFIX}action"})
        conn.execute(text("delete from meeting_summaries where id = :id"), {"id": f"{PREFIX}summary"})
        conn.execute(text("delete from meetings where id = :id"), {"id": f"{PREFIX}meeting"})
        conn.execute(
            text(
                """
                insert into meetings (id, title, status, created_at, updated_at)
                values (:id, :title, 'completed', :now, :now)
                """
            ),
            {"id": f"{PREFIX}meeting", "title": "Phase 11 PostgreSQL check", "now": now},
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
                    cast(:risks as jsonb), '[]'::jsonb, '[]'::jsonb, cast(:meeting_agenda as jsonb), 'summary',
                    cast(:key_conclusions as jsonb), '[]'::jsonb, cast(:risks_and_focus as jsonb), '[]'::jsonb, :now, :now
                )
                """
            ),
            {
                "id": f"{PREFIX}summary",
                "meeting_id": f"{PREFIX}meeting",
                "meeting_agenda": json_text(
                    [
                        {
                            "requirement_id": f"{PREFIX}req_confirmed",
                            "tenant_id": TENANT_ID,
                            "project_id": PROJECT_ID,
                            "title": "Phase 11 confirmed requirement",
                            "description": "Complete requirement candidate.",
                            "status": "confirmed",
                            "owner": "Alice",
                        },
                        {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "owner": "Review"},
                    ]
                ),
                "key_conclusions": json_text([]),
                "risks": json_text(
                    [
                        {
                            "risk_id": f"{PREFIX}risk_confirmed",
                            "tenant_id": TENANT_ID,
                            "project_id": PROJECT_ID,
                            "title": "Phase 11 confirmed risk",
                            "description": "Complete risk candidate.",
                            "status": "active",
                            "level": "high",
                        },
                        {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "level": "medium"},
                    ]
                ),
                "risks_and_focus": json_text([]),
                "now": now,
            },
        )
        conn.execute(
            text(
                """
                insert into action_items (
                    id, meeting_id, summary_id, task, owner, due_date, priority, status, source_text, created_at, updated_at
                )
                values (:id, :meeting_id, :summary_id, 'Phase 11 action', 'Alice', '2026-07-30', 'medium', 'open',
                        'Alice owns the Phase 11 action.', :now, :now)
                """
            ),
            {"id": f"{PREFIX}action", "meeting_id": f"{PREFIX}meeting", "summary_id": f"{PREFIX}summary", "now": now},
        )


def run_auth_checks(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        cleanup_auth(db)
        user = AgentUser(
            id=f"{PREFIX}user",
            tenant_id=TENANT_ID,
            display_name="Phase 11 Reviewer",
            roles=["agent_high_risk_approver"],
            permissions=["proposal_view", "proposal_review", "command_dry_run", "audit_view", "rollback_execute"],
            project_scope=[PROJECT_ID],
            object_scope={"Requirement": [f"{PREFIX}req_confirmed"], "Risk": [f"{PREFIX}risk_confirmed"], "AgentActionItem": [f"{PREFIX}action"]},
            is_active=True,
        )
        db.add(user)
        db.commit()
        valid = AgentAuthSession(
            id=f"{PREFIX}session_valid",
            user_id=user.id,
            token_hash=hash_agent_token(TOKEN),
            authentication_source="phase11_postgres_bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        expired = AgentAuthSession(
            id=f"{PREFIX}session_expired",
            user_id=user.id,
            token_hash=hash_agent_token("expired"),
            authentication_source="phase11_postgres_bearer",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        revoked = AgentAuthSession(
            id=f"{PREFIX}session_revoked",
            user_id=user.id,
            token_hash=hash_agent_token("revoked"),
            authentication_source="phase11_postgres_bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            revoked_at=datetime.now(timezone.utc),
        )
        db.add_all([valid, expired, revoked])
        db.commit()

        principal = principal_from_bearer_token(db, TOKEN)
        assert principal.user_id == user.id
        assert principal.tenant_id == TENANT_ID
        assert principal.project_scope == (PROJECT_ID,)
        assert principal.authentication_source == "phase11_postgres_bearer"
        assert_unauthorized(lambda: principal_from_bearer_token(db, "missing"))
        assert_unauthorized(lambda: principal_from_bearer_token(db, "expired"))
        assert_unauthorized(lambda: principal_from_bearer_token(db, "revoked"))


def run_provider_checks(SessionLocal: sessionmaker[Session]) -> None:
    principal = AgentPrincipal(
        user_id=f"{PREFIX}user",
        reviewer_identity="Phase 11 Reviewer",
        roles=("agent_high_risk_approver",),
        permissions=("proposal_view", "proposal_review", "command_dry_run", "audit_view", "rollback_execute"),
        tenant_id=TENANT_ID,
        project_ids=(PROJECT_ID,),
        object_scopes={
            "Requirement": (f"{PREFIX}req_confirmed",),
            "Risk": (f"{PREFIX}risk_confirmed",),
            "AgentActionItem": (f"{PREFIX}action",),
        },
        authentication_source="phase11_postgres_bearer",
    )
    with SessionLocal() as db:
        provider = DatabaseAuthoritativeStateProvider(db, principal=principal)
        requirement = provider.get_state(object_type="Requirement", object_id=f"{PREFIX}req_confirmed")
        risk = provider.get_state(object_type="Risk", object_id=f"{PREFIX}risk_confirmed")
        action = DatabaseAuthoritativeStateProvider(
            db,
            principal=principal_with(
                tenant_id="default-tenant",
                project_ids=("default-project",),
                object_scopes={"AgentActionItem": (f"{PREFIX}action",)},
            ),
        ).get_state(object_type="AgentActionItem", object_id=f"{PREFIX}action")
        assert requirement is not None and requirement.source == "postgresql.requirements"
        assert risk is not None and risk.source == "postgresql.risks"
        assert action is not None and action.source == "postgresql.action_items"

        review_requirement = db.scalars(
            select(Requirement).where(
                Requirement.source_summary_id == f"{PREFIX}summary",
                Requirement.source_json_field == "meeting_agenda",
                Requirement.source_json_index == 1,
            )
        ).one()
        review_risk = db.scalars(
            select(Risk).where(
                Risk.source_summary_id == f"{PREFIX}summary",
                Risk.source_json_field == "risks",
                Risk.source_json_index == 1,
            )
        ).one()
        assert review_requirement.status == "review"
        assert review_risk.status == "review"

        assert_forbidden(
            lambda: DatabaseAuthoritativeStateProvider(
                db,
                principal=principal_with(tenant_id="other-tenant", project_ids=(PROJECT_ID,)),
            ).get_state(object_type="Requirement", object_id=f"{PREFIX}req_confirmed")
        )
        assert_forbidden(
            lambda: DatabaseAuthoritativeStateProvider(
                db,
                principal=principal_with(tenant_id=TENANT_ID, project_ids=("other-project",)),
            ).get_state(object_type="Risk", object_id=f"{PREFIX}risk_confirmed")
        )
        assert_forbidden(
            lambda: DatabaseAuthoritativeStateProvider(
                db,
                principal=principal_with(object_scopes={"AgentActionItem": ("other-action",)}),
            ).get_state(object_type="AgentActionItem", object_id=f"{PREFIX}action")
        )


def principal_with(
    *,
    tenant_id: str = TENANT_ID,
    project_ids: tuple[str, ...] = (PROJECT_ID,),
    object_scopes: dict[str, tuple[str, ...]] | None = None,
) -> AgentPrincipal:
    return AgentPrincipal(
        user_id=f"{PREFIX}user",
        reviewer_identity="Phase 11 Reviewer",
        permissions=("proposal_view",),
        tenant_id=tenant_id,
        project_ids=project_ids,
        object_scopes=object_scopes or {},
    )


def authoritative_counts(SessionLocal: sessionmaker[Session]) -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "requirements": db.query(Requirement).filter(Requirement.source_summary_id == f"{PREFIX}summary").count(),
            "risks": db.query(Risk).filter(Risk.source_summary_id == f"{PREFIX}summary").count(),
        }


def assert_summary_json_unchanged(engine, before: dict[str, Any]) -> None:  # noqa: ANN001
    after = read_summary_json(engine)
    assert after == before, "original meeting_summaries JSON changed during Phase 11 migration/provider checks"


def assert_business_state_unchanged(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        action = db.get(ActionItem, f"{PREFIX}action")
        assert action is not None
        assert action.owner == "Alice"
        assert action.status == "open"
        assert action.tenant_id == "default-tenant"
        assert action.project_id == "default-project"


def assert_phase11_rollback(engine) -> None:  # noqa: ANN001
    inspector = inspect(engine)
    assert "requirements" not in inspector.get_table_names()
    assert "risks" not in inspector.get_table_names()
    action_columns = {column["name"] for column in inspector.get_columns("action_items")}
    assert "tenant_id" not in action_columns
    assert "project_id" not in action_columns


def read_summary_json(engine) -> dict[str, Any]:  # noqa: ANN001
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select meeting_agenda, risks, risks_and_focus
                from meeting_summaries
                where id = :id
                """
            ),
            {"id": f"{PREFIX}summary"},
        ).mappings().one()
        return dict(row)


def cleanup(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        cleanup_auth(db)
        if table_exists(db, "requirements"):
            db.query(Requirement).filter(Requirement.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "risks"):
            db.query(Risk).filter(Risk.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
        if table_exists(db, "action_items"):
            db.execute(text("delete from action_items where id = :id"), {"id": f"{PREFIX}action"})
        if table_exists(db, "meeting_summaries"):
            db.execute(text("delete from meeting_summaries where id = :id"), {"id": f"{PREFIX}summary"})
        if table_exists(db, "meetings"):
            db.execute(text("delete from meetings where id = :id"), {"id": f"{PREFIX}meeting"})
        db.commit()


def cleanup_auth(db: Session) -> None:
    if table_exists(db, "agent_auth_sessions"):
        db.query(AgentAuthSession).filter(AgentAuthSession.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
    if table_exists(db, "agent_users"):
        db.query(AgentUser).filter(AgentUser.id.like(f"{PREFIX}%")).delete(synchronize_session=False)
    db.commit()


def table_exists(db: Session, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def json_text(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def assert_unauthorized(fn) -> None:  # noqa: ANN001
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == 401, exc.detail
        return
    raise AssertionError("expected 401")


def assert_forbidden(fn) -> None:  # noqa: ANN001
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == 403, exc.detail
        return
    raise AssertionError("expected 403")


if __name__ == "__main__":
    raise SystemExit(main())
