from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

for path in (PROJECT_ROOT, WORKER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


OUTPUT_DIR = PROJECT_ROOT / "data" / "debug" / "fixed_policy_merge_ab"
RESULTS_FILE = PROJECT_ROOT / "fixed_policy_merge_ab_results.json"
REPORT_FILE = PROJECT_ROOT / "fixed_policy_merge_ab_report.md"

STRATEGIES = {
    "A_fixed_policy_first_reranked_dense": "fixed_policy first + reranked dense",
    "B_reranked_dense_first_fixed_policy": "reranked dense first + fixed_policy",
    "C_unified_score_merge": "fixed_policy and dense unified score merge",
    "D_reserved_slot_max1_fixed_policy": "Top-5 reserves at most 1 fixed_policy slot, dense fills the rest",
}


def configure_environment() -> None:
    os.environ["RAG_V3_RETRIEVAL_ENABLED"] = "true"
    os.environ["RAG_RERANKER_ENABLED"] = "true"
    os.environ["RAG_COLLECTION_NAME"] = "meeting_analyst_rules_v3_2_0"
    os.environ["RAG_DATASET_VERSION"] = "meeting_analyst_rag_v3_2_0"
    os.environ["RAG_CHUNK_SCHEMA_VERSION"] = "rag-chunk-v3.2"
    os.environ["RAG_SCENARIO_TAXONOMY_VERSION"] = "meeting-scenario-9-v1"
    os.environ["RAG_RETRIEVAL_VERSION"] = "meeting-rag-retrieval-v2"
    os.environ["RAG_EMBEDDING_LOCAL_FILES_ONLY"] = "true"
    os.environ["RAG_LAYERED_RETRIEVAL_ENABLED"] = "false"


def install_merge_strategy(strategy: str):
    from app.rag_retriever import RagRetriever

    original = RagRetriever._deduplicate

    def patched(self, chunks):
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id", ""))
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            unique.append(chunk)

        fixed = [
            chunk
            for chunk in unique
            if chunk.get("retrieval_pool") == "fixed_policy"
        ]
        dense = [
            chunk
            for chunk in unique
            if chunk.get("retrieval_pool") != "fixed_policy"
        ]

        if strategy == "A_fixed_policy_first_reranked_dense":
            return fixed + dense
        if strategy == "B_reranked_dense_first_fixed_policy":
            return dense + fixed
        if strategy == "C_unified_score_merge":
            return sorted(
                unique,
                key=lambda chunk: (
                    -float(
                        chunk.get("rerank_score")
                        if chunk.get("rerank_score") is not None
                        else chunk.get("score")
                        or 0.0
                    ),
                    str(chunk.get("chunk_id", "")),
                ),
            )
        if strategy == "D_reserved_slot_max1_fixed_policy":
            return fixed[:1] + dense + fixed[1:]

        return unique

    RagRetriever._deduplicate = patched
    return original


def restore_merge_strategy(original) -> None:
    from app.rag_retriever import RagRetriever

    RagRetriever._deduplicate = original


def fixed_policy_ranks(trace: dict[str, Any]) -> list[dict[str, Any]]:
    ranks: list[dict[str, Any]] = []
    for rank, chunk in enumerate(
        trace.get("final_selected_chunks") or [],
        start=1,
    ):
        if chunk.get("retrieval_pool") == "fixed_policy":
            ranks.append(
                {
                    "rank": rank,
                    "chunk_id": chunk.get("chunk_id"),
                    "target_dimension": trace.get("target_dimension"),
                }
            )
    return ranks


def selected_chunks_by_dimension(rag_trace: dict[str, Any]) -> dict[str, Any]:
    dimension_traces = rag_trace.get("dimension_traces") or {}
    output: dict[str, Any] = {}
    for dimension, trace in dimension_traces.items():
        output[dimension] = {
            "chunk_ids": trace.get("final_selected_chunk_ids") or [],
            "fixed_policy_ranks": fixed_policy_ranks(trace),
            "final_selected_chunks": trace.get("final_selected_chunks") or [],
            "candidate_chunks": trace.get("candidate_chunks") or [],
        }
    return output


def result_counts(result: dict[str, Any]) -> dict[str, int]:
    return {
        "Decision": len(result.get("key_conclusions", []) or []),
        "Action": len(result.get("action_items", []) or []),
        "Risk": len(result.get("risks_and_focus", []) or []),
        "Agenda": len(result.get("meeting_agenda", []) or []),
        "Unresolved": len(result.get("unresolved_issues", []) or []),
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def golden_eval(strategy: str) -> dict[str, Any]:
    import services.worker.scripts.run_rag_v3_2_0_retrieval_golden_eval as eval_mod
    from app.config import get_settings

    configure_environment()
    get_settings.cache_clear()
    original = install_merge_strategy(strategy)
    try:
        chunks = eval_mod.load_chunks()
        chunks_by_id = {item["chunk_id"]: item for item in chunks}
        cases = eval_mod.build_golden_cases()
        evaluation = eval_mod.evaluate_retrieval(cases, chunks_by_id)
        aggregate = eval_mod.aggregate_results(evaluation["results"])
    finally:
        restore_merge_strategy(original)
        get_settings.cache_clear()

    quoted = next(
        result
        for result in evaluation["results"]
        if result["case_id"] == "action_quoted_example_not_action_001"
    )

    return {
        "overall": aggregate["overall"],
        "by_dimension": aggregate["by_dimension"],
        "by_scenario": aggregate["by_scenario"],
        "quoted_example": {
            "rank": quoted["first_relevant_rank"],
            "top5": quoted["retrieved_chunk_ids"][:5],
            "fixed_policy_ranks": fixed_policy_ranks(
                quoted["retrieval_trace"]
            ),
        },
        "case_results": evaluation["results"],
    }


def frozen_eval(strategy: str) -> dict[str, Any]:
    from app.config import get_settings
    from services.worker.scripts import run_first_loss_analysis as first_loss

    configure_environment()
    get_settings.cache_clear()
    run_dir = OUTPUT_DIR / "frozen" / strategy
    run_dir.mkdir(parents=True, exist_ok=True)

    existing_trace = run_dir / "first_loss_trace.json"
    existing_validated = run_dir / "validated_result.json"
    if existing_trace.exists() and existing_validated.exists():
        trace = load_json(existing_trace)
        final_result = load_json(existing_validated)
        rag_context = load_json(run_dir / "rag_context.json")
        trace_targets = trace["targets"]
        action_fp_trace = trace["action_fp_production_trace"]
        selected = selected_chunks_by_dimension(
            rag_context.get("retrieval_trace", {})
        )
    else:
        original = install_merge_strategy(strategy)
        parsed = first_loss.parse_meeting_text(
            first_loss.DEFAULT_INPUT_FILE
        )
        try:
            transcript_segments = first_loss.build_transcript_segments(
                parsed
            )
            transcript_text = first_loss.build_transcript_text(
                transcript_segments
            )
            semantic_trace = first_loss.run_semantic_shadow_trace(
                f"fixed-policy-ab-{strategy}",
                transcript_segments,
                trace_root=run_dir / "semantic_pipeline_trace",
            )
            semantic_action_candidates = (
                first_loss._semantic_action_candidates_from_trace(
                    semantic_trace
                )
            )
            semantic_decision_candidates = (
                first_loss._semantic_decision_candidates_from_trace(
                    semantic_trace
                )
            )
            semantic_unresolved_candidates = (
                first_loss._semantic_unresolved_candidates_from_trace(
                    semantic_trace
                )
            )
            pipeline = first_loss.run_formal_pipeline(
                transcript_text=transcript_text,
                transcript_segments=transcript_segments,
                semantic_action_candidates=semantic_action_candidates,
                semantic_decision_candidates=semantic_decision_candidates,
                semantic_unresolved_candidates=semantic_unresolved_candidates,
                output_dir=run_dir,
                top_k=6,
            )

            final_result = pipeline["validated_result"]
            trace_targets = [
                first_loss.build_target_diagnosis(
                    target,
                    transcript_rows=transcript_segments,
                    semantic_trace_dir=semantic_trace,
                    rag_trace=pipeline["rag_context"].retrieval_trace,
                    qwen_raw_parsed=pipeline["qwen_raw_parsed"],
                    normalized_before_fusion=pipeline[
                        "normalized_before_fusion"
                    ],
                    action_fused=pipeline["action_fused"],
                    decision_fused=pipeline["decision_fused"],
                    unresolved_fused=pipeline["unresolved_fused"],
                    evidence_resolved=pipeline["evidence_resolved"],
                    postprocessed=pipeline["postprocessed"],
                    validated_result=final_result,
                    action_fusion_audit=pipeline["action_fusion_audit"],
                    postprocessor_audit=pipeline["postprocessor_audit"],
                    validator_audit=pipeline["validator_audit"],
                )
                for target in first_loss.TARGETS
            ]
            action_fp_trace = first_loss.build_action_fp_production_trace(
                transcript_rows=transcript_segments,
                semantic_trace_dir=semantic_trace,
                rag_trace=pipeline["rag_context"].retrieval_trace,
                qwen_raw_parsed=pipeline["qwen_raw_parsed"],
                normalized_before_fusion=pipeline[
                    "normalized_before_fusion"
                ],
                action_fused=pipeline["action_fused"],
                evidence_resolved=pipeline["evidence_resolved"],
                postprocessed=pipeline["postprocessed"],
                validated_result=final_result,
                final_result=None,
                action_fusion_audit=pipeline["action_fusion_audit"],
                postprocessor_audit=pipeline["postprocessor_audit"],
                validator_audit=pipeline["validator_audit"],
            )
            trace = {
                "metadata": {
                    "strategy": strategy,
                    "output_dir": str(run_dir),
                    "input_file": str(first_loss.DEFAULT_INPUT_FILE),
                    "rag_collection_name": get_settings().rag_collection_name,
                    "rag_dataset_version": get_settings().rag_dataset_version,
                },
                "targets": trace_targets,
                "action_fp_production_trace": action_fp_trace,
            }
            write_json(run_dir / "first_loss_trace.json", trace)
            selected = selected_chunks_by_dimension(
                pipeline["rag_context"].retrieval_trace
            )
        finally:
            restore_merge_strategy(original)
            get_settings.cache_clear()

    counts = result_counts(final_result)
    fp_targets = action_fp_trace.get("targets", [])
    old_fp_regressed = any(
        item.get("reappeared_after_removal")
        for item in fp_targets
    )
    gate = {
        "Decision": counts["Decision"] >= 3,
        "Action": counts["Action"] >= 4,
        "Risk": counts["Risk"] >= 2,
        "Contract": bool(final_result),
        "Action_old_fp": not old_fp_regressed,
    }

    action_recording = next(
        item
        for item in trace_targets
        if item["target"] == "action_recording_test"
    )
    risk_resource = next(
        item
        for item in trace_targets
        if item["target"] == "risk_model_resource"
    )
    return {
        "output_dir": str(run_dir),
        "counts": counts,
        "gate": gate,
        "gate_passed": all(gate.values()),
        "selected_chunks_by_dimension": selected,
        "final_result": final_result,
        "target_failures": {
            "action_recording_test": {
                "first_loss_layer": action_recording["first_loss_layer"],
                "first_loss_reason": action_recording["first_loss_reason"],
                "stage_presence": action_recording["presence"],
                "postprocessor_result": action_recording.get(
                    "postprocessor_result"
                ),
                "validator_result": action_recording.get(
                    "validator_result"
                ),
                "final_result": action_recording.get("final_result"),
            },
            "risk_model_resource": {
                "first_loss_layer": risk_resource["first_loss_layer"],
                "first_loss_reason": risk_resource["first_loss_reason"],
                "stage_presence": risk_resource["presence"],
                "postprocessor_result": risk_resource.get(
                    "postprocessor_result"
                ),
                "validator_result": risk_resource.get(
                    "validator_result"
                ),
                "final_result": risk_resource.get("final_result"),
            },
        },
        "action_fp": action_fp_trace,
    }


def summarize_fixed_policy(strategy_result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    selected = strategy_result["frozen"]["selected_chunks_by_dimension"]
    for dimension, details in selected.items():
        summary[dimension] = {
            "chunk_ids": details["chunk_ids"],
            "fixed_policy_ranks": details["fixed_policy_ranks"],
        }
    return summary


def write_report(results: dict[str, Any]) -> None:
    lines = [
        "# Fixed Policy Merge/Rank Offline A/B Report",
        "",
        "## Scope",
        "",
        "Offline A/B only. No production strategy, chunks, Prompt, Top-K, Embedding, Query Rewrite, PostProcessor, Validator, Fusion, Schema, or default feature flag values were changed.",
        "",
        "## Strategies",
        "",
    ]
    for key, label in STRATEGIES.items():
        lines.append(f"- {key}: {label}")

    lines.extend(["", "## Golden Retrieval Metrics", ""])
    lines.append("| Strategy | R@1 | R@3 | R@5 | P@5 | MRR | Leakage | quoted rank | fixed_policy rank |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for key in STRATEGIES:
        golden = results["strategies"][key]["golden"]
        overall = golden["overall"]
        fixed = golden["quoted_example"]["fixed_policy_ranks"]
        fixed_rank = ", ".join(
            f"{item['chunk_id']}@{item['rank']}" for item in fixed
        ) or "none in Top-5"
        quoted_rank = golden["quoted_example"]["rank"]
        lines.append(
            f"| {key} | {overall['recall_at_1']} | {overall['recall_at_3']} | {overall['recall_at_5']} | {overall['precision_at_5']} | {overall['mrr']} | {overall['dimension_leakage']} | {quoted_rank or 'miss'} | {fixed_rank} |"
        )

    lines.extend(["", "## Frozen Final Counts", ""])
    lines.append("| Strategy | Decision | Action | Risk | Agenda | Unresolved | Gate |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for key in STRATEGIES:
        frozen = results["strategies"][key]["frozen"]
        counts = frozen["counts"]
        gate = "pass" if frozen["gate_passed"] else "fail"
        lines.append(
            f"| {key} | {counts['Decision']} | {counts['Action']} | {counts['Risk']} | {counts['Agenda']} | {counts['Unresolved']} | {gate} |"
        )

    lines.extend(["", "## Frozen Gate Details", ""])
    for key in STRATEGIES:
        frozen = results["strategies"][key]["frozen"]
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- output_dir: `{frozen['output_dir']}`")
        lines.append(f"- gate: `{json.dumps(frozen['gate'], ensure_ascii=False)}`")
        for dimension, details in summarize_fixed_policy(results["strategies"][key]).items():
            lines.append(
                f"- {dimension}: selected={details['chunk_ids']}; fixed_policy={details['fixed_policy_ranks']}"
            )
        action = frozen["target_failures"]["action_recording_test"]
        risk = frozen["target_failures"]["risk_model_resource"]
        lines.append(
            f"- action_recording_test first_loss: {action['first_loss_layer']} / {action['first_loss_reason']}"
        )
        lines.append(
            f"- risk_model_resource first_loss: {risk['first_loss_layer']} / {risk['first_loss_reason']}"
        )
        lines.append("")

    lines.extend(
        [
            "## Failure Localization",
            "",
            "In the prior shadow run and in strategies that keep fixed_policy first, the missing Action and Risk were present before PostProcessor and then removed at PostProcessor. The reranked retrieval context changed the knowledge pack emphasis: Action selected chunks became mostly negative/boundary examples after the fixed policy chunk, and Risk selected chunks emphasized boundary rules. That changed the model output and evidence shape before PostProcessor.",
            "",
            "Strategies B and C move reranked dense candidates ahead of fixed_policy. In Golden retrieval this removes fixed_policy rank-1 suppression for quoted-example. In Frozen, these strategies must be judged by the gate table above rather than retrieval metrics alone.",
            "",
            "## Required Answers",
            "",
        ]
    )

    best = results["recommendation"]["best_strategy"]
    lines.append(f"1. Best merge/rank strategy: `{best}`.")
    lines.append(
        f"2. Can retain both Reranker retrieval lift and Frozen gate: {results['recommendation']['keeps_retrieval_lift_and_frozen_gate']}."
    )
    lines.append(
        f"3. Should fixed_policy keep fixed rank1: {results['recommendation']['fixed_policy_should_remain_rank1']}."
    )
    lines.append(
        f"4. Worth next minimal production experiment: {results['recommendation']['worth_next_minimal_production_experiment']}."
    )

    REPORT_FILE.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {
        "scope": "offline_fixed_policy_merge_rank_ab",
        "strategies": {},
    }

    for strategy in STRATEGIES:
        print(f"[A/B] Running Golden {strategy}", flush=True)
        golden = golden_eval(strategy)
        print(f"[A/B] Running Frozen {strategy}", flush=True)
        frozen = frozen_eval(strategy)
        results["strategies"][strategy] = {
            "description": STRATEGIES[strategy],
            "golden": golden,
            "frozen": frozen,
        }

    eligible = []
    for strategy, data in results["strategies"].items():
        if data["frozen"]["gate_passed"]:
            overall = data["golden"]["overall"]
            eligible.append(
                (
                    overall["recall_at_5"],
                    overall["recall_at_1"],
                    overall["mrr"],
                    -overall["dimension_leakage"],
                    strategy,
                )
            )
    eligible.sort(reverse=True)
    best_strategy = eligible[0][-1] if eligible else None
    keeps_both = bool(best_strategy)
    results["recommendation"] = {
        "best_strategy": best_strategy,
        "keeps_retrieval_lift_and_frozen_gate": keeps_both,
        "fixed_policy_should_remain_rank1": False
        if best_strategy
        in {
            "B_reranked_dense_first_fixed_policy",
            "C_unified_score_merge",
        }
        else "not_supported_by_failed_gate",
        "worth_next_minimal_production_experiment": keeps_both,
    }

    write_json(RESULTS_FILE, results)
    write_report(results)
    print(
        json.dumps(
            {
                "results": str(RESULTS_FILE),
                "report": str(REPORT_FILE),
                "recommendation": results["recommendation"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
