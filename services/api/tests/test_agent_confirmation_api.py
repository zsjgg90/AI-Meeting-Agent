import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.authoritative_state import DatabaseAuthoritativeStateProvider
from app.agent_command_executor import dry_run_command, execute_command_in_transaction
from app.agent_confirmation_service import approve_proposal, recover_duplicate_after_integrity_error
from app.agent_security import AgentPrincipal, get_agent_principal
from app.agent_write_control import AgentActionProposal, AgentProposalConfirmation, build_idempotency_key
from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.models import (
    ActionItem,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
    Meeting,
    MeetingSummary,
)


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


class AgentConfirmationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.app = create_app()

        def override_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_db
        self.set_principal()
        self.client = TestClient(self.app)
        self._seed_business_state()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed_business_state(self) -> None:
        db = self.SessionLocal()
        try:
            now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
            meeting = Meeting(id="meeting-agent-phase8", title="Phase 8", status="completed")
            summary = MeetingSummary(
                id="summary-agent-phase8",
                meeting_id=meeting.id,
                overview="summary",
                agenda=[],
                topics=[],
                speaker_summaries=[],
                decisions=[],
                risks=[
                    {
                        "risk_id": "risk-1",
                        "title": "供应商延期",
                        "status": "active",
                        "level": "high",
                    }
                ],
                open_questions=[],
                next_steps=[],
                meeting_agenda=[
                    {
                        "requirement_id": "req-1",
                        "title": "导出权限配置",
                        "status": "confirmed",
                        "owner": "Alice",
                    }
                ],
                meeting_summary="summary",
                key_conclusions=[],
                unresolved_issues=[],
                risks_and_focus=[],
                updated_at=now,
            )
            item = ActionItem(
                id="action-1",
                meeting_id=meeting.id,
                summary_id=summary.id,
                task="补齐导出权限配置",
                owner="Alice",
                due_date="2026-07-30",
                priority="medium",
                status="open",
                source_text="Alice 负责补齐导出权限配置。",
                updated_at=now,
            )
            db.add_all([meeting, summary, item])
            db.commit()
        finally:
            db.close()

    def set_principal(
        self,
        *,
        permissions: tuple[str, ...] = (
            "proposal_view",
            "proposal_review",
            "command_dry_run",
            "audit_view",
            "rollback_execute",
        ),
        roles: tuple[str, ...] = ("agent_high_risk_approver",),
        tenant_id: str = "tenant-1",
        project_ids: tuple[str, ...] = ("project-1",),
        object_scopes: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        principal = AgentPrincipal(
            user_id="user-1",
            reviewer_identity="reviewer-1",
            roles=roles,
            permissions=permissions,
            tenant_id=tenant_id,
            project_ids=project_ids,
            object_scopes=object_scopes or {},
        )

        async def override_principal():
            return principal

        self.app.dependency_overrides[get_agent_principal] = override_principal

    def auth_headers(self, permissions: str = "") -> dict[str, str]:
        return {}

    def create_action_proposal(self, **overrides) -> dict:
        payload = {
            "proposal_id": "proposal-action-1",
            "action_type": "update",
            "target_object_type": "AgentActionItem",
            "target_object_id": "action-1",
            "title": "补齐导出权限配置",
            "description": "update owner",
            "proposed_changes": {"owner": {"from": "Alice", "to": "Bob"}},
            "evidence": [
                {
                    "source_type": "transcript",
                    "source_meeting_id": "meeting-agent-phase8",
                    "source_text": "Bob 接手导出权限配置。",
                }
            ],
            "confidence": 0.86,
            "risk_level": "medium",
            "requires_confirmation": True,
            "reason": "owner changed in reviewed meeting evidence",
            "metadata": {"schema_version": "agent-state-tracker-v1", "project_id": "project-1", "tenant_id": "tenant-1"},
        }
        metadata_override = overrides.pop("metadata", None)
        payload.update(overrides)
        if metadata_override is not None:
            payload["metadata"] = {**payload["metadata"], **metadata_override}
        response = self.client.post(
            "/agent/action-proposals",
            json=payload,
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_database_authoritative_state_reads_supported_objects(self) -> None:
        db = self.SessionLocal()
        try:
            provider = DatabaseAuthoritativeStateProvider(db)
            action = provider.get_state(object_type="AgentActionItem", object_id="action-1")
            requirement = provider.get_state(object_type="Requirement", object_id="req-1")
            risk = provider.get_state(object_type="Risk", object_id="risk-1")

            self.assertEqual(action.source, "postgresql.action_items")
            self.assertEqual(action.data["owner"], "Alice")
            self.assertEqual(requirement.status, "confirmed")
            self.assertEqual(risk.data["level"], "high")
        finally:
            db.close()

    def test_proposal_save_and_query(self) -> None:
        created = self.create_action_proposal()

        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["expected_object_version"], "2026-07-20T12:00:00")
        listed = self.client.get("/agent/action-proposals", headers=self.auth_headers("agent_review")).json()
        detail = self.client.get(
            "/agent/action-proposals/proposal-action-1",
            headers=self.auth_headers("agent_review"),
        ).json()

        self.assertEqual(len(listed), 1)
        self.assertEqual(detail["id"], "proposal-action-1")

    def test_approve_generates_command_and_audit_without_business_write(self) -> None:
        self.create_action_proposal()
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["proposal"]["status"], "approved")
        self.assertEqual(body["command"]["status"], "ready")
        self.assertEqual(body["command"]["changes"], {"owner": "Bob"})
        self.assertEqual(body["audit"]["result"], "ready")

        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            commands = db.scalars(select(ControlledWriteCommandRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(len(commands), 1)
            self.assertEqual(len(audits), 1)
            self.assertFalse(commands[0].audit_context["writes_performed"])
        finally:
            db.close()

    def test_reject_saves_confirmation_and_audit(self) -> None:
        self.create_action_proposal()
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/reject",
            json={"comment": "not enough evidence"},
            headers=self.auth_headers("agent_review"),
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["proposal"]["status"], "rejected")
        self.assertIsNone(body["command"])
        self.assertEqual(body["audit"]["reasons"], ["human_rejected"])

    def test_unauthorized_confirmation_is_rejected(self) -> None:
        self.create_action_proposal()
        self.app.dependency_overrides.pop(get_agent_principal, None)
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
        )

        self.assertEqual(response.status_code, 401)

    def test_insufficient_permission_is_rejected(self) -> None:
        self.create_action_proposal()
        self.set_principal(permissions=("proposal_view",))
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 403)

    def test_client_supplied_agent_headers_are_ignored(self) -> None:
        self.create_action_proposal()
        self.set_principal(permissions=("proposal_view",))
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "malicious header attempt"},
            headers={
                "X-Agent-Reviewer": "admin",
                "X-Agent-Permissions": "agent_write,agent_write:AgentActionItem",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assert_no_approved_confirmation()

    def test_project_scope_filters_list_and_denies_detail(self) -> None:
        self.create_action_proposal()
        self.set_principal(project_ids=("other-project",))

        listed = self.client.get("/agent/action-proposals").json()
        detail = self.client.get("/agent/action-proposals/proposal-action-1")

        self.assertEqual(listed, [])
        self.assertEqual(detail.status_code, 403)

    def test_tenant_scope_filters_list_and_denies_detail(self) -> None:
        self.create_action_proposal()
        self.set_principal(tenant_id="other-tenant")

        listed = self.client.get("/agent/action-proposals").json()
        detail = self.client.get("/agent/action-proposals/proposal-action-1")

        self.assertEqual(listed, [])
        self.assertEqual(detail.status_code, 403)

    def test_object_scope_denies_review(self) -> None:
        self.create_action_proposal()
        self.set_principal(object_scopes={"AgentActionItem": ("other-action",)})
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "wrong object"},
        )

        self.assertEqual(response.status_code, 403)
        self.assert_no_approved_confirmation()

    def test_high_risk_proposal_requires_elevated_reviewer(self) -> None:
        self.create_action_proposal(risk_level="high", action_type="cancel")
        self.set_principal(roles=())
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "ordinary reviewer"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("High-risk", response.text)
        self.assert_no_approved_confirmation()

    def test_duplicate_approval_is_idempotent(self) -> None:
        self.create_action_proposal()
        first = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved once"},
            headers=self.auth_headers(),
        )
        second = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved twice"},
            headers=self.auth_headers(),
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "duplicate")
        db = self.SessionLocal()
        try:
            commands = db.scalars(select(ControlledWriteCommandRecord)).all()
            confirmations = db.scalars(select(AgentProposalConfirmationRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()
            self.assertEqual(len(commands), 1)
            self.assertEqual(len(confirmations), 1)
            self.assertEqual(len(audits), 1)
        finally:
            db.close()

    def test_stable_idempotency_key_excludes_confirmation_id(self) -> None:
        proposal = AgentActionProposal(
            proposal_id="proposal-stable",
            action_type="update",
            target_object_type="AgentActionItem",
            target_object_id="action-1",
            proposed_changes={"owner": {"from": "Alice", "to": "Bob"}},
            evidence=[{"source_text": "Bob 接手。"}],
            reason="owner changed",
            metadata={"schema_version": "agent-state-tracker-v1"},
        )
        first = AgentProposalConfirmation(
            confirmation_id="confirmation-1",
            proposal_id="proposal-stable",
            decision="approved",
            reviewer="reviewer-1",
            expected_object_version="v1",
            permissions=["agent_write:AgentActionItem"],
        )
        second = first.model_copy(update={"confirmation_id": "confirmation-2"})

        first_key = build_idempotency_key(proposal=proposal, confirmation=first, snapshot=None, operation="update")
        second_key = build_idempotency_key(proposal=proposal, confirmation=second, snapshot=None, operation="update")

        self.assertEqual(first_key, second_key)

    def test_version_conflict_marks_conflict_and_writes_audit(self) -> None:
        self.create_action_proposal()
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.updated_at = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
            db.commit()
        finally:
            db.close()

        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 409)
        db = self.SessionLocal()
        try:
            proposal = db.get(AgentActionProposalRecord, "proposal-action-1")
            commands = db.scalars(select(ControlledWriteCommandRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()
            confirmations = db.scalars(select(AgentProposalConfirmationRecord)).all()
            self.assertEqual(proposal.status, "conflict")
            self.assertEqual(commands, [])
            self.assertEqual(audits[0].reasons, ["version_conflict"])
            self.assertEqual([item.decision for item in confirmations], [])
        finally:
            db.close()

    def test_expired_proposal_is_rejected(self) -> None:
        self.create_action_proposal(
            metadata={
                "schema_version": "agent-state-tracker-v1",
                "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            }
        )
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("confirmation_expired", response.json()["detail"]["reasons"])
        self.assert_no_approved_confirmation()

    def test_missing_target_object_is_rejected(self) -> None:
        self.create_action_proposal(target_object_id="missing-action")
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("target_not_found", response.json()["detail"]["reasons"])
        self.assert_no_approved_confirmation()

    def test_non_whitelisted_field_is_rejected(self) -> None:
        self.create_action_proposal(proposed_changes={"admin": {"from": False, "to": True}})
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("field_not_whitelisted:admin", response.json()["detail"]["reasons"])
        self.assert_no_approved_confirmation()

    def test_terminal_statuses_do_not_transition_again(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        reject_after_approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/reject",
            json={},
            headers=self.auth_headers("agent_review"),
        )

        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(reject_after_approved.status_code, 409)

    def test_repeated_reject_is_idempotent(self) -> None:
        self.create_action_proposal()
        first = self.client.post(
            "/agent/action-proposals/proposal-action-1/reject",
            json={"comment": "reject once"},
            headers=self.auth_headers("agent_review"),
        )
        second = self.client.post(
            "/agent/action-proposals/proposal-action-1/reject",
            json={"comment": "reject twice"},
            headers=self.auth_headers("agent_review"),
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        db = self.SessionLocal()
        try:
            confirmations = db.scalars(select(AgentProposalConfirmationRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()
            self.assertEqual(len(confirmations), 1)
            self.assertEqual(len(audits), 1)
        finally:
            db.close()

    def test_conflict_and_expired_are_terminal(self) -> None:
        self.create_action_proposal()
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.updated_at = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
            db.commit()
        finally:
            db.close()
        first_conflict = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        second_conflict = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )

        self.assertEqual(first_conflict.status_code, 409)
        self.assertEqual(second_conflict.status_code, 409)

    def test_approve_mid_transaction_exception_rolls_back(self) -> None:
        self.create_action_proposal()
        db = self.SessionLocal()
        try:
            with patch("app.agent_confirmation_service.persist_audit", side_effect=RuntimeError("audit failed")):
                with self.assertRaises(RuntimeError):
                    approve_proposal(
                        db,
                        proposal_id="proposal-action-1",
                        reviewer="reviewer-1",
                        permissions=["agent_write:AgentActionItem"],
                    )
            db.rollback()
            proposal = db.get(AgentActionProposalRecord, "proposal-action-1")
            confirmations = db.scalars(select(AgentProposalConfirmationRecord)).all()
            commands = db.scalars(select(ControlledWriteCommandRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()
            self.assertEqual(proposal.status, "pending")
            self.assertEqual(confirmations, [])
            self.assertEqual(commands, [])
            self.assertEqual(audits, [])
        finally:
            db.close()

    def test_integrity_error_recovery_returns_existing_idempotent_result(self) -> None:
        self.create_action_proposal()
        first = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved once"},
            headers=self.auth_headers(),
        )
        self.assertEqual(first.status_code, 200, first.text)

        db = self.SessionLocal()
        try:
            proposal, confirmation, result = recover_duplicate_after_integrity_error(db, "proposal-action-1")
            commands = db.scalars(select(ControlledWriteCommandRecord)).all()
            confirmations = db.scalars(select(AgentProposalConfirmationRecord)).all()
            audits = db.scalars(select(AgentAuditRecord)).all()

            self.assertEqual(proposal.status, "approved")
            self.assertEqual(confirmation.decision, "approved")
            self.assertEqual(result.status, "duplicate")
            self.assertEqual(len(commands), 1)
            self.assertEqual(len(confirmations), 1)
            self.assertEqual(len(audits), 1)
        finally:
            db.close()

    def test_openapi_keeps_existing_routes_and_adds_agent_routes(self) -> None:
        openapi = self.client.get("/openapi.json").json()

        self.assertIn("/meetings/{meeting_id}/summary", openapi["paths"])
        self.assertIn("/agent/action-proposals", openapi["paths"])
        self.assertIn("/agent/action-proposals/{proposal_id}/approve", openapi["paths"])

    def test_no_model_network_or_chroma_dependency_is_used(self) -> None:
        self.create_action_proposal()
        response = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["command"]["audit_context"]["writes_performed"])

    def test_dry_run_command_generates_audit_and_rollback_preview_without_business_write(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={"comment": "approved"},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            response = self.client.post(
                f"/agent/commands/{command_id}/dry-run",
                headers=self.auth_headers(),
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "dry_run")
        self.assertEqual(body["expected_changes"], {"owner": "Bob"})
        self.assertEqual(body["rollback_preview"]["restore_changes"], {"owner": "Alice"})
        self.assertFalse(body["writes_performed"])
        self.assertFalse(body["audit"]["audit_context"]["writes_performed"])

        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            summary = db.get(MeetingSummary, "summary-agent-phase8")
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(summary.meeting_agenda[0]["owner"], "Alice")
        finally:
            db.close()

    def test_dry_run_permission_is_required(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(permissions=("proposal_view", "proposal_review"))

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            response = self.client.post(f"/agent/commands/{command_id}/dry-run")

        self.assertEqual(response.status_code, 403)

    def test_audit_view_permission_is_required(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(permissions=("proposal_view", "proposal_review", "command_dry_run"))

        response = self.client.get(f"/agent/commands/{command_id}/audits")

        self.assertEqual(response.status_code, 403)

    def test_dry_run_is_rejected_when_execution_switch_is_disabled(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        response = self.client.post(
            f"/agent/commands/{command_id}/dry-run",
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("command_execution_disabled", response.json()["detail"]["reasons"])

    def test_non_ready_command_is_rejected_by_dry_run(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        db = self.SessionLocal()
        try:
            command = db.get(ControlledWriteCommandRecord, command_id)
            command.status = "duplicate"
            db.commit()
        finally:
            db.close()

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            response = self.client.post(
                f"/agent/commands/{command_id}/dry-run",
                headers=self.auth_headers(),
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("command_not_ready", response.json()["detail"]["reasons"])

    def test_dry_run_rejects_version_conflict(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.updated_at = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
            db.commit()
        finally:
            db.close()

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            response = self.client.post(
                f"/agent/commands/{command_id}/dry-run",
                headers=self.auth_headers(),
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("version_conflict", response.json()["detail"]["reasons"])

    def test_repeated_dry_run_is_idempotent(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            first = self.client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())
            second = self.client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "duplicate")
        db = self.SessionLocal()
        try:
            dry_run_audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "dry_run")
            ).all()
            self.assertEqual(len(dry_run_audits), 1)
        finally:
            db.close()

    def test_repeated_dry_run_survives_new_client_instance(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            first = self.client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())
            restarted_client = TestClient(self.app)
            second = restarted_client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "duplicate")

    def test_dry_run_audit_failure_rolls_back_audit_insert(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        db = self.SessionLocal()
        try:
            principal = AgentPrincipal(
                user_id="user-1",
                reviewer_identity="reviewer-1",
                permissions=("command_dry_run",),
                project_ids=("project-1",),
            )
            with patch("app.agent_command_executor.persist_dry_run_audit", side_effect=RuntimeError("audit failed")):
                with self.assertRaises(RuntimeError):
                    dry_run_command(
                        db,
                        command_id=command_id,
                        principal=principal,
                        settings=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
                    )
            db.rollback()
            dry_run_audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "dry_run")
            ).all()
            item = db.get(ActionItem, "action-1")
            self.assertEqual(dry_run_audits, [])
            self.assertEqual(item.owner, "Alice")
        finally:
            db.close()

    def test_real_write_contract_stub_rejects_and_preserves_business_data(self) -> None:
        db = self.SessionLocal()
        try:
            with self.assertRaises(Exception) as raised:
                execute_command_in_transaction(db=db, command_id="any")
            item = db.get(ActionItem, "action-1")
            self.assertEqual(getattr(raised.exception, "status_code", None), 403)
            self.assertEqual(item.owner, "Alice")
        finally:
            db.close()

    def test_rollback_dry_run_generates_command_preview_and_audit(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            dry_run = self.client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())
            rollback = self.client.post(f"/agent/commands/{command_id}/rollback/dry-run", headers=self.auth_headers())

        self.assertEqual(dry_run.status_code, 200, dry_run.text)
        self.assertEqual(rollback.status_code, 200, rollback.text)
        body = rollback.json()
        self.assertEqual(body["status"], "rollback_dry_run")
        self.assertTrue(body["rollback_command"]["dry_run"])
        self.assertEqual(body["rollback_command"]["changes"], {"owner": "Alice"})
        self.assertFalse(body["writes_performed"])
        self.assertFalse(body["audit"]["audit_context"]["writes_performed"])

        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            rollback_audits = db.scalars(
                select(AgentAuditRecord).where(
                    AgentAuditRecord.command_id == command_id,
                    AgentAuditRecord.result == "rollback_dry_run",
                )
            ).all()
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(len(rollback_audits), 1)
        finally:
            db.close()

    def test_repeated_rollback_dry_run_is_idempotent(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            self.client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())
            first = self.client.post(f"/agent/commands/{command_id}/rollback/dry-run", headers=self.auth_headers())
            second = self.client.post(f"/agent/commands/{command_id}/rollback/dry-run", headers=self.auth_headers())

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "duplicate")
        db = self.SessionLocal()
        try:
            rollback_audits = db.scalars(
                select(AgentAuditRecord).where(
                    AgentAuditRecord.command_id == command_id,
                    AgentAuditRecord.result == "rollback_dry_run",
                )
            ).all()
            self.assertEqual(len(rollback_audits), 1)
        finally:
            db.close()

    def test_rollback_dry_run_requires_original_dry_run_audit(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        response = self.client.post(f"/agent/commands/{command_id}/rollback/dry-run", headers=self.auth_headers())

        self.assertEqual(response.status_code, 400)
        self.assertIn("missing_original_dry_run_audit", response.json()["detail"]["reasons"])

    def test_rollback_dry_run_rejects_version_conflict(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]

        with patch(
            "app.agent_command_executor.get_settings",
            return_value=Settings(agent_command_execution_enabled=True, agent_command_dry_run_only=True),
        ):
            self.client.post(f"/agent/commands/{command_id}/dry-run", headers=self.auth_headers())

        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.updated_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
            db.commit()
        finally:
            db.close()

        response = self.client.post(f"/agent/commands/{command_id}/rollback/dry-run", headers=self.auth_headers())

        self.assertEqual(response.status_code, 409)
        self.assertIn("rollback_version_conflict", response.json()["detail"]["reasons"])

    def test_agent_command_routes_are_in_openapi(self) -> None:
        openapi = self.client.get("/openapi.json").json()

        self.assertIn("/agent/commands", openapi["paths"])
        self.assertIn("/agent/commands/{command_id}/dry-run", openapi["paths"])
        self.assertIn("/agent/commands/{command_id}/rollback/dry-run", openapi["paths"])

    def assert_no_approved_confirmation(self) -> None:
        db = self.SessionLocal()
        try:
            decisions = db.scalars(select(AgentProposalConfirmationRecord.decision)).all()
            self.assertNotIn("approved", decisions)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
