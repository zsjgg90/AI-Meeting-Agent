from __future__ import annotations

import hashlib
import json
from typing import Any

from app.reasoning_engine import ReasoningContext
from app.workflow_recommendation import WorkflowRecommendation, WorkflowRecommendationType
from app.workflow_state import WorkflowStateEvidenceRef, WorkflowStateObservation


class WorkflowRecommendationBuilder:
    _SEVERITY_RANK = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "unknown": 0,
    }

    _CONFIRMATION_BLOCKERS = {
        "missing_confirmation",
        "conflicting_evidence",
    }
    _REFRESH_BLOCKERS = {
        "missing_evidence",
        "stale_state",
    }
    _DEPENDENCY_BLOCKERS = {
        "blocked_dependency",
    }

    def build(
        self,
        *,
        observation: WorkflowStateObservation | dict[str, Any] | None,
        blockers: list[dict[str, Any]] | None = None,
        dependencies: list[dict[str, Any]] | None = None,
        evidence_refs: list[WorkflowStateEvidenceRef | dict[str, Any] | str] | None = None,
        memory_context: Any | None = None,
        reasoning_context: ReasoningContext | dict[str, Any] | None = None,
    ) -> WorkflowRecommendation | None:
        observed = self._observation(observation)
        if observed is None:
            return None

        refs = self._collect_evidence_refs(
            observation=observed,
            blockers=blockers or [],
            dependencies=dependencies or [],
            evidence_refs=evidence_refs or [],
            memory_context=memory_context,
            reasoning_context=reasoning_context,
        )
        if not refs or not any(ref.support_level == "supports" for ref in refs):
            return None

        blocker = self._top_blocker(blockers or [])
        dependency = self._top_dependency(dependencies or [])

        if blocker is not None:
            recommendation_type, reason, requires_confirmation = self._recommendation_from_blocker(blocker)
        elif dependency is not None:
            recommendation_type, reason, requires_confirmation = self._recommendation_from_dependency(dependency)
        elif self._refs_need_refresh(refs):
            recommendation_type = "refresh_evidence"
            reason = "Workflow evidence is stale, expired, unknown, or below the confidence threshold; refresh evidence before relying on this observation."
            requires_confirmation = False
        elif observed.requires_confirmation:
            recommendation_type = "request_confirmation"
            reason = "Workflow state observation requires confirmation before it can be used for downstream review."
            requires_confirmation = True
        else:
            recommendation_type = "no_action"
            reason = "Observed workflow state has supporting evidence and no active blocker or dependency review signal."
            requires_confirmation = False

        confidence = self._recommendation_confidence(
            observation=observed,
            refs=refs,
            recommendation_type=recommendation_type,
            requires_confirmation=requires_confirmation,
        )
        return WorkflowRecommendation(
            recommendation_id=self._recommendation_id(
                workflow_id=observed.workflow_id,
                recommendation_type=recommendation_type,
                reason=reason,
                refs=refs,
            ),
            workflow_id=observed.workflow_id,
            recommendation_type=recommendation_type,
            reason=reason,
            evidence_refs=refs,
            confidence=confidence,
            requires_confirmation=requires_confirmation,
        )

    def _recommendation_from_blocker(
        self,
        blocker: dict[str, Any],
    ) -> tuple[WorkflowRecommendationType, str, bool]:
        blocker_type = self._clean_text(self._value(blocker, "blocker_type")) or "unknown"
        reason = self._clean_text(self._value(blocker, "reason"))

        if blocker_type in self._CONFIRMATION_BLOCKERS:
            return (
                "request_confirmation",
                reason or "Workflow blocker requires human confirmation before any downstream workflow use.",
                True,
            )
        if blocker_type in self._REFRESH_BLOCKERS:
            return (
                "refresh_evidence",
                reason or "Workflow blocker indicates missing or stale evidence that should be refreshed.",
                False,
            )
        if blocker_type in self._DEPENDENCY_BLOCKERS:
            return (
                "review_dependency",
                reason or "Workflow blocker indicates an active dependency that should be reviewed.",
                True,
            )
        return (
            "manual_review",
            reason or "Workflow blocker is outside automatic recommendation rules and needs manual review.",
            True,
        )

    def _recommendation_from_dependency(
        self,
        dependency: dict[str, Any],
    ) -> tuple[WorkflowRecommendationType, str, bool]:
        dependency_type = self._clean_text(self._value(dependency, "dependency_type")) or "unknown"
        reason = self._clean_text(self._value(dependency, "reason"))
        if dependency_type == "requires_information":
            return (
                "refresh_evidence",
                reason or "Workflow dependency requires additional information before it can be reviewed confidently.",
                False,
            )
        if dependency_type == "requires_confirmation":
            return (
                "request_confirmation",
                reason or "Workflow dependency requires confirmation before it can be relied on.",
                True,
            )
        return (
            "review_dependency",
            reason or "Workflow dependency is active and should be reviewed before workflow progress is considered.",
            True,
        )

    def _collect_evidence_refs(
        self,
        *,
        observation: WorkflowStateObservation,
        blockers: list[dict[str, Any]],
        dependencies: list[dict[str, Any]],
        evidence_refs: list[WorkflowStateEvidenceRef | dict[str, Any] | str],
        memory_context: Any | None,
        reasoning_context: ReasoningContext | dict[str, Any] | None,
    ) -> list[WorkflowStateEvidenceRef]:
        refs: list[WorkflowStateEvidenceRef] = list(observation.evidence_refs)
        refs.extend(self._refs_from_any_list(evidence_refs, default_source_type="workflow_context"))
        refs.extend(self._refs_from_blockers(blockers))
        refs.extend(self._refs_from_dependencies(dependencies))
        refs.extend(self._refs_from_context_evidence(memory_context, source_type="memory_context"))
        refs.extend(self._refs_from_reasoning(reasoning_context))
        return self._deduplicate_refs(refs)

    def _refs_from_any_list(
        self,
        items: list[WorkflowStateEvidenceRef | dict[str, Any] | str],
        *,
        default_source_type: str,
    ) -> list[WorkflowStateEvidenceRef]:
        refs: list[WorkflowStateEvidenceRef] = []
        for item in items:
            ref = self._ref_from_any(item, default_source_type=default_source_type)
            if ref is not None:
                refs.append(ref)
        return refs

    def _refs_from_blockers(self, blockers: list[dict[str, Any]]) -> list[WorkflowStateEvidenceRef]:
        refs: list[WorkflowStateEvidenceRef] = []
        for blocker in blockers:
            blocker_id = self._clean_text(self._value(blocker, "blocker_id")) or "blocker:unknown"
            support_level = "conflicts" if self._clean_text(self._value(blocker, "blocker_type")) == "conflicting_evidence" else "supports"
            evidence_status = "conflicted" if support_level == "conflicts" else "needs_review"
            for ref_id in self._string_list(self._value(blocker, "evidence_refs")):
                refs.append(
                    self._evidence_ref(
                        source_type="workflow_blocker",
                        source_id=blocker_id,
                        stable_source_ref=ref_id,
                        supports=["recommendation", "blocker"],
                        support_level=support_level,
                        evidence_status=evidence_status,
                        confidence=self._float_value(self._value(blocker, "confidence"), default=0.7),
                    )
                )
        return refs

    def _refs_from_dependencies(self, dependencies: list[dict[str, Any]]) -> list[WorkflowStateEvidenceRef]:
        refs: list[WorkflowStateEvidenceRef] = []
        for dependency in dependencies:
            dependency_id = self._clean_text(self._value(dependency, "dependency_id")) or "dependency:unknown"
            status = self._clean_text(self._value(dependency, "status")) or "unknown"
            evidence_status = "active" if status == "active" else "needs_review"
            for ref_id in self._string_list(self._value(dependency, "evidence_refs")):
                refs.append(
                    self._evidence_ref(
                        source_type="workflow_dependency",
                        source_id=dependency_id,
                        stable_source_ref=ref_id,
                        supports=["recommendation", "dependency"],
                        support_level="supports",
                        evidence_status=evidence_status,
                        confidence=self._float_value(self._value(dependency, "confidence"), default=0.7),
                    )
                )
        return refs

    def _refs_from_reasoning(self, reasoning_context: ReasoningContext | dict[str, Any] | None) -> list[WorkflowStateEvidenceRef]:
        if reasoning_context is None:
            return []
        reasoning = reasoning_context if isinstance(reasoning_context, ReasoningContext) else ReasoningContext.model_validate(reasoning_context)
        return [
            self._evidence_ref(
                source_type=ref.source_type,
                source_id=ref.source_id,
                stable_source_ref=ref.evidence_ref_id,
                meeting_id=ref.meeting_id,
                supports=["recommendation", *ref.supported_claim_parts],
                support_level=ref.support_level,
                evidence_status=ref.evidence_status,
                confidence=ref.confidence,
            )
            for ref in reasoning.evidence_refs
        ]

    def _refs_from_context_evidence(self, context: Any | None, *, source_type: str) -> list[WorkflowStateEvidenceRef]:
        refs: list[WorkflowStateEvidenceRef] = []
        for evidence in self._list_value(context, "evidence"):
            source_id = self._clean_text(
                self._value(evidence, "evidence_id")
                or self._value(evidence, "source_id")
                or self._value(evidence, "segment_id")
            )
            if not source_id:
                continue
            refs.append(
                self._evidence_ref(
                    source_type=self._clean_text(self._value(evidence, "source_type")) or source_type,
                    source_id=source_id,
                    meeting_id=self._clean_text(self._value(evidence, "meeting_id")),
                    supports=["recommendation", *self._string_list(self._value(evidence, "supported_fields"))],
                    support_level="supports",
                    evidence_status=self._clean_text(self._value(evidence, "evidence_status")) or "unknown",
                    confidence=self._float_value(self._value(evidence, "confidence"), default=0.0),
                )
            )
        return refs

    def _ref_from_any(self, item: WorkflowStateEvidenceRef | dict[str, Any] | str, *, default_source_type: str) -> WorkflowStateEvidenceRef | None:
        if isinstance(item, WorkflowStateEvidenceRef):
            return item
        if isinstance(item, str):
            text = self._clean_text(item)
            if not text:
                return None
            return self._evidence_ref(
                source_type=default_source_type,
                source_id=text,
                stable_source_ref=text,
                supports=["recommendation"],
                support_level="supports",
                evidence_status="unknown",
                confidence=0.7,
            )
        source_id = self._clean_text(self._value(item, "source_id") or self._value(item, "evidence_ref_id"))
        if not source_id:
            return None
        return self._evidence_ref(
            source_type=self._clean_text(self._value(item, "source_type")) or default_source_type,
            source_id=source_id,
            stable_source_ref=self._clean_text(self._value(item, "evidence_ref_id")),
            meeting_id=self._clean_text(self._value(item, "meeting_id")),
            supports=self._string_list(self._value(item, "supports") or self._value(item, "supported_claim_parts")) or ["recommendation"],
            support_level=self._clean_text(self._value(item, "support_level")) or "supports",
            evidence_status=self._clean_text(self._value(item, "evidence_status")) or "unknown",
            confidence=self._float_value(self._value(item, "confidence"), default=0.0),
        )

    def _top_blocker(self, blockers: list[dict[str, Any]]) -> dict[str, Any] | None:
        active = [
            blocker
            for blocker in blockers
            if (self._clean_text(self._value(blocker, "status") or self._value(blocker, "blocker_state")) or "active")
            in {"active", "needs_review", "unknown"}
        ]
        if not active:
            return None
        return max(
            active,
            key=lambda item: (
                self._SEVERITY_RANK.get(self._clean_text(self._value(item, "severity")) or "unknown", 0),
                self._float_value(self._value(item, "confidence"), default=0.0),
            ),
        )

    def _top_dependency(self, dependencies: list[dict[str, Any]]) -> dict[str, Any] | None:
        active = [
            dependency
            for dependency in dependencies
            if (self._clean_text(self._value(dependency, "status")) or "active")
            in {"active", "blocked", "conflicted", "unknown"}
        ]
        if not active:
            return None
        return max(
            active,
            key=lambda item: self._float_value(self._value(item, "confidence"), default=0.0),
        )

    @staticmethod
    def _refs_need_refresh(refs: list[WorkflowStateEvidenceRef]) -> bool:
        return any(ref.evidence_status in {"expired", "unknown"} or ref.confidence < 0.55 for ref in refs)

    def _recommendation_confidence(
        self,
        *,
        observation: WorkflowStateObservation,
        refs: list[WorkflowStateEvidenceRef],
        recommendation_type: str,
        requires_confirmation: bool,
    ) -> float:
        confidence = min(observation.confidence, sum(ref.confidence for ref in refs) / len(refs))
        if recommendation_type != "no_action":
            confidence = min(confidence, 0.88)
        if requires_confirmation:
            confidence -= 0.1
        return self._float_value(confidence)

    def _recommendation_id(
        self,
        *,
        workflow_id: str,
        recommendation_type: str,
        reason: str,
        refs: list[WorkflowStateEvidenceRef],
    ) -> str:
        basis = {
            "workflow_id": workflow_id,
            "recommendation_type": recommendation_type,
            "reason": reason,
            "refs": [ref.evidence_ref_id for ref in refs],
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return f"wrec:{recommendation_type}:{digest}"

    def _evidence_ref(
        self,
        *,
        source_type: str,
        source_id: str,
        supports: list[str],
        support_level: str,
        confidence: float,
        evidence_status: str,
        meeting_id: str | None = None,
        stable_source_ref: str | None = None,
    ) -> WorkflowStateEvidenceRef:
        basis = {
            "stable_source_ref": stable_source_ref,
            "source_type": source_type,
            "source_id": source_id,
            "support_level": support_level,
            "supports": supports,
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return WorkflowStateEvidenceRef(
            evidence_ref_id=stable_source_ref or f"eref:{digest}",
            source_type=source_type,
            source_id=source_id,
            meeting_id=meeting_id,
            supports=supports,
            support_level=support_level,  # type: ignore[arg-type]
            evidence_status=evidence_status,  # type: ignore[arg-type]
            confidence=self._float_value(confidence),
        )

    @staticmethod
    def _observation(observation: WorkflowStateObservation | dict[str, Any] | None) -> WorkflowStateObservation | None:
        if observation is None:
            return None
        if isinstance(observation, WorkflowStateObservation):
            return observation
        try:
            return WorkflowStateObservation.model_validate(observation)
        except ValueError:
            return None

    @staticmethod
    def _value(item: Any, key: str) -> Any:
        if item is None:
            return None
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def _list_value(self, item: Any, key: str) -> list[Any]:
        value = self._value(item, key)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _float_value(value: Any, *, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _deduplicate_refs(refs: list[WorkflowStateEvidenceRef]) -> list[WorkflowStateEvidenceRef]:
        by_id: dict[str, WorkflowStateEvidenceRef] = {}
        for ref in refs:
            existing = by_id.get(ref.evidence_ref_id)
            if existing is None or ref.confidence > existing.confidence:
                by_id[ref.evidence_ref_id] = ref
        return list(by_id.values())


__all__ = ["WorkflowRecommendationBuilder"]
