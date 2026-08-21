from __future__ import annotations

import hashlib
import json
from typing import Any

from app.reasoning_evidence_graph import ReasoningEvidenceGraph
from app.reasoning_engine import EvidenceRef as ReasoningEvidenceRef
from app.reasoning_engine import ReasoningContext
from app.workflow_state import (
    WORKFLOW_STATES_BY_TYPE,
    WorkflowStateEvidenceRef,
    WorkflowStateObservation,
    WorkflowStateTransition,
    WorkflowTransitionType,
)


class WorkflowStateObservationBuilder:
    _PROJECT_RANK = {
        "requirements_pending": 0,
        "requirements_confirmed": 1,
        "development_in_progress": 2,
        "testing_in_progress": 3,
        "verification_failed": 3,
        "ready_for_release": 4,
        "released": 5,
        "blocked": 2,
    }
    _ISSUE_RANK = {
        "reported": 0,
        "investigating": 1,
        "root_cause_found": 2,
        "fix_in_progress": 3,
        "resolved": 4,
        "verified": 5,
    }
    _FOLLOW_UP_RANK = {
        "action_created": 0,
        "owner_confirmed": 1,
        "pending": 1,
        "in_progress": 2,
        "completed_candidate": 3,
        "needs_review": 1,
    }

    def build(
        self,
        *,
        workflow_context: dict[str, Any],
        memory_context: Any | None = None,
        responsibility_context: Any | None = None,
        reasoning_context: ReasoningContext | dict[str, Any] | None = None,
        evidence_graph: ReasoningEvidenceGraph | dict[str, Any] | None = None,
    ) -> WorkflowStateObservation | None:
        workflow_id = self._clean_text(self._value(workflow_context, "workflow_id"))
        workflow_type = self._clean_text(self._value(workflow_context, "workflow_type"))
        if not workflow_id or workflow_type not in WORKFLOW_STATES_BY_TYPE:
            return None

        refs = self._collect_evidence_refs(
            workflow_context=workflow_context,
            memory_context=memory_context,
            responsibility_context=responsibility_context,
            reasoning_context=reasoning_context,
            evidence_graph=evidence_graph,
        )
        if not refs or not any(ref.support_level == "supports" for ref in refs):
            return None

        previous_state = self._previous_state(workflow_context=workflow_context, workflow_type=workflow_type)
        state_signals = self._state_signals(
            workflow_type=workflow_type,
            workflow_context=workflow_context,
            memory_context=memory_context,
            responsibility_context=responsibility_context,
            reasoning_context=reasoning_context,
            evidence_graph=evidence_graph,
        )
        if not state_signals:
            return None

        observed_state = self._choose_state(
            workflow_type=workflow_type,
            state_signals=state_signals,
            previous_state=previous_state,
            has_blocker=self._has_blocker(workflow_context),
        )
        if observed_state is None:
            return None

        requires_confirmation = self._requires_confirmation(refs=refs, state_signals=state_signals)
        transition_type = self._transition_type(
            workflow_type=workflow_type,
            previous_state=previous_state,
            observed_state=observed_state,
            requires_confirmation=requires_confirmation,
        )
        confidence = self._observation_confidence(refs=refs, state_signals=state_signals, requires_confirmation=requires_confirmation)

        return WorkflowStateObservation(
            workflow_id=workflow_id,
            workflow_type=workflow_type,  # type: ignore[arg-type]
            observed_state=observed_state,  # type: ignore[arg-type]
            previous_state=previous_state,  # type: ignore[arg-type]
            transition=WorkflowStateTransition(
                from_state=previous_state,  # type: ignore[arg-type]
                to_state=observed_state,  # type: ignore[arg-type]
                transition_type=transition_type,
                reason=self._transition_reason(transition_type=transition_type),
            ),
            evidence_refs=refs,
            confidence=confidence,
            requires_confirmation=requires_confirmation,
        )

    def _collect_evidence_refs(
        self,
        *,
        workflow_context: dict[str, Any],
        memory_context: Any | None,
        responsibility_context: Any | None,
        reasoning_context: ReasoningContext | dict[str, Any] | None,
        evidence_graph: ReasoningEvidenceGraph | dict[str, Any] | None,
    ) -> list[WorkflowStateEvidenceRef]:
        refs: list[WorkflowStateEvidenceRef] = []
        for item in self._list_value(workflow_context, "evidence_refs"):
            ref = self._ref_from_any(item, default_source_type="workflow_context")
            if ref is not None:
                refs.append(ref)
        for item in self._list_value(workflow_context, "states"):
            for ref_id in self._string_list(self._value(item, "evidence_refs")):
                refs.append(
                    self._evidence_ref(
                        source_type="workflow_state",
                        source_id=self._clean_text(self._value(item, "state_id")) or ref_id,
                        stable_source_ref=ref_id,
                        supports=["observed_state"],
                        support_level="supports",
                        confidence=self._float_value(self._value(item, "confidence"), default=0.7),
                        evidence_status="active",
                    )
                )
        refs.extend(self._refs_from_reasoning(reasoning_context))
        refs.extend(self._refs_from_evidence_graph(evidence_graph))
        refs.extend(self._refs_from_context_evidence(memory_context, source_type="memory_context"))
        refs.extend(self._refs_from_context_evidence(responsibility_context, source_type="responsibility_context"))
        return self._deduplicate_refs(refs)

    def _refs_from_reasoning(self, reasoning_context: ReasoningContext | dict[str, Any] | None) -> list[WorkflowStateEvidenceRef]:
        if reasoning_context is None:
            return []
        reasoning = reasoning_context if isinstance(reasoning_context, ReasoningContext) else ReasoningContext.model_validate(reasoning_context)
        return [self._ref_from_reasoning_ref(ref) for ref in reasoning.evidence_refs]

    def _ref_from_reasoning_ref(self, ref: ReasoningEvidenceRef) -> WorkflowStateEvidenceRef:
        return self._evidence_ref(
            source_type=ref.source_type,
            source_id=ref.source_id,
            stable_source_ref=ref.evidence_ref_id,
            meeting_id=ref.meeting_id,
            supports=["observed_state", *ref.supported_claim_parts],
            support_level=ref.support_level,
            evidence_status=ref.evidence_status,
            confidence=ref.confidence,
        )

    def _refs_from_evidence_graph(self, evidence_graph: ReasoningEvidenceGraph | dict[str, Any] | None) -> list[WorkflowStateEvidenceRef]:
        if evidence_graph is None:
            return []
        graph = evidence_graph if isinstance(evidence_graph, ReasoningEvidenceGraph) else ReasoningEvidenceGraph.model_validate(evidence_graph)
        nodes = {node.node_id: node for node in graph.nodes}
        refs: list[WorkflowStateEvidenceRef] = []
        for edge in graph.edges:
            if edge.to_node_id != graph.claim_node_id or edge.edge_type == "relates_to":
                continue
            node = nodes.get(edge.from_node_id)
            if node is None:
                continue
            refs.append(
                self._evidence_ref(
                    source_type=f"evidence_graph:{node.node_type}",
                    source_id=node.source_id,
                    stable_source_ref=f"{graph.graph_id}:{edge.from_node_id}:{edge.edge_type}",
                    supports=["observed_state"],
                    support_level=edge.edge_type,
                    confidence=min(node.confidence, edge.confidence),
                    evidence_status="unknown",
                )
            )
        return refs

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
                    supports=["observed_state", *self._string_list(self._value(evidence, "supported_fields"))],
                    support_level="supports",
                    confidence=self._float_value(self._value(evidence, "confidence"), default=0.0),
                    evidence_status="unknown",
                )
            )
        return refs

    def _state_signals(
        self,
        *,
        workflow_type: str,
        workflow_context: dict[str, Any],
        memory_context: Any | None,
        responsibility_context: Any | None,
        reasoning_context: ReasoningContext | dict[str, Any] | None,
        evidence_graph: ReasoningEvidenceGraph | dict[str, Any] | None,
    ) -> list[tuple[str, float]]:
        signals: list[tuple[str, float]] = []
        explicit = self._clean_text(self._value(workflow_context, "observed_state"))
        if self._state_allowed(workflow_type, explicit):
            signals.append((explicit, 0.95))
        for item in self._list_value(workflow_context, "states"):
            value = self._clean_text(self._value(item, "state_value") or self._value(item, "observed_state"))
            if self._state_allowed(workflow_type, value):
                signals.append((value, self._float_value(self._value(item, "confidence"), default=0.75)))
        for item in [workflow_context, memory_context, responsibility_context, reasoning_context]:
            signals.extend(self._signals_from_text(workflow_type=workflow_type, text=self._text_blob(item), confidence=self._confidence_value(item)))
        if evidence_graph is not None:
            graph = evidence_graph if isinstance(evidence_graph, ReasoningEvidenceGraph) else ReasoningEvidenceGraph.model_validate(evidence_graph)
            signals.extend(
                self._signals_from_text(
                    workflow_type=workflow_type,
                    text=" ".join(node.content for node in graph.nodes),
                    confidence=graph.confidence,
                )
            )
        return signals

    def _signals_from_text(self, *, workflow_type: str, text: str, confidence: float) -> list[tuple[str, float]]:
        normalized = text.lower()
        if not normalized:
            return []
        rules = {
            "project_delivery": [
                ("verification_failed", ("verification failed", "test failed", "tests failed", "qa failed")),
                ("released", ("released", "shipped")),
                ("ready_for_release", ("ready for release", "ready to release", "release ready")),
                ("testing_in_progress", ("testing", "test in progress", "qa")),
                ("development_in_progress", ("development", "implement", "implementation", "fix in progress")),
                ("requirements_confirmed", ("requirements confirmed", "requirement confirmed", "approved requirement")),
                ("requirements_pending", ("requirements pending", "pending requirements")),
                ("blocked", ("blocked", "blocking", "blocker")),
            ],
            "issue_resolution": [
                ("verified", ("verified", "verification passed")),
                ("resolved", ("resolved", "fixed")),
                ("fix_in_progress", ("fix in progress", "fixing", "implementing fix")),
                ("root_cause_found", ("root cause",)),
                ("investigating", ("investigating", "diagnosing")),
                ("reported", ("reported", "issue reported")),
            ],
            "meeting_follow_up": [
                ("completed_candidate", ("completed", "done")),
                ("in_progress", ("in progress", "working on")),
                ("owner_confirmed", ("owner confirmed", "confirmed owner", "owner is")),
                ("action_created", ("action created", "created action", "new action")),
                ("needs_review", ("needs review", "review required")),
                ("pending", ("pending", "waiting")),
            ],
        }
        result: list[tuple[str, float]] = []
        for state, keywords in rules[workflow_type]:
            if any(keyword in normalized for keyword in keywords):
                result.append((state, confidence))
        return result

    def _choose_state(
        self,
        *,
        workflow_type: str,
        state_signals: list[tuple[str, float]],
        previous_state: str | None,
        has_blocker: bool,
    ) -> str | None:
        if workflow_type == "project_delivery" and has_blocker:
            return "blocked"
        if workflow_type == "meeting_follow_up" and self._has_conflicting_signals(state_signals):
            return "needs_review"
        if workflow_type == "project_delivery" and self._has_conflicting_signals(state_signals):
            return "blocked"

        rank = self._rank_for(workflow_type)
        best_state, _ = max(
            state_signals,
            key=lambda item: (item[1], rank.get(item[0], -1)),
        )
        if previous_state and best_state == "blocked" and workflow_type != "project_delivery":
            return previous_state
        return best_state

    def _previous_state(self, *, workflow_context: dict[str, Any], workflow_type: str) -> str | None:
        explicit = self._clean_text(self._value(workflow_context, "previous_state"))
        if self._state_allowed(workflow_type, explicit):
            return explicit
        for item in reversed(self._list_value(workflow_context, "states")):
            value = self._clean_text(self._value(item, "previous_state") or self._value(item, "previous_state_value"))
            if self._state_allowed(workflow_type, value):
                return value
        states = self._list_value(workflow_context, "states")
        if len(states) >= 2:
            value = self._clean_text(self._value(states[-2], "state_value"))
            if self._state_allowed(workflow_type, value):
                return value
        return None

    def _transition_type(
        self,
        *,
        workflow_type: str,
        previous_state: str | None,
        observed_state: str,
        requires_confirmation: bool,
    ) -> WorkflowTransitionType:
        if requires_confirmation:
            return "requires_confirmation"
        if previous_state is None:
            return "no_previous_state"
        if previous_state == observed_state:
            return "unchanged"
        if observed_state == "blocked":
            return "blocked"
        if observed_state == "verification_failed":
            return "failed"
        rank = self._rank_for(workflow_type)
        if observed_state in rank and previous_state in rank:
            return "forward" if rank[observed_state] > rank[previous_state] else "backward"
        return "unknown"

    @staticmethod
    def _transition_reason(*, transition_type: str) -> str:
        return {
            "no_previous_state": "No previous workflow state was available for comparison.",
            "unchanged": "Observed evidence supports the same workflow state.",
            "forward": "Observed evidence indicates forward workflow progress.",
            "backward": "Observed evidence appears earlier than the previous workflow state.",
            "blocked": "Observed evidence indicates a blocking condition.",
            "failed": "Observed evidence indicates verification failure.",
            "requires_confirmation": "Observed evidence is conflicted or reviewable and requires confirmation.",
            "unknown": "Observed evidence supports a state change but transition direction is unknown.",
        }[transition_type]

    def _requires_confirmation(self, *, refs: list[WorkflowStateEvidenceRef], state_signals: list[tuple[str, float]]) -> bool:
        if any(ref.support_level == "conflicts" or ref.evidence_status in {"conflicted", "needs_review", "shadow_only", "expired", "unknown"} for ref in refs):
            return True
        if any(ref.confidence < 0.75 for ref in refs):
            return True
        return self._has_conflicting_signals(state_signals)

    def _has_conflicting_signals(self, state_signals: list[tuple[str, float]]) -> bool:
        confident_states = {state for state, confidence in state_signals if confidence >= 0.65}
        if len(confident_states) < 2:
            return False
        terminal = {"released", "verified", "completed_candidate", "resolved", "ready_for_release"}
        early = {"requirements_pending", "reported", "action_created", "pending", "needs_review"}
        return bool(confident_states & terminal and confident_states & early)

    def _observation_confidence(
        self,
        *,
        refs: list[WorkflowStateEvidenceRef],
        state_signals: list[tuple[str, float]],
        requires_confirmation: bool,
    ) -> float:
        ref_score = sum(ref.confidence for ref in refs) / len(refs)
        signal_score = sum(confidence for _, confidence in state_signals) / len(state_signals)
        confidence = min(ref_score, signal_score)
        if requires_confirmation:
            confidence -= 0.18
        return self._float_value(confidence)

    def _ref_from_any(self, item: Any, *, default_source_type: str) -> WorkflowStateEvidenceRef | None:
        source_id = self._clean_text(self._value(item, "source_id") or self._value(item, "evidence_ref_id"))
        if not source_id:
            return None
        return self._evidence_ref(
            source_type=self._clean_text(self._value(item, "source_type")) or default_source_type,
            source_id=source_id,
            stable_source_ref=self._clean_text(self._value(item, "evidence_ref_id")),
            meeting_id=self._clean_text(self._value(item, "meeting_id")),
            supports=self._string_list(self._value(item, "supports") or self._value(item, "supported_claim_parts")) or ["observed_state"],
            support_level=self._clean_text(self._value(item, "support_level")) or "supports",
            evidence_status=self._clean_text(self._value(item, "evidence_status")) or "unknown",
            confidence=self._float_value(self._value(item, "confidence"), default=0.0),
        )

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

    def _rank_for(self, workflow_type: str) -> dict[str, int]:
        if workflow_type == "issue_resolution":
            return self._ISSUE_RANK
        if workflow_type == "meeting_follow_up":
            return self._FOLLOW_UP_RANK
        return self._PROJECT_RANK

    def _has_blocker(self, workflow_context: dict[str, Any]) -> bool:
        for blocker in self._list_value(workflow_context, "blockers"):
            status = self._clean_text(self._value(blocker, "status") or self._value(blocker, "blocker_state"))
            if status in {None, "active", "needs_review"}:
                return True
        return False

    @staticmethod
    def _state_allowed(workflow_type: str, state: str | None) -> bool:
        return bool(state and state in WORKFLOW_STATES_BY_TYPE.get(workflow_type, ()))

    def _text_blob(self, item: Any) -> str:
        if item is None:
            return ""
        if isinstance(item, (str, int, float, bool)):
            return str(item)
        if isinstance(item, dict):
            return " ".join(self._text_blob(value) for value in item.values())
        if isinstance(item, list):
            return " ".join(self._text_blob(value) for value in item)
        if hasattr(item, "model_dump"):
            return self._text_blob(item.model_dump(mode="json"))
        return str(item)

    def _confidence_value(self, item: Any) -> float:
        value = self._value(item, "confidence")
        return self._float_value(value, default=0.7)

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


__all__ = ["WorkflowStateObservationBuilder"]
