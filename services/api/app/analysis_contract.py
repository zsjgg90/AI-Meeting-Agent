from __future__ import annotations

from typing import Any


ANALYSIS_SCHEMA_VERSION = "meeting-analysis-v1"


def infer_result_source(model_name: str | None, prompt_version: str | None) -> str:
    if model_name == "fixture-gold-standard" or prompt_version == "manual-expo-test":
        return "fixture"
    if model_name == "semantic-pipeline":
        return "semantic_pipeline"
    if model_name and "+rag" in model_name:
        return "legacy_qwen_rag"
    return "unknown"


def build_summary_metadata(
    *,
    model_name: str | None,
    confidence_score: float | None,
    generated_at: str,
    prompt_version: str | None = None,
    rag_chunk_ids: list[str] | None = None,
    rag_dataset_version: str | None = None,
    rag_chunk_schema_version: str | None = None,
    rag_collection_name: str | None = None,
    rag_embedding_model: str | None = None,
    result_source: str | None = None,
) -> dict[str, Any]:
    resolved_result_source = result_source or infer_result_source(model_name, prompt_version)
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "model_name": model_name or "",
        "prompt_version": prompt_version,
        "result_source": resolved_result_source,
        "rag_chunk_ids": rag_chunk_ids or [],
        "rag_dataset_version": rag_dataset_version,
        "rag_chunk_schema_version": rag_chunk_schema_version,
        "rag_collection_name": rag_collection_name,
        "rag_embedding_model": rag_embedding_model,
        "confidence_score": confidence_score or 0,
        "generated_at": generated_at,
    }
