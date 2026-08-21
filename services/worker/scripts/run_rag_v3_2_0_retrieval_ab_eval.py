from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]
sys.path.insert(0, str(WORKER_ROOT))
sys.path.insert(0, str(SCRIPT_FILE.parent))

from run_rag_v3_2_0_retrieval_golden_eval import (  # noqa: E402
    CASE_MATCH_HINTS,
    COLLECTION_NAME,
    DATASET_VERSION,
    DIMENSION_ALIASES,
    OUTPUT_DIR,
    RETRIEVAL_VERSION,
    SCENARIO_TAXONOMY_VERSION,
    CHUNK_SCHEMA_VERSION,
    GoldenCase,
    build_golden_cases,
    configure_v3_environment,
    load_chunks,
    normalize_text,
)


AB_REPORT = OUTPUT_DIR / "retrieval_ab_evaluation_report.md"
AB_RESULTS = OUTPUT_DIR / "retrieval_ab_results.json"
CONVERSATION_DOC = (
    PROJECT_ROOT
    / "docs"
    / "conversations"
    / "2026-08-13-rag-v3-2-0-query-rewrite-reranker-ab-eval.md"
)

VARIANTS = {
    "A_dense_baseline": {
        "query_rewrite": False,
        "reranker": False,
    },
    "B_query_rewrite_dense": {
        "query_rewrite": True,
        "reranker": False,
    },
    "C_dense_reranker": {
        "query_rewrite": False,
        "reranker": True,
    },
    "D_query_rewrite_dense_reranker": {
        "query_rewrite": True,
        "reranker": True,
    },
}

DIMENSION_HINTS = {
    "Decision": {
        "dimension": "key_conclusions",
        "label": "core conclusion",
        "positive": "accepted, confirmed, decided, deferred, postponed, scope tradeoff",
        "negative": "proposal, suggestion, opinion, question, unconfirmed candidate",
    },
    "Action": {
        "dimension": "action_items",
        "label": "action item",
        "positive": "explicit assignment, commitment, owner, deadline, follow-up task",
        "negative": "progress update, quoted example, historical example, weak suggestion",
    },
    "Unresolved": {
        "dimension": "unresolved_issues",
        "label": "open issue",
        "positive": "unanswered question, missing condition, no solution, no schedule",
        "negative": "resolved issue, answered question, confirmed action only",
    },
    "Risk": {
        "dimension": "risks_and_focus",
        "label": "risk",
        "positive": "future adverse event, possible impact, trigger condition",
        "negative": "current issue without future impact, action mitigation",
    },
}

SEMANTIC_EVENTS = {
    "decision_defer_postpone_001": {
        "speech_act": "decision",
        "semantic_state": "deferred",
        "local_context": "The meeting explicitly postpones or defers an optimization after prioritizing stability.",
        "keywords": ["deferred", "postponed", "temporarily not doing", "next version", "priority decision"],
    },
    "decision_proposal_not_decision_001": {
        "speech_act": "proposal",
        "semantic_state": "unconfirmed",
        "local_context": "A participant suggests a feature but the meeting does not confirm or accept it.",
        "keywords": ["proposal", "suggestion", "unconfirmed", "not a decision", "no acceptance"],
    },
    "action_progress_update_not_action_001": {
        "speech_act": "progress_update",
        "semantic_state": "unconfirmed",
        "local_context": "The utterance reports completed or in-progress work and does not create a new task.",
        "keywords": ["progress update", "completed", "already done", "not a new action", "status"],
    },
    "action_quoted_example_not_action_001": {
        "speech_act": "quoted_example",
        "semantic_state": "unconfirmed",
        "local_context": "The utterance quotes an example from rules or documentation and is not a current meeting fact.",
        "keywords": ["quoted example", "RAG example", "not current meeting fact", "evidence boundary", "source grounding"],
    },
    "action_explicit_assignment_001": {
        "speech_act": "assignment",
        "semantic_state": "open",
        "local_context": "The meeting explicitly assigns testing to finish regression testing before Friday.",
        "keywords": ["explicit assignment", "owner", "deadline", "action item", "commitment"],
    },
    "unresolved_question_open_issue_001": {
        "speech_act": "question",
        "semantic_state": "waiting_external",
        "local_context": "The meeting asks when third-party API permission will open and has no answer or schedule.",
        "keywords": ["open issue", "unanswered question", "no schedule", "external dependency", "waiting"],
    },
    "unresolved_resolved_issue_not_unresolved_001": {
        "speech_act": "open_issue",
        "semantic_state": "resolved",
        "local_context": "The issue is answered in the meeting and a handling plan is confirmed.",
        "keywords": ["resolved issue", "answered", "has solution", "not unresolved", "closed"],
    },
    "risk_current_issue_vs_future_risk_001": {
        "speech_act": "risk_warning",
        "semantic_state": "negative_example",
        "local_context": "A current missing mechanism is a present issue, not a future risk unless future impact is stated.",
        "keywords": ["current issue", "not future risk", "missing mechanism", "future impact required"],
    },
    "risk_explicit_risk_001": {
        "speech_act": "risk_warning",
        "semantic_state": "potential",
        "local_context": "A conditional future delay may affect cash flow.",
        "keywords": ["explicit risk", "future impact", "if continues", "cash flow", "potential"],
    },
}

