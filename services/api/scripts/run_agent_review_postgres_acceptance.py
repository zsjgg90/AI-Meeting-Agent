from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

PREFIX = "agent_review_pg_"
TENANT_ID = "tenant-agent-review"
OTHER_TENANT_ID = "tenant-agent-review-other"
PROJECT_ID = "project-agent-review"
OTHER_PROJECT_ID = "project-agent-review-other"
TOKEN = f"{PREFIX}token"
USER_ID = f"{PREFIX}user"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent review aggregation PostgreSQL acceptance on synthetic data.")
    parser.add_argument("--database-url", default="", help="PostgreSQL URL. Defaults to API settings database_url.")
    args = parser.parse_args()

    from app.agent_security import hash_agent_token  # noqa: WPS433
    from app.config import get_settings  # noqa: WPS433
    from app.database import get_db  # noqa: WPS433
    from app.main import create_app  # noqa: WPS433

    database_url = args.database_url or get_settings().database_url
    if "postgresql" not in database_url:
        print("SKIP: configured database_url is not PostgreSQL.")
        return 2

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
        command.upgrade(alembic_config(), "head")
        cleanup(SessionLocal)
        seed_data(SessionLocal, hash_agent_token(TOKEN))
        before = business_snapshot(SessionLocal)

        client = TestClient(app)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        overview = get(client, "/agent/review/overview", headers)
        records = get(client, "/agent/review/records?status=all&sort=latest&page=1&page_size=2", headers)
        rejected = get(client, "/agent/review/records?status=rejected&page=1&page_size=10", headers)
        pending_effective = get(client, "/agent/review/records?status=pending_effective&page=1&page_size=10", headers)
        detail = get(client, f"/agent/review/records/{PREFIX}approved", headers)
        hidden = client.get(f"/agent/review/records/{PREFIX}hidden", headers=headers)
        unauthorized = client.get("/agent/review/overview")
        after = business_snapshot(SessionLocal)

        assert overview["pending_count"] == 1, overview
        assert [item["id"] for item in overview["pending_proposals"]] == [f"{PREFIX}pending"], overview
        assert len(records["items"]) == 2 and records["total"] == 2 and records["has_more"] is False, records
        assert [item["id"] for item in rejected["items"]] == [f"{PREFIX}rejected"], rejected
        assert [item["id"] for item in pending_effective["items"]] == [f"{PREFIX}approved"], pending_effective
        assert hidden.status_code == 403, hidden.text
        assert unauthorized.status_code == 401, unauthorized.text
        assert "token" not in str(overview).lower(), "sensitive metadata leaked into overview"
        assert "api_key" not in str(detail).lower(), "sensitive metadata leaked into detail"
        assert detail["proposal"]["changes"][0]["field"] == "owner", detail
        assert detail["command"]["status"] == "ready", detail
        assert detail["writes_performed"] is False, detail
        assert after == before, {"before": before, "after": after}

        print("PASS: Agent review PostgreSQL aggregation, pagination, filters, scope isolation, redaction, and business isolation checks passed.")
        return 0
    finally:
        cleanup(SessionLocal)
        app.dependency_overrides.clear()
        engine.dispose()


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def cleanup(SessionLocal: sessionmaker[Session]) -> None:
    from app.models import (  # noqa: WPS433
        ActionItem,
        AgentActionProposalRecord,
        AgentAuditRecord,
        AgentAuthSession,
        AgentProposalConfirmationRecord,
        AgentUser,
        ControlledWriteCommandRecord,
        Meeting,
    )

    with SessionLocal() as db:
        db.execute(delete(AgentAuditRecord).where(AgentAuditRecord.proposal_id.like(f"{PREFIX}%")))
        db.execute(delete(ControlledWriteCommandRecord).where(ControlledWriteCommandRecord.proposal_id.like(f"{PREFIX}%")))
        db.execute(delete(AgentProposalConfirmationRecord).where(AgentProposalConfirmationRecord.proposal_id.like(f"{PREFIX}%")))
        db.execute(delete(AgentActionProposalRecord).where(AgentActionProposalRecord.id.like(f"{PREFIX}%")))
        db.execute(delete(ActionItem).where(ActionItem.id.like(f"{PREFIX}%")))
        db.execute(delete(AgentAuthSession).where(AgentAuthSession.id.like(f"{PREFIX}%")))
        db.execute(delete(AgentUser).where(AgentUser.id.like(f"{PREFIX}%")))
        db.execute(delete(Meeting).where(Meeting.id.like(f"{PREFIX}%")))
        db.commit()


