from __future__ import annotations

import difflib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

RAG_FILE = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "v3_2_0"
    / "meeting_analyst_rag_v3_2_0_frozen_candidate_500.jsonl"
)
MANIFEST_FILE = (
    PROJECT_ROOT / "data" / "rag" / "v3_2_0" / "manifest.v3_2_0.json"
)
OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "debug"
    / "rag_v3_2_0_retrieval_golden_eval"
)

DATASET_VERSION = "meeting_analyst_rag_v3_2_0"
CHUNK_SCHEMA_VERSION = "rag-chunk-v3.2"
SCENARIO_TAXONOMY_VERSION = "meeting-scenario-9-v1"
CORPUS_STATUS = "FROZEN_CANDIDATE"
COLLECTION_NAME = "meeting_analyst_rules_v3_2_0"
RETRIEVAL_VERSION = "meeting-rag-retrieval-v2"

REQUIRED_METADATA = [
    "runtime_layer",
    "layer",
    "scenario",
    "dimension",
    "knowledge_type",
    "priority",
    "version",
    "dataset_version",
    "chunk_schema_version",
    "expert_review_version",
    "status",
    "legacy_scenario",
    "scenario_scope",
    "scenario_taxonomy_version",
    "speech_act",
    "subtype",
    "confusable_with",
    "state",
    "evidence_requirement",
    "retrieval_pool",
    "retrieval_weight",
    "hard_rule",
    "retrieval_version",
    "taxonomy_version",
    "query_route",
    "selection_role",
    "speech_act_legacy",
    "state_legacy",
    "observed_speech_act",
    "target_dimension",
    "expected_label",
    "semantic_state",
    "metadata_contract_version",
    "metadata_routing_policy",
    "golden_usage",
    "source_origin",
    "corpus_status",
    "corpus_version",
]