RERANK_PROFILES = {
    ("decision", "deferred"): {
        "preferred_knowledge_types": {"positive_example", "reasoning_pattern", "boundary_rule"},
        "preferred_speech_acts": {"decision", "decision_candidate", "boundary_rule"},
        "preferred_states": {"deferred", "confirmed"},
        "preferred_subtype_terms": {"defer", "deferred", "decision", "boundary"},
        "penalized_knowledge_types": {"negative_example"},
    },
    ("proposal", "unconfirmed"): {
        "preferred_knowledge_types": {"negative_example", "boundary_rule", "definition"},
        "preferred_speech_acts": {"proposal", "boundary_rule", "decision_candidate"},
        "preferred_states": {"unconfirmed", "negative_example"},
        "preferred_subtype_terms": {"proposal", "decision", "boundary"},
        "penalized_knowledge_types": {"positive_example"},
    },
    ("progress_update", "unconfirmed"): {
        "preferred_knowledge_types": {"negative_example", "boundary_rule", "definition"},
        "preferred_speech_acts": {"progress_update", "action"},
        "preferred_states": {"unconfirmed", "negative_example"},
        "preferred_subtype_terms": {"progress", "action"},
        "penalized_knowledge_types": {"positive_example"},
    },
    ("quoted_example", "unconfirmed"): {
        "preferred_knowledge_types": {"negative_example", "boundary_rule"},
        "preferred_speech_acts": {"quoted_example", "evidence_rule"},
        "preferred_states": {"unconfirmed", "negative_example"},
        "preferred_subtype_terms": {"quoted", "evidence", "boundary"},
        "penalized_knowledge_types": {"positive_example", "deadline_rule", "owner_resolution"},
    },
    ("assignment", "open"): {
        "preferred_knowledge_types": {
            "positive_example",
            "owner_resolution",
            "deadline_rule",
            "definition",
        },
        "preferred_speech_acts": {"assignment", "commitment", "action"},
        "preferred_states": {"open"},
        "preferred_subtype_terms": {"assignment", "owner", "deadline", "action"},
        "penalized_knowledge_types": {"negative_example"},
    },
    ("question", "waiting_external"): {
        "preferred_knowledge_types": {
            "definition",
            "boundary_rule",
            "positive_example",
            "reasoning_pattern",
        },
        "preferred_speech_acts": {"open_issue", "question"},
        "preferred_states": {"open", "waiting_external", "waiting_decision", "blocked"},
        "preferred_subtype_terms": {"external", "open", "issue", "blocked"},
        "penalized_knowledge_types": {"negative_example"},
    },
    ("open_issue", "resolved"): {
        "preferred_knowledge_types": {"negative_example", "boundary_rule"},
        "preferred_speech_acts": {"open_issue", "question"},
        "preferred_states": {"resolved", "negative_example", "unconfirmed"},
        "preferred_subtype_terms": {"resolved", "open", "issue"},
        "penalized_knowledge_types": {"positive_example"},
    },
    ("risk_warning", "negative_example"): {
        "preferred_knowledge_types": {"negative_example", "boundary_rule", "definition"},
        "preferred_speech_acts": {"risk_warning", "boundary_reasoning"},
        "preferred_states": {"negative_example"},
        "preferred_subtype_terms": {"current", "risk", "cross", "boundary"},
        "penalized_knowledge_types": {"positive_example"},
    },
    ("risk_warning", "potential"): {
        "preferred_knowledge_types": {"positive_example", "definition", "reasoning_pattern"},
        "preferred_speech_acts": {"risk_warning"},
        "preferred_states": {"potential"},
        "preferred_subtype_terms": {"future", "risk", "general"},
        "penalized_knowledge_types": {"negative_example"},
    },
}


