import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.authoritative_state import DatabaseAuthoritativeStateProvider
from app.action_item_scope_backfill import backfill_action_item_scopes, rollback_action_item_scope_backfill
from app.agent_command_executor import dry_run_command, execute_command_in_transaction, rehearse_command_transaction, rollback_command_in_transaction
from app.agent_confirmation_service import approve_proposal, recover_duplicate_after_integrity_error
from app.agent_proposal_generation import generate_action_item_proposals_for_meeting
from app.agent_auth_service import create_local_agent_session
from app.agent_security import AgentPrincipal, get_agent_principal, hash_agent_token
from app.agent_write_control import AgentActionProposal, AgentProposalConfirmation, build_idempotency_key
from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.models import (
    ActionItem,
    ActionItemScopeBackfillAudit,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentAuthSession,
    AgentProposalConfirmationRecord,
    AgentUser,
    ControlledWriteCommandRecord,
    Meeting,
    MeetingSummary,
    Requirement,
    Risk,
    TranscriptSegment,
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
                        "title": "Supplier delay",
                        "status": "active",
                        "level": "high",
                    }
                ],
                open_questions=[],
                next_steps=[],
                meeting_agenda=[
                    {
                        "requirement_id": "req-1",
                        "title": "Export permission configuration",
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
                tenant_id="tenant-1",
                project_id="project-1",
                meeting_id=meeting.id,
                summary_id=summary.id,
                task="Update export permission configuration",
                owner="Alice",
                due_date="2026-07-30",
                priority="medium",
                status="open",
                source_text="Alice owns the export permission configuration.",
                updated_at=now,
            )
            requirement = Requirement(
                id="req-1",
                tenant_id="tenant-1",
                project_id="project-1",
                title="Export permission configuration",
                description="Requirement from formal table.",
                status="confirmed",
                owner="Alice",
                priority="medium",
                version=1,
                source_meeting_id=meeting.id,
                source_summary_id=summary.id,
                source_json_field="meeting_agenda",
                source_json_index=0,
                source_ref={"raw": summary.meeting_agenda[0], "migration_status": "confirmed"},
                updated_at=now,
            )
            risk = Risk(
                id="risk-1",
                tenant_id="tenant-1",
                project_id="project-1",
                title="Supplier delay",
                description="Risk from formal table.",
                status="active",
                owner="Alice",
                priority="high",
                version=1,
                source_meeting_id=meeting.id,
                source_summary_id=summary.id,
                source_json_field="risks",
                source_json_index=0,
                level="high",
                source_ref={"raw": summary.risks[0], "migration_status": "confirmed"},
                updated_at=now,
            )
            db.add_all([meeting, summary, item, requirement, risk])
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

    def use_production_token_auth(
        self,
        *,
        token: str = "phase11-token",
        expires_at: datetime | None = None,
        revoked_at: datetime | None = None,
        permissions: list[str] | None = None,
        project_scope: list[str] | None = None,
        tenant_id: str = "tenant-1",
    ) -> dict[str, str]:
        self.app.dependency_overrides.pop(get_agent_principal, None)
        db = self.SessionLocal()
        try:
            user = AgentUser(
                id="agent-user-1",
                tenant_id=tenant_id,
                display_name="Production Reviewer",
                roles=["agent_high_risk_approver"],
                permissions=permissions
                or ["proposal_view", "proposal_review", "command_dry_run", "audit_view", "rollback_execute"],
                project_scope=project_scope or ["project-1"],
                object_scope={},
                is_active=True,
            )
            session = AgentAuthSession(
                id="agent-session-1",
                user_id=user.id,
                token_hash=hash_agent_token(token),
                authentication_source="phase11_test_bearer",
                expires_at=expires_at or datetime.now(timezone.utc) + timedelta(days=1),
                revoked_at=revoked_at,
            )
            db.merge(user)
            db.merge(session)
            db.commit()
        finally:
            db.close()
        return {"Authorization": f"Bearer {token}"}

    def create_action_proposal(self, **overrides) -> dict:
        payload = {
            "proposal_id": "proposal-action-1",
            "action_type": "update",
            "target_object_type": "AgentActionItem",
            "target_object_id": "action-1",
            "title": "Update export permission configuration",
            "description": "update owner",
            "proposed_changes": {"owner": {"from": "Alice", "to": "Bob"}},
            "evidence": [
                {
                    "source_type": "transcript",
                    "source_meeting_id": "meeting-agent-phase8",
                    "source_text": "Bob takes over the export permission configuration.",
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

    def pilot_settings(self, *, rollback: bool = False) -> Settings:
        return Settings(
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants="tenant-1",
            agent_command_pilot_projects="project-1",
            agent_rollback_execution_enabled=rollback,
            agent_grey_enabled=True,
            agent_grey_tenants="tenant-1",
            agent_grey_projects="project-1",
            agent_grey_users="user-1",
            agent_grey_percentage=100,
            agent_grey_project_daily_limit=100,
            agent_grey_user_daily_limit=100,
            agent_grey_concurrency_limit=1,
        )

    def test_database_authoritative_state_reads_supported_objects(self) -> None:
        db = self.SessionLocal()
        try:
            provider = DatabaseAuthoritativeStateProvider(db)
            action = provider.get_state(object_type="AgentActionItem", object_id="action-1")
            requirement = provider.get_state(object_type="Requirement", object_id="req-1")
            risk = provider.get_state(object_type="Risk", object_id="risk-1")

            self.assertEqual(action.source, "postgresql.action_items")
            self.assertEqual(action.data["owner"], "Alice")
            self.assertEqual(requirement.source, "postgresql.requirements")
            self.assertEqual(requirement.status, "confirmed")
            self.assertEqual(risk.source, "postgresql.risks")
            self.assertEqual(risk.data["level"], "high")
        finally:
            db.close()

    def test_provider_does_not_read_requirement_or_risk_from_summary_json(self) -> None:
        db = self.SessionLocal()
        try:
            db.query(Requirement).delete()
            db.query(Risk).delete()
            db.commit()
            provider = DatabaseAuthoritativeStateProvider(db)

            self.assertIsNone(provider.get_state(object_type="Requirement", object_id="req-1"))
            self.assertIsNone(provider.get_state(object_type="Risk", object_id="risk-1"))
            summary = db.get(MeetingSummary, "summary-agent-phase8")
            self.assertEqual(summary.meeting_agenda[0]["requirement_id"], "req-1")
            self.assertEqual(summary.risks[0]["risk_id"], "risk-1")
        finally:
            db.close()

    def test_valid_bearer_token_builds_agent_principal(self) -> None:
        headers = self.use_production_token_auth()
        response = self.client.get("/agent/action-proposals", headers=headers)

        self.assertEqual(response.status_code, 200, response.text)

    def test_expired_bearer_token_is_rejected(self) -> None:
        headers = self.use_production_token_auth(expires_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc))
        response = self.client.get("/agent/action-proposals", headers=headers)

        self.assertEqual(response.status_code, 401)

    def test_revoked_bearer_token_is_rejected(self) -> None:
        headers = self.use_production_token_auth(revoked_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc))
        response = self.client.get("/agent/action-proposals", headers=headers)

        self.assertEqual(response.status_code, 401)

    def test_proposal_save_and_query(self) -> None:
        created = self.create_action_proposal()

        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["expected_object_version"], "1")
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

    def test_review_overview_returns_pending_and_recent_records_without_sensitive_metadata(self) -> None:
        self.create_action_proposal(evidence=[{
            "source_type": "transcript",
            "source_meeting_id": "meeting-agent-phase8",
            "source_text": "Bob takes over the export permission configuration.",
            "speaker": "Bob",
            "token": "secret-token",
        }])
        self.create_action_proposal(proposal_id="proposal-rejected", title="Reject update")
        rejected = self.client.post("/agent/action-proposals/proposal-rejected/reject", json={"comment": "not enough evidence"})

        response = self.client.get("/agent/review/overview")

        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["pending_count"], 1)
        self.assertEqual(len(body["pending_proposals"]), 1)
        self.assertEqual(body["pending_proposals"][0]["risk_label"], "需要注意")
        self.assertEqual(body["pending_proposals"][0]["changes"][0]["label"], "负责人")
        self.assertEqual(body["pending_proposals"][0]["evidence"]["speaker"], "Bob")
        self.assertNotIn("secret-token", response.text)
        self.assertEqual(len(body["recent_records"]), 1)
        self.assertEqual(body["recent_records"][0]["status_label"], "已拒绝")

    def test_review_records_support_pagination_status_filter_and_sort(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={"comment": "approved"})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.create_action_proposal(proposal_id="proposal-rejected", title="Reject update")
        self.client.post("/agent/action-proposals/proposal-rejected/reject", json={"comment": "no"})
        self.create_action_proposal(proposal_id="proposal-expired", title="Expired update")
        db = self.SessionLocal()
        try:
            expired = db.get(AgentActionProposalRecord, "proposal-expired")
            expired.status = "expired"
            db.commit()
        finally:
            db.close()

        first_page = self.client.get("/agent/review/records", params={"status": "all", "sort": "oldest", "page": 1, "page_size": 2})
        rejected = self.client.get("/agent/review/records", params={"status": "rejected", "page": 1, "page_size": 10})
        pending_effective = self.client.get("/agent/review/records", params={"status": "pending_effective"})

        self.assertEqual(first_page.status_code, 200, first_page.text)
        self.assertEqual(first_page.json()["total"], 3)
        self.assertEqual(len(first_page.json()["items"]), 2)
        self.assertTrue(first_page.json()["has_more"])
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["total"], 1)
        self.assertEqual(rejected.json()["items"][0]["status_label"], "已拒绝")
        self.assertEqual(pending_effective.status_code, 200, pending_effective.text)
        self.assertEqual(pending_effective.json()["items"][0]["status_label"], "待生效")

    def test_review_record_detail_returns_confirmation_command_audit_and_write_scope(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={"comment": "approved"})
        self.assertEqual(approved.status_code, 200, approved.text)

        response = self.client.get("/agent/review/records/proposal-action-1")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["proposal"]["id"], "proposal-action-1")
        self.assertEqual(body["confirmation"]["decision"], "approved")
        self.assertEqual(body["command"]["status"], "ready")
        self.assertNotIn("idempotency_key", body["command"])
        self.assertNotIn("audit_context", body["command"])
        self.assertEqual(body["before_after"][0]["before"], "Alice")
        self.assertEqual(body["before_after"][0]["after"], "Bob")
        self.assertFalse(body["writes_performed"])
        self.assertEqual(body["object_version_before"], "1")

    def test_review_records_apply_tenant_project_scope_and_auth_fail_closed(self) -> None:
        self.create_action_proposal()
        headers = self.use_production_token_auth()
        authorized = self.client.get("/agent/review/overview", headers=headers)
        self.set_principal(project_ids=("other-project",))
        forbidden_detail = self.client.get("/agent/review/records/proposal-action-1")
        filtered = self.client.get("/agent/review/overview")
        self.app.dependency_overrides.pop(get_agent_principal, None)
        unauthorized = self.client.get("/agent/review/overview")

        self.assertEqual(authorized.status_code, 200, authorized.text)
        self.assertEqual(forbidden_detail.status_code, 403)
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()["pending_count"], 0)
        self.assertEqual(unauthorized.status_code, 401)

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
            evidence=[{"source_text": "Bob takes over."}],
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
            item.version += 1
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
            item.version += 1
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
        self.assertIn("/agent/review/overview", openapi["paths"])
        self.assertIn("/agent/review/records", openapi["paths"])
        self.assertIn("/agent/review/records/{record_id}", openapi["paths"])

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
            item.version += 1
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
                tenant_id="tenant-1",
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

    def test_real_write_rejects_under_default_switches_and_preserves_business_data(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )

        response = self.client.post(f"/agent/commands/{command_id}/execute", json={"comment": "execute"})

        self.assertEqual(response.status_code, 403)
        self.assertIn("command_execution_disabled", response.json()["detail"]["reasons"])
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(item.version, 1)
        finally:
            db.close()

    def test_pilot_execute_updates_action_item_and_audit_in_one_transaction(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )

        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings()):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={"comment": "execute"})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "succeeded")
        self.assertTrue(body["writes_performed"])
        self.assertEqual(body["before_state"]["data"]["owner"], "Alice")
        self.assertEqual(body["after_state"]["data"]["owner"], "Bob")
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            command = db.get(ControlledWriteCommandRecord, command_id)
            audit = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_succeeded")
            ).one()
            self.assertEqual(item.owner, "Bob")
            self.assertEqual(item.version, 2)
            self.assertEqual(command.status, "succeeded")
            self.assertTrue(audit.audit_context["business_writes_performed"])
        finally:
            db.close()

    def test_pilot_execute_is_idempotent(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )

        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings()):
            first = self.client.post(f"/agent/commands/{command_id}/execute", json={})
            second = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "duplicate")
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_succeeded")
            ).all()
            self.assertEqual(item.owner, "Bob")
            self.assertEqual(item.version, 2)
            self.assertEqual(len(audits), 1)
        finally:
            db.close()

    def test_pilot_execute_rejects_non_whitelisted_tenant_project(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )

        settings = Settings(
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants="other-tenant",
            agent_command_pilot_projects="other-project",
            agent_grey_enabled=True,
            agent_grey_tenants="tenant-1",
            agent_grey_projects="project-1",
            agent_grey_users="user-1",
            agent_grey_percentage=100,
            agent_grey_project_daily_limit=100,
            agent_grey_user_daily_limit=100,
            agent_grey_concurrency_limit=1,
        )
        with patch("app.agent_command_executor.get_settings", return_value=settings):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 403)
        self.assertIn("pilot_tenant_not_whitelisted", response.json()["detail"]["reasons"])

    def test_pilot_execute_rejects_non_pilot_field_and_risk(self) -> None:
        self.create_action_proposal(proposed_changes={"dependencies": {"from": [], "to": ["other"]}}, risk_level="high")
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )

        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings()):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 403)
        reasons = response.json()["detail"]["reasons"]
        self.assertIn("pilot_risk_not_allowed", reasons)
        self.assertIn("pilot_field_not_allowed:dependencies", reasons)

    def test_pilot_execute_failure_rolls_back_business_and_audit(self) -> None:
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
                roles=("agent_high_risk_approver",),
                permissions=("command_execute",),
                tenant_id="tenant-1",
                project_ids=("project-1",),
            )
            with self.assertRaises(RuntimeError):
                execute_command_in_transaction(
                    db,
                    command_id=command_id,
                    principal=principal,
                    settings=self.pilot_settings(),
                    fail_stage="after_audit",
                )
            item = db.get(ActionItem, "action-1")
            command = db.get(ControlledWriteCommandRecord, command_id)
            audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_succeeded")
            ).all()
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(item.version, 1)
            self.assertEqual(command.status, "ready")
            self.assertEqual(audits, [])
        finally:
            db.close()

    def test_pilot_rollback_restores_action_item_and_is_idempotent(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings(rollback=True)):
            execute_response = self.client.post(f"/agent/commands/{command_id}/execute", json={})
            rollback_response = self.client.post(f"/agent/commands/{command_id}/rollback/execute", json={"comment": "rollback"})
            duplicate_response = self.client.post(f"/agent/commands/{command_id}/rollback/execute", json={"comment": "rollback again"})

        self.assertEqual(execute_response.status_code, 200, execute_response.text)
        self.assertEqual(rollback_response.status_code, 200, rollback_response.text)
        self.assertEqual(duplicate_response.status_code, 200, duplicate_response.text)
        self.assertEqual(duplicate_response.json()["status"], "duplicate")
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            command = db.get(ControlledWriteCommandRecord, command_id)
            rollback_audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "rollback_succeeded")
            ).all()
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(item.version, 3)
            self.assertEqual(command.status, "rolled_back")
            self.assertEqual(len(rollback_audits), 1)
        finally:
            db.close()

    def test_pilot_rollback_rejects_version_conflict(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings(rollback=True)):
            self.client.post(f"/agent/commands/{command_id}/execute", json={})
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.version += 1
            db.commit()
        finally:
            db.close()

        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings(rollback=True)):
            response = self.client.post(f"/agent/commands/{command_id}/rollback/execute", json={"comment": "rollback"})

        self.assertEqual(response.status_code, 409)
        self.assertIn("rollback_version_conflict", response.json()["detail"]["reasons"])

    def test_pilot_execute_does_not_modify_requirement_or_risk(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings()):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 200, response.text)
        db = self.SessionLocal()
        try:
            requirement = db.get(Requirement, "req-1")
            risk = db.get(Risk, "risk-1")
            self.assertEqual(requirement.version, 1)
            self.assertEqual(requirement.status, "confirmed")
            self.assertEqual(risk.version, 1)
            self.assertEqual(risk.status, "active")
        finally:
            db.close()

    def test_real_write_requires_principal_scope(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute"),
            project_ids=("other-project",),
        )

        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings()):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 403)

    def test_real_write_direct_call_without_required_principal_is_rejected(self) -> None:
        db = self.SessionLocal()
        try:
            with self.assertRaises(Exception) as raised:
                execute_command_in_transaction(
                    db=db,
                    command_id="any",
                    principal=AgentPrincipal(user_id="user-1", reviewer_identity="reviewer-1"),
                    settings=self.pilot_settings(),
                )
            item = db.get(ActionItem, "action-1")
            self.assertEqual(getattr(raised.exception, "status_code", None), 404)
            self.assertEqual(item.owner, "Alice")
        finally:
            db.close()

    def test_phase14_grey_config_is_required_even_when_phase13_pilot_is_enabled(self) -> None:
        self.create_action_proposal()
        approved = self.client.post(
            "/agent/action-proposals/proposal-action-1/approve",
            json={},
            headers=self.auth_headers(),
        )
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        phase13_only = Settings(
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants="tenant-1",
            agent_command_pilot_projects="project-1",
        )

        with patch("app.agent_command_executor.get_settings", return_value=phase13_only):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 403, response.text)
        reasons = response.json()["detail"]["reasons"]
        self.assertIn("grey_disabled", reasons)
        self.assertIn("grey_user_not_whitelisted", reasons)
        self.assertIn("grey_percentage_zero", reasons)
        self.assertIn("project_daily_limit_zero", reasons)
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            audit = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "rejected")
            ).one()
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(audit.result, "rejected")
            self.assertFalse(audit.audit_context["writes_performed"])
            self.assertTrue(audit.audit_context["guardrail_rejection"])
        finally:
            db.close()

    def test_phase14_rejects_non_whitelisted_user(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={})
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        settings = Settings(
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants="tenant-1",
            agent_command_pilot_projects="project-1",
            agent_grey_enabled=True,
            agent_grey_tenants="tenant-1",
            agent_grey_projects="project-1",
            agent_grey_users="other-user",
            agent_grey_percentage=100,
            agent_grey_project_daily_limit=100,
            agent_grey_user_daily_limit=100,
            agent_grey_concurrency_limit=1,
        )

        with patch("app.agent_command_executor.get_settings", return_value=settings):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 403)
        self.assertIn("grey_user_not_whitelisted", response.json()["detail"]["reasons"])

    def test_phase14_global_kill_switch_rejects_new_execute(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={})
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        settings = Settings(
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants="tenant-1",
            agent_command_pilot_projects="project-1",
            agent_global_kill_switch=True,
            agent_grey_enabled=True,
            agent_grey_tenants="tenant-1",
            agent_grey_projects="project-1",
            agent_grey_users="user-1",
            agent_grey_percentage=100,
            agent_grey_project_daily_limit=100,
            agent_grey_user_daily_limit=100,
            agent_grey_concurrency_limit=1,
        )

        with patch("app.agent_command_executor.get_settings", return_value=settings):
            response = self.client.post(f"/agent/commands/{command_id}/execute", json={})

        self.assertEqual(response.status_code, 403)
        self.assertIn("global_kill_switch_enabled", response.json()["detail"]["reasons"])

    def test_phase14_ops_metrics_and_audit_search_are_scoped_and_sanitized(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={})
        command_id = approved.json()["command"]["id"]
        self.set_principal(
            permissions=("proposal_view", "proposal_review", "command_dry_run", "command_execute", "audit_view", "rollback_execute")
        )
        with patch("app.agent_command_executor.get_settings", return_value=self.pilot_settings()):
            execute_response = self.client.post(f"/agent/commands/{command_id}/execute", json={})
        self.assertEqual(execute_response.status_code, 200, execute_response.text)
        db = self.SessionLocal()
        try:
            audit = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_succeeded")
            ).one()
            audit.audit_context = {**audit.audit_context, "token": "secret-token"}
            db.add(audit)
            db.commit()
        finally:
            db.close()

        metrics = self.client.get("/agent/ops/metrics")
        audits = self.client.get("/agent/ops/audits", params={"command_id": command_id})

        self.assertEqual(metrics.status_code, 200, metrics.text)
        self.assertGreaterEqual(metrics.json()["totals"]["success"], 1)
        self.assertEqual(audits.status_code, 200, audits.text)
        self.assertEqual(audits.json()["total"], 2)
        contexts = [item["audit_context"] for item in audits.json()["items"]]
        self.assertTrue(any(context.get("token") == "[redacted]" for context in contexts))

        self.set_principal(tenant_id="other-tenant")
        denied = self.client.get("/agent/ops/audits", params={"command_id": command_id})
        self.assertEqual(denied.json()["total"], 0)

    def test_phase14_circuit_status_and_reset_endpoints(self) -> None:
        self.set_principal(permissions=("audit_view",), project_ids=("project-1",))

        status = self.client.get("/agent/ops/circuit-breakers", params={"tenant_id": "tenant-1", "project_id": "project-1"})
        reset = self.client.post(
            "/agent/ops/circuit-breakers/reset",
            json={"tenant_id": "tenant-1", "project_id": "project-1", "reason": "manual recovery"},
        )

        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["status"], "closed")
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(reset.json()["status"], "reset")
        self.assertEqual(reset.json()["audit"]["result"], "circuit_reset")

    def test_phase14_ops_routes_are_in_openapi(self) -> None:
        openapi = self.client.get("/openapi.json").json()

        self.assertIn("/agent/ops/metrics", openapi["paths"])
        self.assertIn("/agent/ops/audits", openapi["paths"])
        self.assertIn("/agent/ops/circuit-breakers", openapi["paths"])
        self.assertIn("/agent/ops/circuit-breakers/reset", openapi["paths"])
        self.assertIn("/agent/ops/preflight", openapi["paths"])

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
            item.version += 1
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
        self.assertIn("/agent/commands/{command_id}/execute", openapi["paths"])
        self.assertIn("/agent/commands/{command_id}/rollback/dry-run", openapi["paths"])
        self.assertIn("/agent/commands/{command_id}/rollback/execute", openapi["paths"])

    def test_action_item_scope_backfill_uses_unique_authoritative_scope(self) -> None:
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.tenant_id = "default-tenant"
            item.project_id = "default-project"
            db.commit()

            stats = backfill_action_item_scopes(db, run_id="phase12-backfill", dry_run=False)
            item = db.get(ActionItem, "action-1")
            audit = db.scalars(select(ActionItemScopeBackfillAudit)).one()

            self.assertEqual(stats.applied, 1)
            self.assertEqual(item.tenant_id, "tenant-1")
            self.assertEqual(item.project_id, "project-1")
            self.assertEqual(audit.status, "applied")
            self.assertFalse(audit.dry_run)
            self.assertEqual(audit.reason, "unique_authoritative_requirement_or_risk_scope")
        finally:
            db.close()

    def test_action_item_scope_backfill_review_for_unverifiable_scope(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(id="phase12-review-meeting", title="Phase 12 review", status="completed")
            summary = MeetingSummary(
                id="phase12-review-summary",
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
                rag_chunk_ids=[],
            )
            item = ActionItem(
                id="phase12-review-action",
                meeting_id=meeting.id,
                summary_id=summary.id,
                task="Needs review",
                status="open",
            )
            db.add_all([meeting, summary, item])
            db.commit()

            stats = backfill_action_item_scopes(db, run_id="phase12-review", dry_run=False)
            item = db.get(ActionItem, "phase12-review-action")
            audit = db.scalars(
                select(ActionItemScopeBackfillAudit).where(ActionItemScopeBackfillAudit.action_item_id == item.id)
            ).one()

            self.assertGreaterEqual(stats.review, 1)
            self.assertEqual(item.tenant_id, "default-tenant")
            self.assertEqual(item.project_id, "default-project")
            self.assertEqual(audit.status, "review")
            self.assertEqual(audit.reason, "no_unique_verifiable_scope")
        finally:
            db.close()

    def test_action_item_scope_backfill_is_idempotent_and_preserves_existing_scope(self) -> None:
        db = self.SessionLocal()
        try:
            first = backfill_action_item_scopes(db, run_id="phase12-idempotent", dry_run=False)
            second = backfill_action_item_scopes(db, run_id="phase12-idempotent", dry_run=False)
            item = db.get(ActionItem, "action-1")
            audits = db.scalars(select(ActionItemScopeBackfillAudit)).all()

            self.assertEqual(first.skipped_existing, 1)
            self.assertEqual(second.skipped_idempotent, 1)
            self.assertEqual(item.tenant_id, "tenant-1")
            self.assertEqual(item.project_id, "project-1")
            self.assertEqual(len(audits), 1)
        finally:
            db.close()

    def test_action_item_scope_backfill_rollback_restores_previous_scope(self) -> None:
        db = self.SessionLocal()
        try:
            item = db.get(ActionItem, "action-1")
            item.tenant_id = "default-tenant"
            item.project_id = "default-project"
            db.commit()

            backfill_action_item_scopes(db, run_id="phase12-rollback", dry_run=False)
            rollback_stats = rollback_action_item_scope_backfill(db, run_id="phase12-rollback")
            item = db.get(ActionItem, "action-1")
            audit = db.scalars(select(ActionItemScopeBackfillAudit)).one()

            self.assertEqual(rollback_stats.rolled_back, 1)
            self.assertEqual(item.tenant_id, "default-tenant")
            self.assertEqual(item.project_id, "default-project")
            self.assertEqual(audit.status, "rolled_back")
        finally:
            db.close()

    def test_transaction_rehearsal_writes_only_agent_audit(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={})
        command_id = approved.json()["command"]["id"]
        db = self.SessionLocal()
        try:
            principal = AgentPrincipal(
                user_id="user-1",
                reviewer_identity="reviewer-1",
                permissions=("command_execute",),
                tenant_id="tenant-1",
                project_ids=("project-1",),
            )
            result = rehearse_command_transaction(db, command_id=command_id, principal=principal)
            duplicate = rehearse_command_transaction(db, command_id=command_id, principal=principal)
            item = db.get(ActionItem, "action-1")
            requirement = db.get(Requirement, "req-1")
            risk = db.get(Risk, "risk-1")
            audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_rehearsal")
            ).all()

            self.assertEqual(result.status, "execution_rehearsal")
            self.assertEqual(duplicate.status, "duplicate")
            self.assertEqual(len(audits), 1)
            self.assertFalse(audits[0].audit_context["business_writes_performed"])
            self.assertEqual(item.owner, "Alice")
            self.assertEqual(item.status, "open")
            self.assertEqual(requirement.version, 1)
            self.assertEqual(risk.version, 1)
        finally:
            db.close()

    def test_transaction_rehearsal_mid_failure_rolls_back_audit(self) -> None:
        self.create_action_proposal()
        approved = self.client.post("/agent/action-proposals/proposal-action-1/approve", json={})
        command_id = approved.json()["command"]["id"]
        db = self.SessionLocal()
        try:
            principal = AgentPrincipal(
                user_id="user-1",
                reviewer_identity="reviewer-1",
                permissions=("command_execute",),
                tenant_id="tenant-1",
                project_ids=("project-1",),
            )
            with self.assertRaises(RuntimeError):
                rehearse_command_transaction(db, command_id=command_id, principal=principal, fail_stage="after_audit")
            item = db.get(ActionItem, "action-1")
            audits = db.scalars(
                select(AgentAuditRecord).where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_rehearsal")
            ).all()

            self.assertEqual(audits, [])
            self.assertEqual(item.owner, "Alice")
        finally:
            db.close()

    def test_local_agent_login_creates_session_and_authorizes_review_overview(self) -> None:
        self.app.dependency_overrides.pop(get_agent_principal, None)
        with patch(
            "app.agent_auth_service.get_settings",
            return_value=Settings(
                agent_local_auth_enabled=True,
                agent_local_auth_tenant_id="tenant-1",
                agent_local_auth_project_id="project-1",
                agent_local_auth_token_ttl_hours=2,
            ),
        ):
            response = self.client.post("/agent/auth/login", json={"display_name": "Local Reviewer"})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["token"])
        self.assertEqual(body["tenant_id"], "tenant-1")
        self.assertEqual(body["project_scope"], ["project-1"])
        self.assertIn("proposal_review", body["permissions"])

        overview = self.client.get("/agent/review/overview", headers={"Authorization": f"Bearer {body['token']}"})
        self.assertEqual(overview.status_code, 200, overview.text)

        logout = self.client.post("/agent/auth/logout", headers={"Authorization": f"Bearer {body['token']}"})
        self.assertEqual(logout.status_code, 200, logout.text)
        expired = self.client.get("/agent/review/overview", headers={"Authorization": f"Bearer {body['token']}"})
        self.assertEqual(expired.status_code, 401, expired.text)

    def test_local_agent_login_is_fail_closed_by_default(self) -> None:
        self.app.dependency_overrides.pop(get_agent_principal, None)
        response = self.client.post("/agent/auth/login", json={"display_name": "Local Reviewer"})
        self.assertEqual(response.status_code, 403, response.text)

    def test_real_meeting_owner_change_generates_idempotent_proposal(self) -> None:
        db = self.SessionLocal()
        try:
            self._seed_real_meeting_change(db)
            first = generate_action_item_proposals_for_meeting(db, "real-meeting-new", persist=True)
            second = generate_action_item_proposals_for_meeting(db, "real-meeting-new", persist=True)
            generated = [item for item in first if item.generated]
            duplicate = [item for item in second if item.skip_reason == "duplicate_proposal"]
            proposal = db.get(AgentActionProposalRecord, generated[0].proposal_id)

            self.assertEqual(len(generated), 1)
            self.assertEqual(len(duplicate), 1)
            self.assertEqual(proposal.target_object_type, "AgentActionItem")
            self.assertEqual(proposal.target_object_id, "historical-action-owner")
            self.assertEqual(proposal.status, "pending")
            self.assertEqual(proposal.proposed_changes["owner"], {"from": "前端", "to": "后端"})
            self.assertEqual(proposal.metadata_["source_meeting_id"], "real-meeting-new")
            self.assertIn("后端", proposal.evidence[0]["source_text"])
        finally:
            db.close()

    def test_real_meeting_new_or_unchanged_or_unsupported_items_do_not_generate_proposals(self) -> None:
        db = self.SessionLocal()
        try:
            self._seed_real_meeting_change(db, include_changed_item=False)
            unchanged = ActionItem(
                id="real-action-unchanged",
                tenant_id="tenant-1",
                project_id="project-1",
                meeting_id="real-meeting-new",
                summary_id="real-summary-new",
                task="接口联调联系人",
                owner="前端",
                due_date="周三",
                priority="medium",
                status="open",
                source_text="接口联调联系人仍由前端负责，周三完成。",
            )
            new_item = ActionItem(
                id="real-action-new",
                tenant_id="tenant-1",
                project_id="project-1",
                meeting_id="real-meeting-new",
                summary_id="real-summary-new",
                task="全新验收清单整理",
                owner="后端",
                due_date="周五",
                priority="medium",
                status="open",
                source_text="全新验收清单由后端周五整理。",
            )
            insufficient = ActionItem(
                id="real-action-insufficient",
                tenant_id="tenant-1",
                project_id="project-1",
                meeting_id="real-meeting-new",
                summary_id="real-summary-new",
                task="接口响应优化",
                owner="后端",
                due_date="周五",
                priority="medium",
                status="open",
                source_text="接口响应优化需要继续跟进。",
            )
            historical_insufficient = ActionItem(
                id="historical-action-insufficient",
                tenant_id="tenant-1",
                project_id="project-1",
                meeting_id="real-meeting-old",
                summary_id="real-summary-old",
                task="接口响应优化",
                owner="前端",
                due_date="周三",
                priority="medium",
                status="open",
                source_text="接口响应优化由前端周三完成。",
            )
            db.add_all([unchanged, new_item, insufficient, historical_insufficient])
            db.commit()

            diagnostics = generate_action_item_proposals_for_meeting(db, "real-meeting-new", persist=True)
            reasons = {item.action_item_id: item.skip_reason for item in diagnostics}
            self.assertEqual(reasons["real-action-unchanged"], "no_field_change")
            self.assertEqual(reasons["real-action-new"], "no_historical_match")
            self.assertEqual(reasons["real-action-insufficient"], "insufficient_evidence")
            self.assertFalse(any(item.generated for item in diagnostics))
        finally:
            db.close()

    def _seed_real_meeting_change(self, db: Session, *, include_changed_item: bool = True) -> None:
        old_meeting = Meeting(id="real-meeting-old", title="真实历史会", status="completed")
        old_summary = MeetingSummary(
            id="real-summary-old",
            meeting_id=old_meeting.id,
            overview="old",
            agenda=[],
            topics=[],
            speaker_summaries=[],
            decisions=[],
            risks=[],
            open_questions=[],
            next_steps=[],
            meeting_agenda=[],
            meeting_summary="old",
            key_conclusions=[],
            unresolved_issues=[],
            risks_and_focus=[],
        )
        historical = ActionItem(
            id="historical-action-owner",
            tenant_id="tenant-1",
            project_id="project-1",
            meeting_id=old_meeting.id,
            summary_id=old_summary.id,
            task="接口联调联系人",
            owner="前端",
            due_date="周三",
            priority="medium",
            status="open",
            source_text="接口联调联系人由前端负责，周三完成。",
            version=3,
        )
        new_meeting = Meeting(id="real-meeting-new", title="真实变更会", status="completed")
        new_summary = MeetingSummary(
            id="real-summary-new",
            meeting_id=new_meeting.id,
            overview="new",
            agenda=[],
            topics=[],
            speaker_summaries=[],
            decisions=[],
            risks=[],
            open_questions=[],
            next_steps=[],
            meeting_agenda=[],
            meeting_summary="new",
            key_conclusions=[],
            unresolved_issues=[],
            risks_and_focus=[],
        )
        segment = TranscriptSegment(
            id="real-segment-owner",
            meeting_id=new_meeting.id,
            audio_file_id=None,
            segment_index=1,
            start_time=1.0,
            end_time=5.0,
            text="接口联调联系人确认改为后端负责，截止时间仍是周三。",
            speaker_label="speaker_1",
            speaker_name="张三",
        )
        rows = [old_meeting, old_summary, historical, new_meeting, new_summary, segment]
        if include_changed_item:
            rows.append(
                ActionItem(
                    id="real-action-owner",
                    tenant_id="tenant-1",
                    project_id="project-1",
                    meeting_id=new_meeting.id,
                    summary_id=new_summary.id,
                    task="接口联调联系人",
                    owner="后端",
                    due_date="周三",
                    priority="medium",
                    status="open",
                    source_text="接口联调联系人确认改为后端负责，截止时间仍是周三。",
                )
            )
        db.add_all(rows)
        db.commit()

    def assert_no_approved_confirmation(self) -> None:
        db = self.SessionLocal()
        try:
            decisions = db.scalars(select(AgentProposalConfirmationRecord.decision)).all()
            self.assertNotIn("approved", decisions)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