ALLOWED_DIMENSIONS = {
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
    "cross_dimension",
    "evidence",
}
EXPECTED_LABEL_BY_KNOWLEDGE_TYPE = {
    "positive_example": "positive",
    "negative_example": "negative",
    "boundary_rule": "rule",
    "definition": "rule",
    "reasoning_pattern": "rule",
    "deadline_rule": "rule",
    "owner_resolution": "rule",
}
POOL_BY_RUNTIME = {
    "POLICY_FIXED": "fixed_policy",
    "RAG_DYNAMIC": "dynamic_boundary",
    "RAG_SCENARIO": "scenario_example",
}
DIMENSION_LABELS = {
    "meeting_agenda": ["会议议程"],
    "meeting_summary": ["会议总结"],
    "key_conclusions": ["核心结论", "结论"],
    "action_items": ["待办", "行动", "后续安排"],
    "unresolved_issues": ["遗留问题", "未闭环", "未解决"],
    "risks_and_focus": ["风险", "关注点"],
}
DIMENSION_ALIASES = {
    "Action": "action_items",
    "Decision": "key_conclusions",
    "Unresolved": "unresolved_issues",
    "Risk": "risks_and_focus",
}
CASE_MATCH_HINTS = {
    "decision_defer_postpone_001": {
        "subtypes": {"deferred_decision", "decision_boundary"},
        "observed_speech_acts": {"decision", "decision_candidate", "boundary_rule"},
        "semantic_states": {"deferred"},
    },
    "decision_proposal_not_decision_001": {
        "subtypes": {"proposal_boundary", "decision_boundary"},
        "observed_speech_acts": {"proposal", "boundary_rule", "decision_candidate"},
        "semantic_states": {"unconfirmed", "negative_example", "n/a"},
    },
    "action_progress_update_not_action_001": {
        "subtypes": {"progress_negative"},
        "observed_speech_acts": {"progress_update"},
        "semantic_states": {"unconfirmed", "negative_example", "n/a"},
    },
    "action_quoted_example_not_action_001": {
        "subtypes": {"quoted_negative", "evidence_boundary"},
        "observed_speech_acts": {"quoted_example", "evidence_rule"},
        "semantic_states": {"unconfirmed", "negative_example", "n/a"},
    },
    "action_explicit_assignment_001": {
        "subtypes": {"owner_resolution", "deadline_resolution", "assignment_positive"},
        "observed_speech_acts": {"assignment", "commitment", "action"},
        "semantic_states": {"open", "n/a"},
    },
    "unresolved_question_open_issue_001": {
        "subtypes": {"external_dependency", "open_issue_boundary", "blocked_issue"},
        "observed_speech_acts": {"open_issue", "question"},
        "semantic_states": {"open", "waiting_external", "waiting_decision", "blocked", "n/a"},
    },
    "unresolved_resolved_issue_not_unresolved_001": {
        "subtypes": {"resolved_issue", "open_issue_boundary"},
        "observed_speech_acts": {"open_issue", "question"},
        "semantic_states": {"resolved", "unconfirmed", "negative_example", "n/a"},
    },
    "risk_current_issue_vs_future_risk_001": {
        "subtypes": {"current_issue_negative", "general_risk", "cross_boundary"},
        "observed_speech_acts": {"risk_warning", "boundary_reasoning"},
        "semantic_states": {"negative_example", "n/a"},
    },
    "risk_explicit_risk_001": {
        "subtypes": {"future_risk", "general_risk"},
        "observed_speech_acts": {"risk_warning"},
        "semantic_states": {"potential", "n/a"},
    },
}


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    scenario: str
    query: str
    target_dimension: str
    expected_chunk_ids: list[str]
    expected_knowledge_types: list[str]
    negative_chunk_types: list[str]
    meeting_type: str = "project_weekly"
    transcript: str = ""


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalized_for_duplicate(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


def load_chunks() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with RAG_FILE.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            item["_line_number"] = line_number
            chunks.append(item)
    return chunks


def issue(kind: str, message: str) -> dict[str, str]:
    return {"kind": kind, "message": message}


def audit_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    issues_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    ids = [normalize_text(item.get("chunk_id")) for item in chunks]
    id_counts = Counter(ids)

    for item in chunks:
        chunk_id = normalize_text(item.get("chunk_id"))
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        content = normalize_text(item.get("content"))
        title = normalize_text(item.get("title"))

        if not chunk_id:
            chunk_id = f"line_{item.get('_line_number', 'unknown')}"
            issues_by_id[chunk_id].append(issue("invalid", "missing chunk_id"))
        if normalize_text(item.get("id")) != chunk_id:
            issues_by_id[chunk_id].append(issue("invalid", "id and chunk_id mismatch"))
        if id_counts[chunk_id] > 1:
            issues_by_id[chunk_id].append(issue("duplicate", "duplicate chunk_id"))
        if not title:
            issues_by_id[chunk_id].append(issue("invalid", "empty title"))
        if not content:
            issues_by_id[chunk_id].append(issue("invalid", "empty content"))
        if not isinstance(item.get("metadata"), dict):
            issues_by_id[chunk_id].append(issue("invalid", "metadata is not an object"))
            continue

        missing = [
            key
            for key in REQUIRED_METADATA
            if key not in metadata or normalize_text(metadata.get(key)) == ""
        ]
        allowed_empty = {"source_case", "failure_type", "expected_dimension", "correct_dimension_hint"}
        missing = [key for key in missing if key not in allowed_empty]
        if missing:
            issues_by_id[chunk_id].append(
                issue("metadata conflict", f"missing metadata: {', '.join(missing)}")
            )

        expected_versions = {
            "dataset_version": DATASET_VERSION,
            "chunk_schema_version": CHUNK_SCHEMA_VERSION,
            "scenario_taxonomy_version": SCENARIO_TAXONOMY_VERSION,
            "corpus_status": CORPUS_STATUS,
            "corpus_version": DATASET_VERSION,
            "retrieval_version": RETRIEVAL_VERSION,
            "metadata_contract_version": "meeting-rag-metadata-v3.2",
        }
        for key, expected_value in expected_versions.items():
            if normalize_text(metadata.get(key)) != expected_value:
                issues_by_id[chunk_id].append(
                    issue(
                        "metadata conflict",
                        f"{key}={metadata.get(key)!r}, expected {expected_value!r}",
                    )
                )

        dimension = normalize_text(metadata.get("dimension"))
        target_dimension = normalize_text(metadata.get("target_dimension"))
        if dimension not in ALLOWED_DIMENSIONS:
            issues_by_id[chunk_id].append(
                issue("dimension conflict", f"unknown dimension {dimension!r}")
            )
        if target_dimension != dimension:
            issues_by_id[chunk_id].append(
                issue(
                    "dimension conflict",
                    f"target_dimension {target_dimension!r} != dimension {dimension!r}",
                )
            )

        knowledge_type = normalize_text(metadata.get("knowledge_type"))
        expected_label = normalize_text(metadata.get("expected_label"))
        expected_label_from_type = EXPECTED_LABEL_BY_KNOWLEDGE_TYPE.get(knowledge_type)
        if expected_label_from_type and expected_label != expected_label_from_type:
            issues_by_id[chunk_id].append(
                issue(
                    "metadata conflict",
                    f"expected_label {expected_label!r} conflicts with {knowledge_type}",
                )
            )

        observed_speech_act = normalize_text(metadata.get("observed_speech_act"))
        if not observed_speech_act:
            issues_by_id[chunk_id].append(
                issue("metadata conflict", "observed_speech_act is empty")
            )
        semantic_state = normalize_text(metadata.get("semantic_state"))
        if not semantic_state:
            issues_by_id[chunk_id].append(
                issue("metadata conflict", "semantic_state is empty")
            )

        runtime_layer = normalize_text(metadata.get("runtime_layer"))
        retrieval_pool = normalize_text(metadata.get("retrieval_pool"))
        hard_rule = metadata.get("hard_rule")
        if runtime_layer == "POLICY_FIXED":
            if retrieval_pool != "fixed_policy" or hard_rule is not True:
                issues_by_id[chunk_id].append(
                    issue("metadata conflict", "fixed policy is not marked as fixed_policy hard_rule")
                )
        elif retrieval_pool == "fixed_policy" or hard_rule is True:
            issues_by_id[chunk_id].append(
                issue("metadata conflict", "non fixed runtime layer mixes fixed_policy markers")
            )

        if knowledge_type == "positive_example" and not re.search(r"正确分类|应提取|应进入|属于", content):
            issues_by_id[chunk_id].append(
                issue("warning", "positive example does not explicitly state the intended positive classification")
            )
        if knowledge_type == "negative_example" and "错误" not in content and "不得" not in content:
            issues_by_id[chunk_id].append(
                issue("warning", "negative example lacks explicit wrong/forbidden signal")
            )
        if knowledge_type == "negative_example" and expected_label != "negative":
            issues_by_id[chunk_id].append(
                issue("metadata conflict", "negative example is not expected_label=negative")
            )

        for other_dimension, labels in DIMENSION_LABELS.items():
            if other_dimension == dimension or dimension == "cross_dimension":
                continue
            if any(f"正确分类：{label}" in content for label in labels):
                issues_by_id[chunk_id].append(
                    issue(
                        "dimension conflict",
                        f"content names {other_dimension} as correct classification",
                    )
                )

    duplicate_pairs: list[dict[str, Any]] = []
    exact_seen: dict[str, str] = {}
    normalized = [(item["chunk_id"], normalized_for_duplicate(item.get("content", ""))) for item in chunks]
    for chunk_id, text in normalized:
        if text in exact_seen:
            duplicate_pairs.append(
                {"type": "exact", "chunk_ids": [exact_seen[text], chunk_id], "similarity": 1.0}
            )
            issues_by_id[chunk_id].append(issue("duplicate", f"exact duplicate of {exact_seen[text]}"))
        else:
            exact_seen[text] = chunk_id

    for left_index in range(len(normalized)):
        left_id, left_text = normalized[left_index]
        if len(left_text) < 24:
            continue
        for right_id, right_text in normalized[left_index + 1 :]:
            if len(right_text) < 24:
                continue
            ratio = difflib.SequenceMatcher(None, left_text, right_text).ratio()
            if ratio >= 0.94:
                duplicate_pairs.append(
                    {
                        "type": "near",
                        "chunk_ids": [left_id, right_id],
                        "similarity": round(ratio, 4),
                    }
                )
                issues_by_id[left_id].append(issue("duplicate", f"near duplicate of {right_id}"))
                issues_by_id[right_id].append(issue("duplicate", f"near duplicate of {left_id}"))

    invalid_ids = set()
    warning_ids = set()
    duplicate_ids = set()
    metadata_conflict_ids = set()
    dimension_conflict_ids = set()
    valid_ids = set()

    for item in chunks:
        chunk_id = item["chunk_id"]
        kinds = {entry["kind"] for entry in issues_by_id.get(chunk_id, [])}
        if "invalid" in kinds:
            invalid_ids.add(chunk_id)
        if "warning" in kinds:
            warning_ids.add(chunk_id)
        if "duplicate" in kinds:
            duplicate_ids.add(chunk_id)
        if "metadata conflict" in kinds:
            metadata_conflict_ids.add(chunk_id)
        if "dimension conflict" in kinds:
            dimension_conflict_ids.add(chunk_id)
        if not kinds:
            valid_ids.add(chunk_id)

    return {
        "summary": {
            "total": len(chunks),
            "valid": len(valid_ids),
            "warning": len(warning_ids),
            "invalid": len(invalid_ids),
            "duplicate": len(duplicate_ids),
            "metadata_conflict": len(metadata_conflict_ids),
            "dimension_conflict": len(dimension_conflict_ids),
        },
        "issues_by_id": dict(issues_by_id),
        "duplicate_pairs": duplicate_pairs,
        "field_distribution": {
            key: dict(Counter(normalize_text(item["metadata"].get(key)) for item in chunks))
            for key in [
                "dimension",
                "knowledge_type",
                "retrieval_pool",
                "runtime_layer",
                "expected_label",
                "observed_speech_act",
                "semantic_state",
                "scenario",
                "source_origin",
            ]
        },
    }


def build_golden_cases() -> list[GoldenCase]:
    return [
        GoldenCase(
            case_id="decision_defer_postpone_001",
            scenario="defer/postpone -> Decision",
            query="会议明确说这个优化先放一下，等主链稳定以后再做，应该归入哪个维度？",
            target_dimension="Decision",
            expected_chunk_ids=[
                "exp500_decision_pos_001",
                "exp_decision_001",
                "exp500_decision_pattern_001",
            ],
            expected_knowledge_types=["positive_example", "reasoning_pattern", "boundary_rule"],
            negative_chunk_types=["action_items", "unresolved_issues", "risks_and_focus"],
            transcript="这个优化先放一下，等主链稳定以后再做。",
        ),
        GoldenCase(
            case_id="decision_proposal_not_decision_001",
            scenario="proposal != Decision",
            query="有人只是建议增加导出功能，会议没有确认，不能当成核心结论。",
            target_dimension="Decision",
            expected_chunk_ids=[
                "negative_example_002",
                "v4_negative_example_001",
                "exp_decision_008",
                "boundary_rule_008",
            ],
            expected_knowledge_types=["negative_example", "boundary_rule", "definition"],
            negative_chunk_types=["positive_example"],
            transcript="是不是可以考虑增加导出功能？大家没有继续确认。",
        ),
        GoldenCase(
            case_id="action_progress_update_not_action_001",
            scenario="progress update != Action",
            query="研发同步接口联调已经完成百分之八十，这只是进展同步，不是新的待办。",
            target_dimension="Action",
            expected_chunk_ids=[
                "exp500_action_neg_001",
                "exp500_action_boundary_003",
                "definition_004",
            ],
            expected_knowledge_types=["negative_example", "boundary_rule", "definition"],
            negative_chunk_types=["positive_example"],
            transcript="接口联调已经完成百分之八十，今天只是同步进展。",
        ),
        GoldenCase(
            case_id="action_quoted_example_not_action_001",
            scenario="quoted example != Action",
            query="会议只是引用示例说研发周五前完成联调，不能把引用例子当成当前会议待办。",
            target_dimension="Action",
            expected_chunk_ids=[
                "boundary_rule_012",
                "v4_negative_example_006",
                "v4_negative_example_005",
            ],
            expected_knowledge_types=["negative_example", "boundary_rule"],
            negative_chunk_types=["positive_example", "deadline_rule", "owner_resolution"],
            transcript="这个就像规则里写的研发周五前完成联调，只是举例说明格式。",
        ),
        GoldenCase(
            case_id="action_explicit_assignment_001",
            scenario="explicit assignment -> Action",
            query="会议明确指派测试负责周五前完成回归测试，这是待办。",
            target_dimension="Action",
            expected_chunk_ids=[
                "definition_004",
                "v4_owner_resolution_002",
                "v4_owner_resolution_003",
                "v4_deadline_rule_001",
            ],
            expected_knowledge_types=["definition", "owner_resolution", "deadline_rule", "positive_example"],
            negative_chunk_types=["negative_example"],
            transcript="测试负责周五前完成回归测试。",
        ),
        GoldenCase(
            case_id="unresolved_question_open_issue_001",
            scenario="question/open issue -> Unresolved",
            query="会上提出第三方接口权限什么时候开放，但没有答案也没有排期，应归入遗留问题。",
            target_dimension="Unresolved",
            expected_chunk_ids=[
                "definition_005",
                "boundary_rule_009",
                "positive_example_012",
                "reasoning_pattern_001",
            ],
            expected_knowledge_types=["definition", "boundary_rule", "positive_example", "reasoning_pattern"],
            negative_chunk_types=["action_items", "risks_and_focus"],
            transcript="第三方接口权限什么时候开放？目前还没有明确时间，也没有替代方案。",
        ),
        GoldenCase(
            case_id="unresolved_resolved_issue_not_unresolved_001",
            scenario="resolved issue != Unresolved",
            query="问题在会上已经回答并形成处理方案，不应该继续作为遗留问题。",
            target_dimension="Unresolved",
            expected_chunk_ids=[
                "boundary_rule_007",
                "boundary_rule_009",
                "exp500_unresolved_neg_001",
            ],
            expected_knowledge_types=["boundary_rule", "negative_example"],
            negative_chunk_types=["positive_example"],
            transcript="权限问题已经确认由平台今天开通，方案也确定了。",
        ),
        GoldenCase(
            case_id="risk_current_issue_vs_future_risk_001",
            scenario="current issue vs future Risk",
            query="当前已经没有监控机制是现存问题，不要直接写成未来风险，除非说明后续影响。",
            target_dimension="Risk",
            expected_chunk_ids=[
                "boundary_rule_005",
                "definition_006",
                "v4_negative_example_007",
            ],
            expected_knowledge_types=["boundary_rule", "negative_example", "definition"],
            negative_chunk_types=["positive_example"],
            transcript="当前还没有差评监控机制，会议没有讨论未来影响。",
        ),
        GoldenCase(
            case_id="risk_explicit_risk_001",
            scenario="explicit Risk -> Risk",
            query="如果回款继续延期，会影响现金流，这是明确风险。",
            target_dimension="Risk",
            expected_chunk_ids=[
                "definition_006",
                "v4_positive_example_009",
                "positive_example_013",
            ],
            expected_knowledge_types=["definition", "positive_example", "reasoning_pattern"],
            negative_chunk_types=["unresolved_issues", "action_items"],
            meeting_type="management_decision",
            transcript="如果回款继续延期，会影响现金流。",
        ),
    ]


def configure_v3_environment() -> None:
    os.environ["MEETMIND_PROJECT_ROOT"] = str(PROJECT_ROOT)
    os.environ["RAG_V3_RETRIEVAL_ENABLED"] = "true"
    os.environ["RAG_LAYERED_RETRIEVAL_ENABLED"] = "false"
    os.environ["RAG_COLLECTION_NAME"] = COLLECTION_NAME
    os.environ["RAG_DATASET_VERSION"] = DATASET_VERSION
    os.environ["RAG_CHUNK_SCHEMA_VERSION"] = CHUNK_SCHEMA_VERSION
    os.environ["RAG_SCENARIO_TAXONOMY_VERSION"] = SCENARIO_TAXONOMY_VERSION
    os.environ["RAG_RETRIEVAL_VERSION"] = RETRIEVAL_VERSION
    os.environ["RAG_EMBEDDING_LOCAL_FILES_ONLY"] = "true"


def evaluate_retrieval(cases: list[GoldenCase], chunks_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    configure_v3_environment()
    from app.config import get_settings
    from app.rag_retriever import RagRetriever

    get_settings.cache_clear()
    retriever = RagRetriever()
    results: list[dict[str, Any]] = []

    for case in cases:
        context = retriever.build_context_payload(
            query=case.query,
            top_k=5,
            transcript=case.transcript,
            meeting_type=case.meeting_type,
            meeting_type_confidence=1.0,
            target_dimension=case.target_dimension,
        )
        expected_dimension = DIMENSION_ALIASES[case.target_dimension]
        hits: list[dict[str, Any]] = []
        for rank, chunk in enumerate(context.chunks, start=1):
            chunk_id = chunk["chunk_id"]
            metadata = chunks_by_id[chunk_id]["metadata"]
            is_expected_id = chunk_id in case.expected_chunk_ids
            match_hints = CASE_MATCH_HINTS.get(case.case_id, {})
            subtype_match = normalize_text(metadata.get("subtype")) in match_hints.get(
                "subtypes", set()
            )
            speech_act_match = normalize_text(
                metadata.get("observed_speech_act")
            ) in match_hints.get("observed_speech_acts", set())
            state_match = normalize_text(metadata.get("semantic_state")) in match_hints.get(
                "semantic_states", set()
            )
            is_expected_type = (
                metadata.get("dimension") == expected_dimension
                and metadata.get("knowledge_type") in case.expected_knowledge_types
                and (
                    subtype_match
                    or speech_act_match
                    or (
                        state_match
                        and normalize_text(metadata.get("semantic_state")) != "n/a"
                    )
                )
            )
            is_relevant = is_expected_id or is_expected_type
            is_negative_type = (
                metadata.get("dimension") in case.negative_chunk_types
                or metadata.get("knowledge_type") in case.negative_chunk_types
            )
            hits.append(
                {
                    "rank": rank,
                    "chunk_id": chunk_id,
                    "title": chunk.get("title", ""),
                    "distance": chunk.get("distance"),
                    "score": chunk.get("score"),
                    "dimension": metadata.get("dimension"),
                    "knowledge_type": metadata.get("knowledge_type"),
                    "retrieval_pool": metadata.get("retrieval_pool"),
                    "scenario": metadata.get("scenario"),
                    "is_expected_id": is_expected_id,
                    "is_expected_type": is_expected_type,
                    "is_relevant": is_relevant,
                    "is_negative_type": is_negative_type,
                }
            )
        ranks = [hit["rank"] for hit in hits if hit["is_relevant"]]
        expected_id_ranks = [hit["rank"] for hit in hits if hit["is_expected_id"]]
        relevant_at_5 = sum(1 for hit in hits[:5] if hit["is_relevant"])
        leakage = sum(1 for hit in hits[:5] if hit["is_negative_type"])
        first_rank = min(ranks) if ranks else None
        if first_rank == 1:
            miss_reason = "hit_at_1"
        elif first_rank and first_rank <= 5:
            miss_reason = "correct_chunk_or_type_in_top5_but_ranked_late"
        elif any(hit["dimension"] != expected_dimension for hit in hits[:3]):
            miss_reason = "dimension_leakage_or_boundary_chunk_dominates_top3"
        else:
            miss_reason = "dense_recall_miss_or_expected_type_not_retrieved"

        results.append(
            {
                "case_id": case.case_id,
                "scenario": case.scenario,
                "query": case.query,
                "target_dimension": case.target_dimension,
                "expected_dimension": expected_dimension,
                "expected_chunk_ids": case.expected_chunk_ids,
                "expected_knowledge_types": case.expected_knowledge_types,
                "negative_chunk_type": case.negative_chunk_types,
                "retrieval_strategy": context.retrieval_strategy,
                "retrieved_chunk_ids": context.chunk_ids,
                "hits": hits,
                "first_relevant_rank": first_rank,
                "expected_id_ranks": expected_id_ranks,
                "recall_at_1": 1 if first_rank and first_rank <= 1 else 0,
                "recall_at_3": 1 if first_rank and first_rank <= 3 else 0,
                "recall_at_5": 1 if first_rank and first_rank <= 5 else 0,
                "precision_at_5": relevant_at_5 / 5,
                "mrr": 1 / first_rank if first_rank else 0,
                "dimension_leakage": leakage,
                "first_loss_or_miss_reason": miss_reason,
                "retrieval_trace": context.retrieval_trace,
            }
        )

    return {"cases": [case.__dict__ for case in cases], "results": results}


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {
                "count": 0,
                "recall_at_1": 0,
                "recall_at_3": 0,
                "recall_at_5": 0,
                "precision_at_5": 0,
                "mrr": 0,
                "dimension_leakage": 0,
            }
        return {
            "count": len(items),
            "recall_at_1": round(sum(item["recall_at_1"] for item in items) / len(items), 4),
            "recall_at_3": round(sum(item["recall_at_3"] for item in items) / len(items), 4),
            "recall_at_5": round(sum(item["recall_at_5"] for item in items) / len(items), 4),
            "precision_at_5": round(sum(item["precision_at_5"] for item in items) / len(items), 4),
            "mrr": round(sum(item["mrr"] for item in items) / len(items), 4),
            "dimension_leakage": sum(item["dimension_leakage"] for item in items),
        }

    by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        by_dimension[item["target_dimension"]].append(item)
        by_scenario[item["scenario"]].append(item)

    return {
        "overall": summarize(results),
        "by_dimension": {key: summarize(value) for key, value in sorted(by_dimension.items())},
        "by_scenario": {key: summarize(value) for key, value in sorted(by_scenario.items())},
        "miss_reasons": dict(Counter(item["first_loss_or_miss_reason"] for item in results)),
    }


def write_audit_report(audit: dict[str, Any], path: Path) -> None:
    summary = audit["summary"]
    distributions = audit["field_distribution"]
    issues_by_id = audit["issues_by_id"]
    duplicate_pairs = audit["duplicate_pairs"]

    lines = [
        "# RAG Chunk Quality Audit Report",
        "",
        "Scope: `data/rag/v3_2_0/meeting_analyst_rag_v3_2_0_frozen_candidate_500.jsonl`.",
        "",
        "This audit is offline and read-only. Strict counters come from schema, metadata, version, dimension, and duplicate checks. Warning counters are heuristic content/label checks.",
        "",
        "## Required Counts",
        "",
        f"- total: {summary['total']}",
        f"- valid: {summary['valid']}",
        f"- warning: {summary['warning']}",
        f"- invalid: {summary['invalid']}",
        f"- duplicate: {summary['duplicate']}",
        f"- metadata conflict: {summary['metadata_conflict']}",
        f"- dimension conflict: {summary['dimension_conflict']}",
        "",
        "## Field Distribution",
        "",
    ]
    for field, counter in distributions.items():
        lines.append(f"### {field}")
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- `{key}`: {value}")
        lines.append("")

    lines.extend(["## Duplicate / Near-Duplicate Findings", ""])
    if duplicate_pairs:
        for pair in duplicate_pairs[:100]:
            lines.append(
                f"- {pair['type']} similarity={pair['similarity']}: {', '.join(pair['chunk_ids'])}"
            )
    else:
        lines.append("- None detected at exact match or near-duplicate threshold 0.94.")
    lines.append("")

    lines.extend(["## Invalid / Conflict / Warning Details", ""])
    problem_ids = sorted(chunk_id for chunk_id, entries in issues_by_id.items() if entries)
    if not problem_ids:
        lines.append("- None.")
    else:
        for chunk_id in problem_ids[:250]:
            entries = issues_by_id[chunk_id]
            lines.append(f"### {chunk_id}")
            for entry in entries:
                lines.append(f"- {entry['kind']}: {entry['message']}")
            lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_retrieval_report(aggregate: dict[str, Any], results: list[dict[str, Any]], path: Path) -> None:
    overall = aggregate["overall"]
    late = [
        item
        for item in results
        if item["first_loss_or_miss_reason"] == "correct_chunk_or_type_in_top5_but_ranked_late"
    ]
    misses = [item for item in results if not item["recall_at_5"]]
    leakage_cases = [item for item in results if item["dimension_leakage"] > 0]

    lines = [
        "# Retrieval Golden Evaluation Report",
        "",
        "Scope: v3.2.0 collection `meeting_analyst_rules_v3_2_0`, production `RagRetriever` with v3 routing enabled by environment for this offline run.",
        "",
        "## Overall",
        "",
        f"- cases: {overall['count']}",
        f"- Recall@1: {overall['recall_at_1']}",
        f"- Recall@3: {overall['recall_at_3']}",
        f"- Recall@5: {overall['recall_at_5']}",
        f"- Precision@5: {overall['precision_at_5']}",
        f"- MRR: {overall['mrr']}",
        f"- dimension leakage: {overall['dimension_leakage']}",
        "",
        "## Dimension Breakdown",
        "",
    ]
    for dimension, metrics in aggregate["by_dimension"].items():
        lines.append(
            f"- {dimension}: n={metrics['count']}, R@1={metrics['recall_at_1']}, R@3={metrics['recall_at_3']}, R@5={metrics['recall_at_5']}, P@5={metrics['precision_at_5']}, MRR={metrics['mrr']}, leakage={metrics['dimension_leakage']}"
        )
    lines.extend(["", "## Scenario Breakdown", ""])
    for scenario, metrics in aggregate["by_scenario"].items():
        lines.append(
            f"- {scenario}: n={metrics['count']}, R@1={metrics['recall_at_1']}, R@3={metrics['recall_at_3']}, R@5={metrics['recall_at_5']}, P@5={metrics['precision_at_5']}, MRR={metrics['mrr']}, leakage={metrics['dimension_leakage']}"
        )
    lines.extend(["", "## First-Loss / Miss Reasons", ""])
    for reason, count in sorted(aggregate["miss_reasons"].items()):
        lines.append(f"- {reason}: {count}")

    lines.extend(["", "## Case Results", ""])
    for item in results:
        top = ", ".join(
            f"{hit['rank']}.{hit['chunk_id']}[{hit['dimension']}/{hit['knowledge_type']}]"
            for hit in item["hits"]
        )
        lines.extend(
            [
                f"### {item['case_id']}",
                f"- scenario: {item['scenario']}",
                f"- target_dimension: {item['target_dimension']}",
                f"- first_relevant_rank: {item['first_relevant_rank']}",
                f"- expected_id_ranks: {item['expected_id_ranks']}",
                f"- first-loss / miss reason: {item['first_loss_or_miss_reason']}",
                f"- top5: {top}",
                "",
            ]
        )

    lines.extend(["## Reranker Evidence", ""])
    if late:
        lines.append(
            f"- {len(late)} cases retrieved a relevant chunk/type in Top-5 but not Rank-1, which is direct evidence of ranking loss."
        )
    else:
        lines.append("- No case showed relevant Top-5-but-late evidence.")
    if misses:
        lines.append(
            f"- {len(misses)} cases missed by Top-5; those indicate dense recall/query/routing issues before reranking."
        )
    else:
        lines.append("- No Top-5 misses in this golden set.")
    if leakage_cases:
        lines.append(
            f"- {len(leakage_cases)} cases had configured negative chunk type leakage in Top-5."
        )
    else:
        lines.append("- No configured negative chunk type leakage in Top-5.")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_conversation_doc(audit: dict[str, Any], aggregate: dict[str, Any], path: Path) -> None:
    lines = [
        "# RAG v3.2.0 Chunk Audit and Retrieval Golden Evaluation",
        "",
        "## Goal",
        "",
        "Run a read-only quality audit for the RAG v3.2.0 500-chunk corpus and evaluate current production RagRetriever behavior with an independent golden set.",
        "",
        "## Background",
        "",
        "The task explicitly forbids production Retriever, Prompt, RAG chunk, Top-K, Embedding, Reranker, and Schema changes. The implementation therefore adds only an offline evaluation script and generated debug/report artifacts.",
        "",
        "## Implementation",
        "",
        "The offline script reads the v3.2.0 JSONL and manifest, runs metadata, dimension, duplicate, provenance, fixed-policy, and heuristic semantic consistency checks, then invokes the existing RagRetriever under v3.2.0 environment settings for golden queries.",
        "",
        "## Changes",
        "",
        "- Added `services/worker/scripts/run_rag_v3_2_0_retrieval_golden_eval.py`.",
        "- Generated audit and retrieval evaluation artifacts under `data/debug/rag_v3_2_0_retrieval_golden_eval/`.",
        "",
        "## Impact",
        "",
        "Only offline evaluation script and debug/report artifacts. No production path or RAG source data was changed.",
        "",
        "## Test Results",
        "",
        f"- Chunk audit total={audit['summary']['total']}, valid={audit['summary']['valid']}, invalid={audit['summary']['invalid']}, warning={audit['summary']['warning']}.",
        f"- Retrieval golden overall R@1={aggregate['overall']['recall_at_1']}, R@3={aggregate['overall']['recall_at_3']}, R@5={aggregate['overall']['recall_at_5']}, P@5={aggregate['overall']['precision_at_5']}, MRR={aggregate['overall']['mrr']}.",
        "",
        "## Known Limitations",
        "",
        "Semantic consistency warnings are heuristic and do not replace manual per-chunk semantic review.",
        "",
        "## Follow-up",
        "",
        "If retrieval strategy changes in the next phase, use the Top-5-but-late evidence in golden results to separate reranker, query rewrite, and routing work.",
    ]
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    chunks = load_chunks()
    chunks_by_id = {item["chunk_id"]: item for item in chunks}

    audit = audit_chunks(chunks)
    cases = build_golden_cases()
    evaluation = evaluate_retrieval(cases, chunks_by_id)
    aggregate = aggregate_results(evaluation["results"])

    (OUTPUT_DIR / "retrieval_golden_cases.json").write_text(
        json.dumps(evaluation["cases"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "retrieval_golden_results.json").write_text(
        json.dumps(
            {
                "manifest": manifest,
                "audit_summary": audit["summary"],
                "aggregate": aggregate,
                "results": evaluation["results"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_audit_report(audit, OUTPUT_DIR / "rag_chunk_quality_audit_report.md")
    write_retrieval_report(
        aggregate,
        evaluation["results"],
        OUTPUT_DIR / "retrieval_golden_evaluation_report.md",
    )
    write_conversation_doc(
        audit,
        aggregate,
        PROJECT_ROOT
        / "docs"
        / "conversations"
        / "2026-08-13-rag-v3-2-0-chunk-audit-retrieval-golden-eval.md",
    )

    print(json.dumps({"audit": audit["summary"], "retrieval": aggregate["overall"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