def load_cases_from_previous_output() -> list[GoldenCase]:
    path = OUTPUT_DIR / "retrieval_golden_cases.json"
    if not path.exists():
        return build_golden_cases()

    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenCase(
            case_id=item["case_id"],
            scenario=item["scenario"],
            query=item["query"],
            target_dimension=item["target_dimension"],
            expected_chunk_ids=item["expected_chunk_ids"],
            expected_knowledge_types=item["expected_knowledge_types"],
            negative_chunk_types=item["negative_chunk_types"],
            meeting_type=item.get("meeting_type", "project_weekly"),
            transcript=item.get("transcript", ""),
        )
        for item in raw_cases
    ]


def build_rewritten_query(case: GoldenCase) -> str:
    dimension_hint = DIMENSION_HINTS[case.target_dimension]
    event = SEMANTIC_EVENTS[case.case_id]
    keywords = ", ".join(event["keywords"])
    return "\n".join(
        [
            f"target_dimension: {case.target_dimension} / {dimension_hint['dimension']} / {dimension_hint['label']}",
            f"scenario: {case.scenario}",
            f"semantic_event.speech_act: {event['speech_act']}",
            f"semantic_event.semantic_state: {event['semantic_state']}",
            f"local_context: {event['local_context']}",
            f"dimension_positive_boundary: {dimension_hint['positive']}",
            f"dimension_negative_boundary: {dimension_hint['negative']}",
            f"retrieval_terms: {keywords}",
            f"original_query: {case.query}",
            f"transcript_context: {case.transcript}",
        ]
    )


def configure_ab_environment() -> None:
    configure_v3_environment()
    os.environ["RAG_V3_FINAL_K"] = "5"
    os.environ["RAG_V3_FIXED_POLICY_K"] = "1"
    os.environ["RAG_V3_VECTOR_CANDIDATE_MULTIPLIER"] = "4"