def seed_data(SessionLocal: sessionmaker[Session], token_hash: str) -> None:
    from app.models import (  # noqa: WPS433
        ActionItem,
        AgentActionProposalRecord,
        AgentAuditRecord,
        AgentAuthSession,
        AgentProposalConfirmationRecord,
        AgentUser,
        ControlledWriteCommandRecord,
        Meeting,
    )

    now = datetime(2026, 7, 23, 9, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add(
            AgentUser(
                id=USER_ID,
                tenant_id=TENANT_ID,
                display_name="Agent Review Tester",
                roles=["agent_reviewer"],
                permissions=["proposal_view", "proposal_review", "audit_view"],
                project_scope=[PROJECT_ID],
                object_scope={},
                is_active=True,
            )
        )
        db.add(Meeting(id=f"{PREFIX}meeting", title="Agent review acceptance meeting", status="completed", created_at=now))
        db.flush()
        db.add(
            AgentAuthSession(
                id=f"{PREFIX}session",
                user_id=USER_ID,
                token_hash=token_hash,
                authentication_source="agent_review_pg_acceptance",
                expires_at=now + timedelta(days=1),
            )
        )
        db.add_all(
            [
                ActionItem(
                    id=f"{PREFIX}action",
                    tenant_id=TENANT_ID,
                    project_id=PROJECT_ID,
                    meeting_id=f"{PREFIX}meeting",
                    task="Review aggregation action item",
                    owner="Alice",
                    due_date="2026-07-25",
                    priority="medium",
                    status="open",
                    version=3,
                    source_text="Bob will take over this action item.",
                    created_at=now,
                    updated_at=now,
                ),
                ActionItem(
                    id=f"{PREFIX}hidden_action",
                    tenant_id=OTHER_TENANT_ID,
                    project_id=OTHER_PROJECT_ID,
                    meeting_id=f"{PREFIX}meeting",
                    task="Hidden action item",
                    owner="Eve",
                    status="open",
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                proposal(f"{PREFIX}pending", "pending", f"{PREFIX}action", now + timedelta(minutes=3), token=True),
                proposal(f"{PREFIX}approved", "approved", f"{PREFIX}action", now + timedelta(minutes=2)),
                proposal(f"{PREFIX}rejected", "rejected", f"{PREFIX}action", now + timedelta(minutes=1)),
                proposal(
                    f"{PREFIX}hidden",
                    "pending",
                    f"{PREFIX}hidden_action",
                    now,
                    tenant_id=OTHER_TENANT_ID,
                    project_id=OTHER_PROJECT_ID,
                ),
            ]
        )
        db.add(
            AgentProposalConfirmationRecord(
                id=f"{PREFIX}confirmation_rejected",
                proposal_id=f"{PREFIX}rejected",
                reviewer="Agent Review Tester",
                decision="rejected",
                comment="Synthetic rejection reason",
                reviewed_at=now + timedelta(minutes=4),
            )
        )
        db.add(
            AgentProposalConfirmationRecord(
                id=f"{PREFIX}confirmation_approved",
                proposal_id=f"{PREFIX}approved",
                reviewer="Agent Review Tester",
                decision="approved",
                comment="Synthetic approval",
                reviewed_at=now + timedelta(minutes=5),
            )
        )
        db.add(
            ControlledWriteCommandRecord(
                id=f"{PREFIX}command",
                proposal_id=f"{PREFIX}approved",
                target_object_type="AgentActionItem",
                target_object_id=f"{PREFIX}action",
                operation="update",
                expected_version="3",
                changes={"owner": {"from": "Alice", "to": "Bob"}},
                status="ready",
                idempotency_key=f"{PREFIX}idempotency",
                confirmation_id=f"{PREFIX}confirmation_approved",
                audit_context={"writes_performed": False, "api_key": "redacted-by-dto"},
                created_at=now + timedelta(minutes=6),
            )
        )
        db.flush()
        db.add(
            AgentAuditRecord(
                id=f"{PREFIX}audit",
                proposal_id=f"{PREFIX}approved",
                confirmation_id=f"{PREFIX}confirmation_approved",
                command_id=f"{PREFIX}command",
                target_object_type="AgentActionItem",
                target_object_id=f"{PREFIX}action",
                reviewer="Agent Review Tester",
                decision="approved",
                operation="update",
                result="ready",
                reasons=[],
                audit_context={"writes_performed": False},
                created_at=now + timedelta(minutes=7),
            )
        )
        db.commit()


def proposal(
    proposal_id: str,
    status: str,
    action_id: str,
    updated_at: datetime,
    *,
    tenant_id: str = TENANT_ID,
    project_id: str = PROJECT_ID,
    token: bool = False,
) -> Any:
    from app.models import AgentActionProposalRecord  # noqa: WPS433

    metadata = {"tenant_id": tenant_id, "project_id": project_id}
    if token:
        metadata["api_key"] = "must-not-leak"
    return AgentActionProposalRecord(
        id=proposal_id,
        action_type="update",
        target_object_type="AgentActionItem",
        target_object_id=action_id,
        title="Update action owner",
        description="Synthetic review proposal",
        proposed_changes={"owner": {"from": "Alice", "to": "Bob"}},
        evidence=[
            {
                "source_type": "transcript",
                "source_meeting_id": f"{PREFIX}meeting",
                "source_text": "Bob will take over this action item.",
                "speaker": "Bob",
            }
        ],
        confidence=0.9,
        risk_level="low",
        status=status,
        expected_object_version="3",
        reason="Synthetic evidence",
        metadata_=metadata,
        created_at=updated_at,
        updated_at=updated_at,
        expires_at=updated_at + timedelta(days=1),
    )


def business_snapshot(SessionLocal: sessionmaker[Session]) -> dict[str, Any]:
    from app.models import ActionItem  # noqa: WPS433

    with SessionLocal() as db:
        rows = db.scalars(select(ActionItem).where(ActionItem.id.in_([f"{PREFIX}action", f"{PREFIX}hidden_action"]))).all()
        return {row.id: {"owner": row.owner, "status": row.status, "version": row.version} for row in rows}


def get(client: TestClient, url: str, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


if __name__ == "__main__":
    raise SystemExit(main())
