from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reasoning_engine import EvidenceRef as ReasoningEvidenceRef
from app.reasoning_engine import ReasoningContext
from app.responsibility_evidence_matrix import ResponsibilityEvidenceMatrix, ResponsibilityEvidenceMatrixRow
from app.responsibility_extractor import ResponsibilityContext, ResponsibilityEvidence


ActionType = Literal[
    "create_task",
    "update_task",
    "notify_owner",
    "request_confirmation",
    "search_information",
]
ActionSupportLevel = Literal["supports", "weakens", "conflicts", "context_only"]
ActionEvidenceStatus = Literal[
    "confirmed",
    "active",
    "candidate",
    "needs_review",
    "shadow_only",
    "conflicted",
    "expired",
    "unknown",
]
PermissionStateName = Literal[
    "proposal_only",
    "blocked_pending_confirmation",
    "blocked_missing_permission",
    "blocked_by_policy",
    "dry_run_allowed",
    "execution_not_supported",
]
AllowedNextStep = Literal[
    "request_confirmation",
    "show_for_review",
    "dry_run",
    "revise_candidate",
    "reject_candidate",
    "no_action",
]


class ActionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1)
    target_id: str | None = None
    target_label: str = Field(min_length=1)
    project_id: str | None = None
    meeting_id: str | None = None
    owner_candidate: str | None = None
    related_refs: list[str] = Field(default_factory=list)


class ActionReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    reasoning_refs: list[str] = Field(default_factory=list)
    risk_or_gap: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)


class ActionEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    meeting_id: str | None = None
    supported_action_parts: list[str] = Field(default_factory=list)
    support_level: ActionSupportLevel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_status: ActionEvidenceStatus = "unknown"

    @model_validator(mode="after")
    def require_action_part_support(self) -> "ActionEvidenceRef":
        if not self.supported_action_parts:
            raise ValueError("action evidence ref requires supported_action_parts")
        return self


class PermissionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: PermissionStateName
    required_permissions: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    allowed_next_step: AllowedNextStep


class ActionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1)
    action_type: ActionType
    reason: ActionReason
    target: ActionTarget
    evidence_refs: list[ActionEvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool
    permission_state: PermissionState

    @model_validator(mode="after")
    def require_evidence_first(self) -> "ActionCandidate":
        if not self.evidence_refs:
            raise ValueError("action candidate requires evidence")
        if not any(item.support_level != "context_only" for item in self.evidence_refs):
            raise ValueError("action candidate requires non-context evidence")
        if any(item.support_level == "conflicts" for item in self.evidence_refs) and not self.requires_confirmation:
            raise ValueError("conflicting action evidence requires confirmation")
        if self.action_type in {"create_task", "update_task", "notify_owner", "search_information"} and not self.requires_confirmation:
            raise ValueError("write-adjacent or external action proposals require confirmation")
        return self


class ActionProposalEngine:
    def generate(
        self,
        *,
        reasoning_contexts: list[ReasoningContext | dict[str, Any]] | None = None,
        responsibility_contexts: list[ResponsibilityContext | dict[str, Any]] | None = None,
        responsibility_matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None = None,
        memory_context: Any | None = None,
        current_meeting_context: dict[str, Any] | None = None,
    ) -> list[ActionCandidate]:
        current = current_meeting_context or {}
        candidates: list[ActionCandidate] = []
        matrix_rows = self._matrix_rows(responsibility_matrix)

        for reasoning in self._reasoning_contexts(reasoning_contexts):
            if reasoning.reasoning_type == "risk_assessment":
                candidate = self._risk_confirmation_candidate(reasoning=reasoning, current=current)
                if candidate is not None:
                    candidates.append(candidate)
            elif reasoning.reasoning_type == "responsibility_analysis" and self._has_conflict_evidence(reasoning.evidence_refs):
                candidate = self._reasoning_conflict_candidate(reasoning=reasoning, current=current)
                if candidate is not None:
                    candidates.append(candidate)

        for row in matrix_rows:
            if row.consistency_status == "responsibility_only":
                candidate = self._create_task_candidate(row=row, current=current)
                if candidate is not None:
                    candidates.append(candidate)
            elif row.consistency_status == "owner_conflict":
                candidate = self._matrix_conflict_candidate(row=row, current=current)
                if candidate is not None:
                    candidates.append(candidate)

        if not matrix_rows:
            for context in self._responsibility_contexts(responsibility_contexts):
                if context.evidence and context.owner and not any(item.requires_confirmation for item in context.evidence):
                    candidate = self._create_task_candidate_from_context(context=context, current=current)
                    if candidate is not None:
                        candidates.append(candidate)

        # Stage8.5.2 accepts MemoryContext as input but does not propose actions
        # from memory alone. Missing current evidence must result in no action.
        _ = memory_context
        return self._deduplicate(candidates)

    def _risk_confirmation_candidate(
        self,
        *,
        reasoning: ReasoningContext,
        current: dict[str, Any],
    ) -> ActionCandidate | None:
        refs = self._refs_from_reasoning(reasoning, supported_parts=["action_type", "reason", "target"])
        if not refs:
            return None
        return self._candidate(
            action_type="request_confirmation",
            target=ActionTarget(
                target_type="risk_review",
                target_id=reasoning.reasoning_id,
                target_label=self._short_label(reasoning.claim),
                project_id=reasoning.impact_scope.project_id or self._clean_text(current.get("project_id")),
                meeting_id=self._first_meeting_id(reasoning, current),
                related_refs=[reasoning.reasoning_id],
            ),
            reason=ActionReason(
                summary="Risk reasoning should be confirmed before any downstream action is considered.",
                reasoning_refs=[reasoning.reasoning_id],
                risk_or_gap="risk_reasoning",
                expected_outcome="A reviewer can confirm whether the risk needs mitigation planning.",
            ),
            evidence_refs=refs,
            confidence=min(reasoning.confidence, self._avg_ref_confidence(refs)),
            requires_confirmation=True,
            permission_state=self._request_confirmation_permission(),
        )

    def _reasoning_conflict_candidate(
        self,
        *,
        reasoning: ReasoningContext,
        current: dict[str, Any],
    ) -> ActionCandidate | None:
        refs = self._refs_from_reasoning(reasoning, supported_parts=["action_type", "reason", "target"])
        if not refs:
            return None
        return self._candidate(
            action_type="request_confirmation",
            target=ActionTarget(
                target_type="responsibility_conflict",
                target_id=reasoning.reasoning_id,
                target_label=self._short_label(reasoning.claim),
                project_id=reasoning.impact_scope.project_id or self._clean_text(current.get("project_id")),
                meeting_id=self._first_meeting_id(reasoning, current),
                related_refs=[reasoning.reasoning_id],
            ),
            reason=ActionReason(
                summary="Responsibility evidence conflicts and must be resolved by a reviewer.",
                reasoning_refs=[reasoning.reasoning_id],
                risk_or_gap="responsibility_conflict",
                expected_outcome="A reviewer can confirm the correct responsibility before any task update.",
            ),
            evidence_refs=refs,
            confidence=min(reasoning.confidence, self._avg_ref_confidence(refs)),
            requires_confirmation=True,
            permission_state=self._request_confirmation_permission(),
        )

    def _create_task_candidate(
        self,
        *,
        row: ResponsibilityEvidenceMatrixRow,
        current: dict[str, Any],
    ) -> ActionCandidate | None:
        refs = self._refs_from_responsibility_evidence(
            evidence_items=row.evidence,
            responsibility_id=row.task_key,
            supported_parts=["action_type", "target", "reason"],
        )
        if not refs:
            return None
        candidate = row.responsibility_candidates[0] if row.responsibility_candidates else None
        task = candidate.task if candidate is not None else row.task_key
        owner = candidate.owner if candidate is not None else None
        return self._candidate(
            action_type="create_task",
            target=ActionTarget(
                target_type="task",
                target_id=None,
                target_label=self._short_label(task),
                project_id=self._clean_text(current.get("project_id")),
                meeting_id=self._meeting_id_from_action_refs(refs, current),
                owner_candidate=owner,
                related_refs=[row.task_key],
            ),
            reason=ActionReason(
                summary="Confirmed responsibility evidence exists without a matching action item.",
                reasoning_refs=[],
                risk_or_gap="responsibility_only",
                expected_outcome="A reviewer can decide whether to create a task from the cited responsibility evidence.",
            ),
            evidence_refs=refs,
            confidence=min(row.confidence, self._avg_ref_confidence(refs)),
            requires_confirmation=True,
            permission_state=self._blocked_permission(required_permissions=["task:create"]),
        )

    def _create_task_candidate_from_context(
        self,
        *,
        context: ResponsibilityContext,
        current: dict[str, Any],
    ) -> ActionCandidate | None:
        refs = self._refs_from_responsibility_evidence(
            evidence_items=context.evidence,
            responsibility_id=context.responsibility_id,
            supported_parts=["action_type", "target", "reason"],
        )
        if not refs:
            return None
        return self._candidate(
            action_type="create_task",
            target=ActionTarget(
                target_type="task",
                target_id=None,
                target_label=self._short_label(context.task),
                project_id=self._clean_text(current.get("project_id")),
                meeting_id=self._meeting_id_from_action_refs(refs, current),
                owner_candidate=context.owner,
                related_refs=[context.responsibility_id],
            ),
            reason=ActionReason(
                summary="Confirmed responsibility context can be reviewed as a task creation proposal.",
                reasoning_refs=[],
                risk_or_gap="confirmed_responsibility",
                expected_outcome="A reviewer can decide whether the responsibility should become a tracked task.",
            ),
            evidence_refs=refs,
            confidence=min(context.confidence, self._avg_ref_confidence(refs)),
            requires_confirmation=True,
            permission_state=self._blocked_permission(required_permissions=["task:create"]),
        )

    def _matrix_conflict_candidate(
        self,
        *,
        row: ResponsibilityEvidenceMatrixRow,
        current: dict[str, Any],
    ) -> ActionCandidate | None:
        refs = self._refs_from_responsibility_evidence(
            evidence_items=row.evidence,
            responsibility_id=row.task_key,
            supported_parts=["action_type", "target", "reason"],
            support_level="conflicts",
        )
        if row.action_owner:
            refs.append(
                self._evidence_ref(
                    source_type="responsibility_matrix",
                    source_id=row.task_key,
                    meeting_id=self._clean_text(current.get("meeting_id")),
                    supported_action_parts=["reason", "target"],
                    support_level="supports",
                    confidence=row.confidence,
                    evidence_status="unknown",
                )
            )
        if not refs:
            return None
        task = row.responsibility_candidates[0].task if row.responsibility_candidates else row.task_key
        return self._candidate(
            action_type="request_confirmation",
            target=ActionTarget(
                target_type="responsibility_conflict",
                target_id=row.task_key,
                target_label=self._short_label(task),
                project_id=self._clean_text(current.get("project_id")),
                meeting_id=self._meeting_id_from_action_refs(refs, current),
                related_refs=[row.task_key],
            ),
            reason=ActionReason(
                summary="Responsibility matrix shows conflicting owner evidence.",
                reasoning_refs=[],
                risk_or_gap="responsibility_conflict",
                expected_outcome="A reviewer can resolve the owner conflict before any task update.",
            ),
            evidence_refs=refs,
            confidence=min(row.confidence, self._avg_ref_confidence(refs)),
            requires_confirmation=True,
            permission_state=self._request_confirmation_permission(),
        )

    def _candidate(
        self,
        *,
        action_type: ActionType,
        target: ActionTarget,
        reason: ActionReason,
        evidence_refs: list[ActionEvidenceRef],
        confidence: float,
        requires_confirmation: bool,
        permission_state: PermissionState,
    ) -> ActionCandidate:
        action_id = self._action_id(
            action_type=action_type,
            target=target,
            reason=reason,
            evidence_refs=evidence_refs,
        )
        return ActionCandidate(
            action_id=action_id,
            action_type=action_type,
            target=target,
            reason=reason,
            evidence_refs=evidence_refs,
            confidence=self._float_value(confidence),
            requires_confirmation=requires_confirmation,
            permission_state=permission_state,
        )

    def _refs_from_reasoning(
        self,
        reasoning: ReasoningContext,
        *,
        supported_parts: list[str],
    ) -> list[ActionEvidenceRef]:
        refs: list[ActionEvidenceRef] = []
        for ref in reasoning.evidence_refs:
            refs.append(
                self._evidence_ref(
                    source_type=ref.source_type,
                    source_id=ref.source_id,
                    meeting_id=ref.meeting_id,
                    supported_action_parts=supported_parts,
                    support_level=ref.support_level,
                    confidence=ref.confidence,
                    evidence_status=ref.evidence_status,
                    stable_source_ref=ref.evidence_ref_id,
                )
            )
        return refs

    def _refs_from_responsibility_evidence(
        self,
        *,
        evidence_items: list[ResponsibilityEvidence],
        responsibility_id: str,
        supported_parts: list[str],
        support_level: ActionSupportLevel = "supports",
    ) -> list[ActionEvidenceRef]:
        refs: list[ActionEvidenceRef] = []
        for evidence in evidence_items:
            source_id = self._clean_text(evidence.segment_id or evidence.event_id or evidence.utterance_id or responsibility_id)
            if not source_id:
                continue
            status: ActionEvidenceStatus = "needs_review" if evidence.requires_confirmation else "active"
            if evidence.source_type == "semantic_event":
                status = "shadow_only"
            refs.append(
                self._evidence_ref(
                    source_type=evidence.source_type,
                    source_id=source_id,
                    meeting_id=evidence.meeting_id,
                    supported_action_parts=supported_parts,
                    support_level=support_level,
                    confidence=evidence.confidence,
                    evidence_status=status,
                )
            )
        return refs

    def _evidence_ref(
        self,
        *,
        source_type: str,
        source_id: str,
        supported_action_parts: list[str],
        support_level: ActionSupportLevel,
        confidence: float,
        evidence_status: ActionEvidenceStatus,
        meeting_id: str | None = None,
        stable_source_ref: str | None = None,
    ) -> ActionEvidenceRef:
        basis = {
            "source_ref": stable_source_ref,
            "source_type": source_type,
            "source_id": source_id,
            "support_level": support_level,
            "parts": supported_action_parts,
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return ActionEvidenceRef(
            evidence_ref_id=f"eref:{digest}",
            source_type=source_type,
            source_id=source_id,
            meeting_id=meeting_id,
            supported_action_parts=supported_action_parts,
            support_level=support_level,
            confidence=self._float_value(confidence),
            evidence_status=evidence_status,
        )

    def _action_id(
        self,
        *,
        action_type: ActionType,
        target: ActionTarget,
        reason: ActionReason,
        evidence_refs: list[ActionEvidenceRef],
    ) -> str:
        basis = {
            "type": action_type,
            "target_type": target.target_type,
            "target_id": target.target_id,
            "target_label": self._normalize(target.target_label),
            "risk_or_gap": reason.risk_or_gap,
            "refs": [ref.evidence_ref_id for ref in evidence_refs],
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return f"action:{action_type}:{digest}"

    @staticmethod
    def _blocked_permission(*, required_permissions: list[str]) -> PermissionState:
        return PermissionState(
            state="blocked_pending_confirmation",
            required_permissions=required_permissions,
            blocked_reasons=["human_confirmation_required", "write_scope_not_enabled"],
            allowed_next_step="request_confirmation",
        )

    @staticmethod
    def _request_confirmation_permission() -> PermissionState:
        return PermissionState(
            state="proposal_only",
            required_permissions=[],
            blocked_reasons=["execution_not_in_scope"],
            allowed_next_step="show_for_review",
        )

    def _reasoning_contexts(self, contexts: list[ReasoningContext | dict[str, Any]] | None) -> list[ReasoningContext]:
        return [item if isinstance(item, ReasoningContext) else ReasoningContext.model_validate(item) for item in contexts or []]

    def _responsibility_contexts(self, contexts: list[ResponsibilityContext | dict[str, Any]] | None) -> list[ResponsibilityContext]:
        return [item if isinstance(item, ResponsibilityContext) else ResponsibilityContext.model_validate(item) for item in contexts or []]

    def _matrix_rows(self, matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None) -> list[ResponsibilityEvidenceMatrixRow]:
        if matrix is None:
            return []
        resolved = matrix if isinstance(matrix, ResponsibilityEvidenceMatrix) else ResponsibilityEvidenceMatrix.model_validate(matrix)
        return resolved.rows

    @staticmethod
    def _has_conflict_evidence(refs: list[ReasoningEvidenceRef]) -> bool:
        return any(ref.support_level == "conflicts" for ref in refs)

    @staticmethod
    def _first_meeting_id(reasoning: ReasoningContext, current: dict[str, Any]) -> str | None:
        return (
            ActionProposalEngine._clean_text(current.get("meeting_id"))
            or next((meeting_id for meeting_id in reasoning.impact_scope.meeting_ids if meeting_id), None)
            or next((ref.meeting_id for ref in reasoning.evidence_refs if ref.meeting_id), None)
        )

    @staticmethod
    def _meeting_id_from_action_refs(refs: list[ActionEvidenceRef], current: dict[str, Any]) -> str | None:
        return ActionProposalEngine._clean_text(current.get("meeting_id")) or next((ref.meeting_id for ref in refs if ref.meeting_id), None)

    @staticmethod
    def _short_label(value: str, *, limit: int = 96) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if len(text) <= limit:
            return text or "review action"
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _avg_ref_confidence(refs: list[ActionEvidenceRef]) -> float:
        if not refs:
            return 0.0
        return max(0.0, min(1.0, sum(ref.confidence for ref in refs) / len(refs)))

    def _deduplicate(self, candidates: list[ActionCandidate]) -> list[ActionCandidate]:
        by_id: dict[str, ActionCandidate] = {}
        for candidate in candidates:
            existing = by_id.get(candidate.action_id)
            if existing is None or candidate.confidence > existing.confidence:
                by_id[candidate.action_id] = candidate
        return list(by_id.values())

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _float_value(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, parsed))


__all__ = [
    "ActionCandidate",
    "ActionEvidenceRef",
    "ActionProposalEngine",
    "ActionReason",
    "ActionTarget",
    "ActionType",
    "PermissionState",
]