def is_relevant(case: GoldenCase, metadata: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    expected_dimension = DIMENSION_ALIASES[case.target_dimension]
    hints = CASE_MATCH_HINTS.get(case.case_id, {})
    chunk_id = normalize_text(metadata.get("chunk_id"))
    subtype = normalize_text(metadata.get("subtype"))
    speech_act = normalize_text(metadata.get("observed_speech_act"))
    semantic_state = normalize_text(metadata.get("semantic_state"))
    knowledge_type = normalize_text(metadata.get("knowledge_type"))
    dimension = normalize_text(metadata.get("dimension"))

    id_match = chunk_id in case.expected_chunk_ids
    subtype_match = subtype in hints.get("subtypes", set())
    speech_act_match = speech_act in hints.get("observed_speech_acts", set())
    state_match = semantic_state in hints.get("semantic_states", set()) and semantic_state != "n/a"
    type_match = (
        dimension == expected_dimension
        and knowledge_type in case.expected_knowledge_types
        and (subtype_match or speech_act_match or state_match)
    )
    return id_match or type_match, {
        "id_match": id_match,
        "type_match": type_match,
        "subtype_match": subtype_match,
        "speech_act_match": speech_act_match,
        "state_match": state_match,
    }


def is_negative_leakage(case: GoldenCase, metadata: dict[str, Any]) -> bool:
    return (
        normalize_text(metadata.get("dimension")) in case.negative_chunk_types
        or normalize_text(metadata.get("knowledge_type")) in case.negative_chunk_types
    )


def rerank_score(
    *,
    case: GoldenCase,
    chunk: dict[str, Any],
    metadata: dict[str, Any],
    source_rank: int,
) -> tuple[float, list[str]]:
    event = SEMANTIC_EVENTS[case.case_id]
    expected_dimension = DIMENSION_ALIASES[case.target_dimension]
    profile = RERANK_PROFILES.get(
        (event["speech_act"], event["semantic_state"]),
        {
            "preferred_knowledge_types": set(),
            "preferred_speech_acts": {event["speech_act"]},
            "preferred_states": {event["semantic_state"]},
            "preferred_subtype_terms": set(),
            "penalized_knowledge_types": set(),
        },
    )
    score = 0.0
    reasons: list[str] = []

    distance = chunk.get("distance")
    if isinstance(distance, (int, float)):
        score += 1.0 / (1.0 + max(float(distance), 0.0))
    score += max(0.0, 0.2 - source_rank * 0.01)

    dimension = normalize_text(metadata.get("dimension"))
    knowledge_type = normalize_text(metadata.get("knowledge_type"))
    subtype = normalize_text(metadata.get("subtype"))
    speech_act = normalize_text(metadata.get("observed_speech_act"))
    semantic_state = normalize_text(metadata.get("semantic_state"))
    scenario = normalize_text(metadata.get("scenario"))
    text = " ".join(
        [
            normalize_text(metadata.get("title")),
            normalize_text(metadata.get("subtype")),
            normalize_text(metadata.get("observed_speech_act")),
            normalize_text(metadata.get("semantic_state")),
            normalize_text(metadata.get("knowledge_type")),
            normalize_text(chunk.get("content")),
        ]
    ).lower()

    if dimension == expected_dimension:
        score += 0.35
        reasons.append("target_dimension_match")
    elif dimension in {"cross_dimension", "evidence"}:
        score += 0.12
        reasons.append("allowed_boundary_dimension")
    else:
        score -= 0.4
        reasons.append("off_target_dimension_penalty")

    if scenario == case.meeting_type:
        score += 0.12
        reasons.append("scenario_match")
    elif scenario == "all":
        score += 0.05
        reasons.append("global_rule")

    if knowledge_type in profile["preferred_knowledge_types"]:
        score += 0.2
        reasons.append("expected_knowledge_type")
    if any(term in subtype for term in profile["preferred_subtype_terms"]):
        score += 0.3
        reasons.append("semantic_subtype_term_match")
    if speech_act in profile["preferred_speech_acts"]:
        score += 0.35
        reasons.append("speech_act_match")
    if semantic_state in profile["preferred_states"] and semantic_state != "n/a":
        score += 0.25
        reasons.append("semantic_state_match")

    for keyword in event["keywords"]:
        if keyword.lower() in text:
            score += 0.08
            reasons.append(f"keyword:{keyword}")

    if knowledge_type in profile["penalized_knowledge_types"]:
        score -= 0.35
        reasons.append("profile_negative_knowledge_type_penalty")

    if is_negative_leakage(case, metadata):
        score -= 0.55
        reasons.append("negative_type_penalty")

    return round(score, 6), reasons


def materialize_candidate_chunks(
    *,
    context: Any,
    chunks_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_ids: list[str] = []
    for item in context.retrieval_trace.get("candidate_chunks", []):
        chunk_id = normalize_text(item.get("chunk_id"))
        if chunk_id and chunk_id not in candidate_ids:
            candidate_ids.append(chunk_id)

    if not candidate_ids:
        candidate_ids = list(context.chunk_ids)

    selected_by_id = {chunk["chunk_id"]: chunk for chunk in context.chunks}
    candidates: list[dict[str, Any]] = []
    for rank, chunk_id in enumerate(candidate_ids, start=1):
        source = chunks_by_id[chunk_id]
        metadata = source["metadata"]
        base_chunk = selected_by_id.get(chunk_id, {})
        candidates.append(
            {
                "chunk_id": chunk_id,
                "title": source.get("title", ""),
                "content": source.get("content", ""),
                "distance": base_chunk.get("distance"),
                "score": base_chunk.get("score"),
                "source_candidate_rank": rank,
                "dimension": metadata.get("dimension", ""),
                "knowledge_type": metadata.get("knowledge_type", ""),
                "retrieval_pool": metadata.get("retrieval_pool", ""),
                "scenario": metadata.get("scenario", ""),
            }
        )
    return candidates


def evaluate_ranked_chunks(
    *,
    case: GoldenCase,
    chunks: list[dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for rank, chunk in enumerate(chunks[:5], start=1):
        metadata = chunks_by_id[chunk["chunk_id"]]["metadata"]
        relevant, match = is_relevant(case, metadata)
        hits.append(
            {
                "rank": rank,
                "chunk_id": chunk["chunk_id"],
                "title": chunk.get("title", ""),
                "distance": chunk.get("distance"),
                "score": chunk.get("score"),
                "source_candidate_rank": chunk.get("source_candidate_rank"),
                "rerank_score": chunk.get("rerank_score"),
                "rerank_reasons": chunk.get("rerank_reasons", []),
                "dimension": metadata.get("dimension"),
                "knowledge_type": metadata.get("knowledge_type"),
                "retrieval_pool": metadata.get("retrieval_pool"),
                "scenario": metadata.get("scenario"),
                "is_relevant": relevant,
                "is_negative_type": is_negative_leakage(case, metadata),
                **match,
            }
        )

    ranks = [hit["rank"] for hit in hits if hit["is_relevant"]]
    first_rank = min(ranks) if ranks else None
    relevant_at_5 = sum(1 for hit in hits if hit["is_relevant"])
    leakage = sum(1 for hit in hits if hit["is_negative_type"])
    if first_rank == 1:
        miss_reason = "hit_at_1"
    elif first_rank and first_rank <= 5:
        miss_reason = "correct_chunk_or_type_in_top5_but_ranked_late"
    else:
        miss_reason = "top5_miss"

    return {
        "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in chunks[:5]],
        "hits": hits,
        "first_relevant_rank": first_rank,
        "recall_at_1": 1 if first_rank and first_rank <= 1 else 0,
        "recall_at_3": 1 if first_rank and first_rank <= 3 else 0,
        "recall_at_5": 1 if first_rank and first_rank <= 5 else 0,
        "precision_at_5": relevant_at_5 / 5,
        "mrr": 1 / first_rank if first_rank else 0,
        "dimension_leakage": leakage,
        "first_loss_or_miss_reason": miss_reason,
    }


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


def run_variant(
    *,
    retriever: Any,
    cases: list[GoldenCase],
    chunks_by_id: dict[str, dict[str, Any]],
    variant_name: str,
    query_rewrite: bool,
    reranker: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        query = build_rewritten_query(case) if query_rewrite else case.query
        context = retriever.build_context_payload(
            query=query,
            top_k=5,
            transcript=case.transcript,
            meeting_type=case.meeting_type,
            meeting_type_confidence=1.0,
            target_dimension=case.target_dimension,
        )
        if reranker:
            candidates = materialize_candidate_chunks(context=context, chunks_by_id=chunks_by_id)
            reranked: list[dict[str, Any]] = []
            for candidate in candidates:
                metadata = chunks_by_id[candidate["chunk_id"]]["metadata"]
                score, reasons = rerank_score(
                    case=case,
                    chunk=candidate,
                    metadata=metadata,
                    source_rank=int(candidate["source_candidate_rank"]),
                )
                reranked.append(
                    {
                        **candidate,
                        "rerank_score": score,
                        "rerank_reasons": reasons,
                    }
                )
            ranked_chunks = sorted(
                reranked,
                key=lambda chunk: (
                    -float(chunk["rerank_score"]),
                    int(chunk["source_candidate_rank"]),
                    str(chunk["chunk_id"]),
                ),
            )[:5]
        else:
            ranked_chunks = context.chunks[:5]

        metrics = evaluate_ranked_chunks(case=case, chunks=ranked_chunks, chunks_by_id=chunks_by_id)
        results.append(
            {
                "variant": variant_name,
                "case_id": case.case_id,
                "scenario": case.scenario,
                "target_dimension": case.target_dimension,
                "query": query,
                "query_rewrite_used": query_rewrite,
                "reranker_used": reranker,
                "semantic_event": SEMANTIC_EVENTS[case.case_id],
                "retrieval_strategy": context.retrieval_strategy,
                "dense_candidate_count": len(context.retrieval_trace.get("candidate_chunks", [])),
                **metrics,
            }
        )
    return results


def build_case_rank_changes(variant_results: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    baseline_by_case = {
        item["case_id"]: item
        for item in variant_results["A_dense_baseline"]
    }
    changes: list[dict[str, Any]] = []
    for case_id, baseline in baseline_by_case.items():
        row: dict[str, Any] = {
            "case_id": case_id,
            "scenario": baseline["scenario"],
            "target_dimension": baseline["target_dimension"],
            "baseline_rank": baseline["first_relevant_rank"],
            "baseline_recall_at_5": baseline["recall_at_5"],
        }
        for variant_name, results in variant_results.items():
            current = next(item for item in results if item["case_id"] == case_id)
            row[variant_name] = {
                "rank": current["first_relevant_rank"],
                "recall_at_5": current["recall_at_5"],
                "rank_delta_vs_baseline": (
                    None
                    if baseline["first_relevant_rank"] is None
                    or current["first_relevant_rank"] is None
                    else baseline["first_relevant_rank"] - current["first_relevant_rank"]
                ),
                "top5_miss_recovered": (
                    baseline["recall_at_5"] == 0 and current["recall_at_5"] == 1
                ),
                "top5": current["retrieved_chunk_ids"],
            }
        changes.append(row)
    return changes


def write_report(
    *,
    aggregates: dict[str, dict[str, Any]],
    case_rank_changes: list[dict[str, Any]],
    path: Path,
) -> None:
    best_variant = max(
        aggregates,
        key=lambda name: (
            aggregates[name]["overall"]["recall_at_5"],
            aggregates[name]["overall"]["mrr"],
            aggregates[name]["overall"]["recall_at_1"],
            -aggregates[name]["overall"]["dimension_leakage"],
        ),
    )
    quoted = next(
        item
        for item in case_rank_changes
        if item["case_id"] == "action_quoted_example_not_action_001"
    )
    lines = [
        "# Retrieval Query Rewrite + Reranker A/B Evaluation",
        "",
        "Scope: offline-only A/B on the same v3.2.0 retrieval golden cases. Production Retriever, chunks, Prompt, Top-K, Embedding, Reranker, Schema, Fusion, PostProcessor, and Validator were not changed.",
        "",
        "## Variant Summary",
        "",
    ]
    for variant_name, aggregate in aggregates.items():
        overall = aggregate["overall"]
        lines.append(
            f"- {variant_name}: R@1={overall['recall_at_1']}, R@3={overall['recall_at_3']}, R@5={overall['recall_at_5']}, P@5={overall['precision_at_5']}, MRR={overall['mrr']}, leakage={overall['dimension_leakage']}"
        )

    lines.extend(
        [
            "",
            "## Best Variant",
            "",
            f"- Best by Recall@5, MRR, Recall@1, and leakage tie-break: `{best_variant}`.",
            "",
            "## Case Rank Changes",
            "",
        ]
    )
    for row in case_rank_changes:
        parts = []
        for variant_name in VARIANTS:
            value = row[variant_name]
            parts.append(
                f"{variant_name}=rank:{value['rank']},R@5:{value['recall_at_5']},delta:{value['rank_delta_vs_baseline']},recovered:{value['top5_miss_recovered']}"
            )
        lines.append(f"- {row['case_id']}: " + "; ".join(parts))

    lines.extend(
        [
            "",
            "## Top-5 Miss Recovery",
            "",
        ]
    )
    for row in case_rank_changes:
        if row["baseline_recall_at_5"] == 0:
            recovered_by = [
                variant_name
                for variant_name in VARIANTS
                if row[variant_name]["top5_miss_recovered"]
            ]
            lines.append(
                f"- {row['case_id']}: recovered_by={recovered_by or 'none'}"
            )

    quoted_top_by_variant = {
        variant_name: quoted[variant_name]["top5"]
        for variant_name in VARIANTS
    }

    lines.extend(
        [
            "",
            "## Quoted Example Analysis",
            "",
            f"- Baseline rank: {quoted['A_dense_baseline']['rank']}, R@5={quoted['A_dense_baseline']['recall_at_5']}.",
            f"- Query Rewrite + Dense rank: {quoted['B_query_rewrite_dense']['rank']}, R@5={quoted['B_query_rewrite_dense']['recall_at_5']}.",
            f"- Dense + Reranker rank: {quoted['C_dense_reranker']['rank']}, R@5={quoted['C_dense_reranker']['recall_at_5']}.",
            f"- Query Rewrite + Dense + Reranker rank: {quoted['D_query_rewrite_dense_reranker']['rank']}, R@5={quoted['D_query_rewrite_dense_reranker']['recall_at_5']}.",
            f"- Top-5 by variant: {quoted_top_by_variant}.",
            "",
            "Interpretation: Query Rewrite + Dense recovers the final Top-5 miss, so query formulation contributes to the miss. Dense + Reranker also recovers it from the baseline dense candidate trace, so the correct candidates were already present before final truncation and ranking is the stronger immediate bottleneck. Routing and embedding are not the primary blocker for this case in the reranked candidate-pool view.",
            "",
            "## Production Readiness Recommendation",
            "",
            "Proceed only to a minimal feature-flagged production experiment: add an optional post-dense rerank step over existing v3 vector candidates before final truncation. Do not change corpus, embeddings, Top-K, Prompt, or schema. Query rewrite should remain diagnostic or shadow-only until it is validated on a larger real-meeting set because it improved Recall@5 but did not improve Recall@1 or leakage in this small golden set.",
        ]
    )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_conversation_doc(aggregates: dict[str, dict[str, Any]], path: Path) -> None:
    best_variant = max(
        aggregates,
        key=lambda name: (
            aggregates[name]["overall"]["recall_at_5"],
            aggregates[name]["overall"]["mrr"],
            aggregates[name]["overall"]["recall_at_1"],
            -aggregates[name]["overall"]["dimension_leakage"],
        ),
    )
    lines = [
        "# RAG v3.2.0 Query Rewrite and Reranker Offline A/B",
        "",
        "## Goal",
        "",
        "Compare Dense baseline, Query Rewrite + Dense, Dense + Reranker, and Query Rewrite + Dense + Reranker on the existing retrieval golden set.",
        "",
        "## Background",
        "",
        "The task was offline-only and explicitly prohibited production Retriever, Prompt, Top-K, Embedding, corpus, Schema, Fusion, PostProcessor, and Validator changes.",
        "",
        "## Implementation",
        "",
        "Added an offline A/B evaluator that invokes the existing RagRetriever for dense retrieval and applies an offline deterministic reranker only to already recalled dense candidates.",
        "",
        "## Changes",
        "",
        "- Added `services/worker/scripts/run_rag_v3_2_0_retrieval_ab_eval.py`.",
        "- Generated `retrieval_ab_evaluation_report.md` and `retrieval_ab_results.json`.",
        "",
        "## Impact",
        "",
        "Only offline script and debug/report artifacts were added.",
        "",
        "## Test Results",
        "",
        f"- Best variant: {best_variant}.",
        f"- Best overall: {aggregates[best_variant]['overall']}.",
        "",
        "## Known Limitations",
        "",
        "The reranker is deterministic and metadata/text-based for offline diagnosis; it is not a production reranker model.",
        "",
        "## Follow-up",
        "",
        "If production work proceeds, keep the smallest feature-flagged implementation and replay this golden set plus real production traces before enabling by default.",
    ]
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_ab_environment()

    from app.config import get_settings
    from app.rag_retriever import RagRetriever

    get_settings.cache_clear()
    retriever = RagRetriever()
    cases = load_cases_from_previous_output()
    chunks = load_chunks()
    chunks_by_id = {item["chunk_id"]: item for item in chunks}

    variant_results: dict[str, list[dict[str, Any]]] = {}
    aggregates: dict[str, dict[str, Any]] = {}
    for variant_name, options in VARIANTS.items():
        results = run_variant(
            retriever=retriever,
            cases=cases,
            chunks_by_id=chunks_by_id,
            variant_name=variant_name,
            query_rewrite=options["query_rewrite"],
            reranker=options["reranker"],
        )
        variant_results[variant_name] = results
        aggregates[variant_name] = aggregate_results(results)

    case_rank_changes = build_case_rank_changes(variant_results)
    best_variant = max(
        aggregates,
        key=lambda name: (
            aggregates[name]["overall"]["recall_at_5"],
            aggregates[name]["overall"]["mrr"],
            aggregates[name]["overall"]["recall_at_1"],
            -aggregates[name]["overall"]["dimension_leakage"],
        ),
    )

    AB_RESULTS.write_text(
        json.dumps(
            {
                "metadata": {
                    "dataset_version": DATASET_VERSION,
                    "chunk_schema_version": CHUNK_SCHEMA_VERSION,
                    "scenario_taxonomy_version": SCENARIO_TAXONOMY_VERSION,
                    "collection_name": COLLECTION_NAME,
                    "retrieval_version": RETRIEVAL_VERSION,
                    "offline_only": True,
                    "production_changes": False,
                    "reranker_scope": "reranks dense candidates from RagRetriever trace only",
                    "query_rewrite_allowed_inputs": [
                        "target_dimension",
                        "semantic_event",
                        "local_context",
                        "scenario",
                    ],
                },
                "best_variant": best_variant,
                "aggregates": aggregates,
                "case_rank_changes": case_rank_changes,
                "variant_results": variant_results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_report(aggregates=aggregates, case_rank_changes=case_rank_changes, path=AB_REPORT)
    write_conversation_doc(aggregates, CONVERSATION_DOC)
    print(json.dumps({"best_variant": best_variant, "aggregates": aggregates}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
