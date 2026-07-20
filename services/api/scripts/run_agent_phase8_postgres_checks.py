from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.agent_confirmation_service import approve_proposal, create_proposal  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import (  # noqa: E402
    ActionItem,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
    Meeting,
    MeetingSummary,
)


PREFIX = "phase8_pg_"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent Phase 8 PostgreSQL migration and concurrency checks.")
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
        proposal = create_phase8_proposal(SessionLocal)
        assert_same_instant(proposal.expected_object_version, "2026-07-20T12:00:00+00:00")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(call_approve, SessionLocal),
                executor.submit(call_approve, SessionLocal),
            ]
            results = [future.result(timeout=30) for future in futures]

        statuses = sorted(item["status"] for item in results)
        assert statuses == ["approved", "approved"], statuses

        with SessionLocal() as db:
            commands = db.scalars(select(ControlledWriteCommandRecord)).all()
            confirmations = db.scalars(select(AgentProposalConfirmationRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()
            item = db.get(ActionItem, f"{PREFIX}action")
            keys = {command.idempotency_key for command in commands}

            assert len(commands) == 1, f"expected one ready command, got {len(commands)}"
            assert len(keys) == 1, f"expected one idempotency key, got {keys}"
            assert len(confirmations) == 1, f"expected one confirmation, got {len(confirmations)}"
            assert len(audits) == 1, f"expected one audit, got {len(audits)}"
            assert item is not None and item.owner == "Alice", "formal ActionItem row was modified"

        print("PASS: PostgreSQL migration head, unique idempotency, concurrent approve, and business isolation checks passed.")
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


def seed_business_state(SessionLocal: sessionmaker[Session]) -> None:
    with SessionLocal() as db:
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        meeting = Meeting(id=f"{PREFIX}meeting", title="Phase 8 PostgreSQL check", status="completed")
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
            task="Phase 8 controlled write check",
            owner="Alice",
            due_date="2026-07-30",
            priority="medium",
            status="open",
            source_text="Bob takes over this synthetic action.",
            updated_at=now,
        )
        db.add_all([meeting, summary, action])
        db.commit()


def create_phase8_proposal(SessionLocal: sessionmaker[Session]) -> AgentActionProposalRecord:
    with SessionLocal() as db:
        row = create_proposal(
            db,
            {
                "proposal_id": f"{PREFIX}proposal",
                "action_type": "update",
                "target_object_type": "AgentActionItem",
                "target_object_id": f"{PREFIX}action",
                "title": "Phase 8 controlled write check",
                "description": "owner update",
                "proposed_changes": {"owner": {"from": "Alice", "to": "Bob"}},
                "evidence": [
                    {
                        "source_type": "transcript",
                        "source_meeting_id": f"{PREFIX}meeting",
                        "source_text": "Bob takes over this synthetic action.",
                    }
                ],
                "confidence": 0.9,
                "risk_level": "medium",
                "requires_confirmation": True,
                "reason": "synthetic PostgreSQL concurrency check",
                "metadata": {"schema_version": "agent-state-tracker-v1"},
            },
        )
        return row


def call_approve(SessionLocal: sessionmaker[Session]) -> dict[str, Any]:
    with SessionLocal() as db:
        proposal, confirmation, result = approve_proposal(
            db,
            proposal_id=f"{PREFIX}proposal",
            reviewer="phase8-postgres-check",
            permissions=["agent_write:AgentActionItem", "agent_review"],
            comment="approve",
        )
        return {
            "proposal_status": proposal.status,
            "confirmation_id": confirmation.id,
            "status": "approved" if result.status in {"ready", "duplicate"} else result.status,
        }


def assert_same_instant(actual: str | None, expected: str) -> None:
    assert actual is not None, "expected object version was not captured"
    actual_dt = parse_iso_datetime(actual)
    expected_dt = parse_iso_datetime(expected)
    assert actual_dt == expected_dt, f"expected version {expected}, got {actual}"


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
