import json
import re
import time
from typing import Any

from app.action_validator_trace import write_action_validator_trace
from app.rag_retriever import (
    RagRetriever,
)

from app.ollama_client import (
    OllamaClient,
)

from app.meeting_analyst_prompt import (
    RAG_QUERY,
    build_meeting_analyst_prompt,
)
from app.semantic_intelligence.boundary_engine import analyze_boundary
from app.semantic_intelligence.event_understanding import analyze_event
from app.semantic_intelligence.rag_adapter import build_rag_request
from app.semantic_intelligence.retrieval_bridge import RetrievalBridge
from app.semantic_intelligence.rule_planner import build_rule_plan
from app.prompt_registry import get_meeting_analyst_prompt_spec
from app.observability import log_event, log_stage
from app.config import get_settings

from app.anti_hallucination_validator import (
    validate_meeting_analysis_with_audit,
)
from app.analysis_contract import (
    canonicalize_meeting_analysis_aliases,
    ensure_non_empty_analysis_result,
    normalize_meeting_analysis_result,
)
from app.action_fusion import fuse_action_items, mark_action_fusion_final_survivors
from app.decision_fusion import fuse_key_conclusions_with_decisions
from app.unresolved_fusion import fuse_unresolved_issues
from app.evidence_resolver import resolve_meeting_analysis_evidence
from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor


FORMAL_DIMENSION_RAG_QUERIES: tuple[dict[str, str], ...] = (
    {
        "dimension": "action_items",
        "target_dimension": "Action",
        "query": (
            f"{RAG_QUERY}\n\n"
            "Target dimension: action_items.\n"
            "Focus: actionable commitments, assignment, owner/deadline evidence, "
            "quoted examples, progress updates, weak suggestions, and boundaries "
            "where a progress update is not a new action item."
        ),
    },
    {
        "dimension": "key_conclusions",
        "target_dimension": "Decision",
        "query": (
            f"{RAG_QUERY}\n\n"
            "Target dimension: key_conclusions.\n"
            "Focus: accepted decisions, explicit confirmation, proposal-vs-decision "
            "boundaries, weak suggestions, options, and negative examples where a "
            "proposal is not a conclusion."
        ),
    },
    {
        "dimension": "unresolved_issues",
        "target_dimension": "Unresolved",
        "query": (
            f"{RAG_QUERY}\n\n"
            "Target dimension: unresolved_issues.\n"
            "Focus: open questions, unresolved state, answered-question boundaries, "
            "question-vs-unresolved negative examples, and issues that remain "
            "without answer, plan, or closure."
        ),
    },
    {
        "dimension": "risks_and_focus",
        "target_dimension": "Risk",
        "query": (
            f"{RAG_QUERY}\n\n"
            "Target dimension: risks_and_focus.\n"
            "Focus: future adverse impact, risk-vs-unresolved boundary, mitigation "
            "only when confirmed, and negative examples where suggestions or "
            "quoted examples are not risks."
        ),
    },
)

SEMANTIC_PROPOSAL_MARKERS = (
    "可以研究",
    "研究一下",
    "后面可以",
    "可以考虑",
    "考虑一下",
    "看看",
)

SEMANTIC_DECISION_MARKERS = (
    "确认",
    "决定",
    "确定",
    "批准",
    "同意",
    "达成",
)

SEMANTIC_ACTION_MARKERS = (
    "测试",
    "整理",
    "开发",
    "修改",
    "修复",
    "提交",
    "跟进",
    "处理",
    "检查",
)

SEMANTIC_TIME_MARKERS = (
    "今天",
    "下午",
    "明天",
    "本周",
    "下周",
)

SEMANTIC_PERSON_MARKERS = (
    "张",
    "李",
    "王",
    "陈",
    "赵",
    "负责人",
    "前端",
    "后端",
)


def _contains_any(
    text: str,
    markers: tuple[str, ...],
) -> bool:
    return any(marker in text for marker in markers)


def infer_semantic_event_type(
    text: str,
) -> str | None:
    if _contains_any(text, SEMANTIC_PROPOSAL_MARKERS):
        return "proposal"

    if _contains_any(text, SEMANTIC_DECISION_MARKERS):
        return "decision"

    if _contains_any(
        text,
        SEMANTIC_ACTION_MARKERS,
    ) and (
        _contains_any(text, SEMANTIC_TIME_MARKERS)
        or _contains_any(text, SEMANTIC_PERSON_MARKERS)
    ):
        return "action_assignment"

    return None


def build_semantic_retrieval_request(
    transcript: str,
    *,
    top_k: int,
) -> dict[str, Any] | None:
    text = str(transcript or "").strip()
    if not text:
        return None

    event_type = infer_semantic_event_type(
        text
    )
    if event_type is None:
        return None

    context = analyze_event(
        {
            "event_type": event_type,
            "content": text,
        }
    )
    boundary = analyze_boundary(
        context.model_dump()
    )
    rule_plan = build_rule_plan(
        context.model_dump(),
        boundary.model_dump(),
    )
    rag_request = build_rag_request(
        rule_plan.model_dump()
    )
    rag_request["top_k"] = top_k
    rag_request["transcript"] = text
    rag_request["semantic_event_type"] = event_type
    rag_request["semantic_boundary_type"] = (
        boundary.boundary_type
    )
    return rag_request


def extract_json(text: str) -> dict:
    if not text:
        raise ValueError(
            "Model output is empty"
        )

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1:
        raise ValueError(
            "No JSON start token found"
        )

    if end == -1:
        raise ValueError(
            "No JSON end token found"
        )

    if end <= start:
        raise ValueError(
            "Invalid JSON object range"
        )

    json_text = cleaned[
        start : end + 1
    ]

    try:
        return json.loads(json_text)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid model JSON: {exc}"
        ) from exc


class MeetingAnalystService:
    def __init__(
        self,
        retriever: RagRetriever | None = None,
        llm_client: OllamaClient | None = None,
    ):
        self.retriever = (
            retriever or RagRetriever()
        )
        self.retrieval_bridge = RetrievalBridge(
            self.retriever
        )

        self.llm_client = (
            llm_client or OllamaClient()
        )

    @staticmethod
    def _deduplicate_chunks(
        contexts: list[Any],
    ) -> list[dict]:
        seen_ids: set[str] = set()
        chunks: list[dict] = []

        for context in contexts:
            for chunk in context.chunks:
                chunk_id = str(
                    chunk.get("chunk_id", "")
                )

                if not chunk_id or chunk_id in seen_ids:
                    continue

                seen_ids.add(chunk_id)
                chunks.append(chunk)

        return chunks

    @staticmethod
    def _merge_bucket_maps(
        contexts: list[Any],
    ) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = {}

        for context in contexts:
            for bucket, chunk_ids in (
                context.retrieval_buckets or {}
            ).items():
                target = buckets.setdefault(
                    str(bucket),
                    [],
                )
                for chunk_id in chunk_ids:
                    resolved_id = str(chunk_id)
                    if resolved_id not in target:
                        target.append(resolved_id)

        return buckets

    @staticmethod
    def _combine_dimension_context_text(
        contexts: list[Any],
        *,
        max_chars: int | None = None,
    ) -> str:
        parts: list[str] = []
        per_context_limit: int | None = None

        if max_chars is not None and max_chars > 0:
            per_context_limit = max(
                1,
                max_chars // max(1, len(contexts)),
            )

        for context in contexts:
            trace = context.retrieval_trace or {}
            dimension = str(
                trace.get("target_dimension")
                or "unknown"
            )
            text = str(context.text or "").strip()
            if (
                per_context_limit is not None
                and len(text) > per_context_limit
            ):
                text = text[:per_context_limit]
            if text:
                parts.append(
                    f"[RAG target_dimension={dimension}]\n{text}"
                )

        combined = "\n\n".join(parts)

        if max_chars is not None and max_chars > 0:
            return combined[:max_chars]

        return combined

    def _build_formal_rag_context(
        self,
        *,
        transcript: str,
        top_k: int,
    ):
        semantic_context = (
            self._build_semantic_guided_rag_context(
                transcript=transcript,
                top_k=top_k,
            )
        )
        if semantic_context is not None:
            return semantic_context

        return self._build_default_formal_rag_context(
            transcript=transcript,
            top_k=top_k,
        )

    def _build_semantic_guided_rag_context(
        self,
        *,
        transcript: str,
        top_k: int,
    ):
        rag_request = build_semantic_retrieval_request(
            transcript,
            top_k=top_k,
        )
        if rag_request is None:
            return None

        try:
            context = self.retrieval_bridge.retrieve_context(
                rag_request
            )
        except Exception as exc:
            log_event(
                "semantic_retrieval.fallback",
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            return None

        trace = dict(
            context.retrieval_trace or {}
        )
        trace["semantic_guided_retrieval"] = {
            "event_type": rag_request.get(
                "semantic_event_type"
            ),
            "boundary_type": rag_request.get(
                "semantic_boundary_type"
            ),
            "query": rag_request.get(
                "query",
                "",
            ),
            "target_dimension": (
                rag_request.get(
                    "metadata_filter",
                    {},
                ).get("dimension")
            ),
        }

        return type(context)(
            text=context.text,
            chunks=context.chunks,
            chunk_ids=context.chunk_ids,
            collection_name=context.collection_name,
            embedding_model=context.embedding_model,
            dataset_version=context.dataset_version,
            chunk_schema_version=context.chunk_schema_version,
            retrieved_chunk_ids=(
                context.retrieved_chunk_ids
            ),
            retrieval_version=context.retrieval_version,
            scenario_taxonomy_version=(
                context.scenario_taxonomy_version
            ),
            retrieval_strategy=(
                f"semantic_guided_{context.retrieval_strategy}"
            ),
            retrieval_buckets=context.retrieval_buckets,
            retrieval_trace=trace,
            routed_meeting_type=context.routed_meeting_type,
            routed_scenario=context.routed_scenario,
            fallback_reason=context.fallback_reason,
        )

    def _build_default_formal_rag_context(
        self,
        *,
        transcript: str,
        top_k: int,
    ):
        settings = get_settings()

        if not settings.rag_v3_retrieval_enabled:
            return self.retriever.build_context_payload(
                query=RAG_QUERY,
                top_k=top_k,
                transcript=transcript,
            )

        try:
            contexts = [
                self.retriever.build_context_payload(
                    query=target["query"],
                    top_k=top_k,
                    transcript=transcript,
                    target_dimension=target[
                        "target_dimension"
                    ],
                )
                for target in FORMAL_DIMENSION_RAG_QUERIES
            ]
        except Exception as exc:
            fallback_context = (
                self.retriever.build_context_payload(
                    query=RAG_QUERY,
                    top_k=top_k,
                    transcript=transcript,
                )
            )
            fallback_context.retrieval_trace[
                "formal_dimension_fallback_reason"
            ] = f"{type(exc).__name__}: {exc}"
            return fallback_context

        base_context = contexts[0]
        chunks = self._deduplicate_chunks(
            contexts
        )
        chunk_ids = [
            str(chunk["chunk_id"])
            for chunk in chunks
        ]
        dimension_traces = {
            target["dimension"]: context.retrieval_trace
            for target, context in zip(
                FORMAL_DIMENSION_RAG_QUERIES,
                contexts,
            )
        }

        return type(base_context)(
            text=self._combine_dimension_context_text(
                contexts,
                max_chars=getattr(
                    self.retriever,
                    "max_context_chars",
                    None,
                ),
            ),
            chunks=chunks,
            chunk_ids=chunk_ids,
            collection_name=base_context.collection_name,
            embedding_model=base_context.embedding_model,
            dataset_version=base_context.dataset_version,
            chunk_schema_version=base_context.chunk_schema_version,
            retrieved_chunk_ids=chunk_ids,
            retrieval_version=base_context.retrieval_version,
            scenario_taxonomy_version=base_context.scenario_taxonomy_version,
            retrieval_strategy="v3_formal_dimension_aware",
            retrieval_buckets=self._merge_bucket_maps(
                contexts
            ),
            retrieval_trace={
                "strategy": "v3_formal_dimension_aware",
                "dimension_traces": dimension_traces,
                "final_selected_chunk_ids": chunk_ids,
                "fallback_reason": None,
            },
            routed_meeting_type=base_context.routed_meeting_type,
            routed_scenario=base_context.routed_scenario,
            fallback_reason=None,
        )

    def analyze(
        self,
        transcript: str,
        top_k: int | None = None,
        semantic_action_candidates: list[dict] | None = None,
        semantic_decision_candidates: list[dict] | None = None,
        semantic_unresolved_candidates: list[dict] | None = None,
        transcript_segments: list[Any] | None = None,
    ) -> dict:
        if not transcript or not transcript.strip():
            raise ValueError(
                "Transcript cannot be empty"
            )

        total_started_at = time.perf_counter()
        settings = get_settings()
        resolved_top_k = top_k if top_k is not None else settings.rag_top_k
        prompt_spec = get_meeting_analyst_prompt_spec()
        log_event(
            "analysis.started",
            transcript=transcript,
            transcript_chars=len(transcript),
            model_name=self.llm_client.model,
            prompt_version=prompt_spec.prompt_version,
            schema_version=prompt_spec.schema_version,
            rag_top_k=resolved_top_k,
            ollama_timeout=self.llm_client.timeout,
            ollama_temperature=self.llm_client.temperature,
            ollama_top_p=self.llm_client.top_p,
            ollama_seed=self.llm_client.seed,
            ollama_format=self.llm_client.response_format,
        )

        print(
            "[ANALYST] Step 1/5: retrieving RAG rules"
        )

        with log_stage("rag_retrieval", rag_top_k=resolved_top_k):
            rag_context = (
                self._build_formal_rag_context(
                    transcript=transcript,
                    top_k=resolved_top_k,
                )
            )
        log_event(
            "analysis.rag_context",
            rag_chunk_count=len(rag_context.chunk_ids),
            rag_context_chars=len(rag_context.text),
            rag_chunk_ids=rag_context.chunk_ids,
            rag_retrieval_strategy=rag_context.retrieval_strategy,
            rag_retrieval_buckets=rag_context.retrieval_buckets,
            rag_retrieval_trace=rag_context.retrieval_trace,
            rag_dimension_traces=(
                rag_context.retrieval_trace.get(
                    "dimension_traces",
                    {},
                )
                if isinstance(
                    rag_context.retrieval_trace,
                    dict,
                )
                else {}
            ),
            rag_routed_meeting_type=rag_context.routed_meeting_type,
            rag_routed_scenario=rag_context.routed_scenario,
            rag_fallback_reason=rag_context.fallback_reason,
            retrieved_chunk_ids=rag_context.retrieved_chunk_ids or rag_context.chunk_ids,
            retrieval_version=rag_context.retrieval_version,
            scenario_taxonomy_version=rag_context.scenario_taxonomy_version,
        )

        print(
            "[ANALYST] Step 2/5: building prompt"
        )

        with log_stage(
            "prompt_build",
            prompt_version=prompt_spec.prompt_version,
            rag_chunk_ids=rag_context.chunk_ids,
        ):
            prompt = build_meeting_analyst_prompt(
                rag_context=rag_context.text,
                transcript=transcript,
            )
        log_event(
            "analysis.prompt_built",
            prompt=prompt,
            prompt_chars=len(prompt),
            transcript_chars=len(transcript),
            rag_chunk_count=len(rag_context.chunk_ids),
        )

        print(
            "[ANALYST] Step 3/5: calling Qwen3"
        )

        with log_stage(
            "model_inference",
            model_name=self.llm_client.model,
            temperature=self.llm_client.temperature,
            top_p=self.llm_client.top_p,
            seed=self.llm_client.seed,
            response_format=self.llm_client.response_format,
            context=self.llm_client.num_ctx,
            base_url=self.llm_client.base_url,
        ):
            raw_output = self.llm_client.chat(
                prompt=prompt
            )

        print(
            "[ANALYST] Step 4/5: parsing JSON"
        )

        with log_stage("json_parse", raw_output=raw_output):
            parsed_result = extract_json(
                raw_output
            )
        parsed_result = canonicalize_meeting_analysis_aliases(
            parsed_result
        )

        print(
            "[ANALYST] Step 5/5: normalizing, post-processing, validating result, and keeping title candidate"
        )
        title_fields = {
            "meeting_title": str(parsed_result.get("meeting_title") or "").strip(),
            "meeting_type": str(parsed_result.get("meeting_type") or "").strip(),
            "meeting_type_confidence": parsed_result.get("meeting_type_confidence"),
            "meeting_title_candidate": str(parsed_result.get("meeting_title_candidate") or "").strip(),
            "title_basis": parsed_result.get("title_basis") if isinstance(parsed_result.get("title_basis"), list) else [],
        }

        parsed_result["_metadata"] = {
            "prompt_id": prompt_spec.prompt_id,
            "prompt_version": prompt_spec.prompt_version,
            "schema_version": prompt_spec.schema_version,
            "rag_chunk_ids": rag_context.chunk_ids,
            "rag_dataset_version": rag_context.dataset_version,
            "rag_chunk_schema_version": rag_context.chunk_schema_version,
            "rag_collection_name": rag_context.collection_name,
            "rag_embedding_model": rag_context.embedding_model,
            "retrieved_chunk_ids": rag_context.retrieved_chunk_ids or rag_context.chunk_ids,
            "retrieval_version": rag_context.retrieval_version,
            "scenario_taxonomy_version": rag_context.scenario_taxonomy_version,
            "rag_retrieval_strategy": rag_context.retrieval_strategy,
            "rag_retrieval_buckets": rag_context.retrieval_buckets,
            "rag_dimension_traces": (
                rag_context.retrieval_trace.get(
                    "dimension_traces",
                    {},
                )
                if isinstance(
                    rag_context.retrieval_trace,
                    dict,
                )
                else {}
            ),
            "rag_routed_meeting_type": rag_context.routed_meeting_type,
            "rag_routed_scenario": rag_context.routed_scenario,
            "rag_fallback_reason": rag_context.fallback_reason,
            "result_source": "legacy_qwen_rag",
        }

        with log_stage("schema_normalize", schema_version=prompt_spec.schema_version):
            normalized_before_postprocess = normalize_meeting_analysis_result(
                parsed_result,
                model_name=f"{settings.ollama_model}+rag",
            )

        action_fusion_audit: list[dict[str, Any]] = []
        with log_stage(
            "action_fusion",
            semantic_action_candidate_count=len(semantic_action_candidates or []),
            legacy_action_count=len(normalized_before_postprocess.action_items),
        ):
            action_fused = fuse_action_items(
                normalized_before_postprocess,
                semantic_action_candidates,
                audit=action_fusion_audit,
            )

        with log_stage(
            "decision_fusion",
            semantic_decision_candidate_count=len(semantic_decision_candidates or []),
            legacy_conclusion_count=len(action_fused.key_conclusions),
        ):
            decision_fused = fuse_key_conclusions_with_decisions(
                action_fused,
                semantic_decision_candidates,
            )

        with log_stage(
            "unresolved_fusion",
            semantic_unresolved_candidate_count=len(semantic_unresolved_candidates or []),
            legacy_unresolved_count=len(decision_fused.unresolved_issues),
        ):
            unresolved_fused = fuse_unresolved_issues(
                decision_fused,
                semantic_unresolved_candidates,
            )

        with log_stage("evidence_resolve", schema_version=prompt_spec.schema_version):
            evidence_resolved = resolve_meeting_analysis_evidence(
                unresolved_fused,
                transcript,
                transcript_segments=transcript_segments,
            )

        postprocessor = MeetingAnalysisPostProcessor()
        with log_stage("postprocess", schema_version=prompt_spec.schema_version):
            postprocessed = postprocessor.process(
                evidence_resolved,
                transcript,
            )

        with log_stage(
            "validation",
            schema_version=prompt_spec.schema_version,
            postprocessor_audit_summary=postprocessor.audit_summary(),
        ):
            validator_input = postprocessed.model_dump(exclude_defaults=True)
            validated_result, validator_audit = validate_meeting_analysis_with_audit(
                validator_input,
                transcript,
            )
            mark_action_fusion_final_survivors(
                action_fusion_audit,
                validated_result.get("action_items", []) or [],
            )
            log_event(
                "action_fusion.audit_trace",
                action_fusion_audit=action_fusion_audit,
            )
            if settings.action_validator_trace_enabled:
                trace_dir = write_action_validator_trace(
                    validator_input,
                    validated_result,
                    validator_audit,
                    output_dir=settings.action_validator_trace_dir,
                )
                log_event(
                    "action_validator_trace.written",
                    trace_dir=str(trace_dir),
                    validator_input_action_count=len(validator_input.get("action_items", []) or []),
                    validator_output_action_count=len(validated_result.get("action_items", []) or []),
                )
        for key, value in title_fields.items():
            if value not in ("", [], None):
                validated_result[key] = value
        ensure_non_empty_analysis_result(validated_result)

        validated_result["_metadata"] = {
            "prompt_id": prompt_spec.prompt_id,
            "prompt_version": prompt_spec.prompt_version,
            "schema_version": prompt_spec.schema_version,
            "rag_chunk_ids": rag_context.chunk_ids,
            "rag_dataset_version": rag_context.dataset_version,
            "rag_chunk_schema_version": rag_context.chunk_schema_version,
            "rag_collection_name": rag_context.collection_name,
            "rag_embedding_model": rag_context.embedding_model,
            "retrieved_chunk_ids": rag_context.retrieved_chunk_ids or rag_context.chunk_ids,
            "retrieval_version": rag_context.retrieval_version,
            "scenario_taxonomy_version": rag_context.scenario_taxonomy_version,
            "rag_retrieval_strategy": rag_context.retrieval_strategy,
            "rag_retrieval_buckets": rag_context.retrieval_buckets,
            "rag_dimension_traces": (
                rag_context.retrieval_trace.get(
                    "dimension_traces",
                    {},
                )
                if isinstance(
                    rag_context.retrieval_trace,
                    dict,
                )
                else {}
            ),
            "rag_routed_meeting_type": rag_context.routed_meeting_type,
            "rag_routed_scenario": rag_context.routed_scenario,
            "rag_fallback_reason": rag_context.fallback_reason,
            "ollama_temperature": self.llm_client.temperature,
            "ollama_top_p": self.llm_client.top_p,
            "ollama_seed": self.llm_client.seed,
            "ollama_format": self.llm_client.response_format,
            "semantic_action_candidate_count": len(semantic_action_candidates or []),
            "semantic_decision_candidate_count": len(semantic_decision_candidates or []),
            "semantic_unresolved_candidate_count": len(semantic_unresolved_candidates or []),
            "legacy_unresolved_count": len(normalized_before_postprocess.unresolved_issues),
            "fused_unresolved_count": len(unresolved_fused.unresolved_issues),
            "result_source": "legacy_qwen_rag",
        }

        log_event(
            "analysis.completed",
            duration_ms=round((time.perf_counter() - total_started_at) * 1000, 2),
            model_name=self.llm_client.model,
            result_source="legacy_qwen_rag",
            transcript_chars=len(transcript),
            prompt_chars=len(prompt),
            rag_chunk_count=len(rag_context.chunk_ids),
            ollama_timeout=self.llm_client.timeout,
            prompt_version=prompt_spec.prompt_version,
            schema_version=prompt_spec.schema_version,
            rag_chunk_ids=rag_context.chunk_ids,
            rag_dataset_version=rag_context.dataset_version,
            rag_collection_name=rag_context.collection_name,
            rag_embedding_model=rag_context.embedding_model,
            retrieved_chunk_ids=rag_context.retrieved_chunk_ids or rag_context.chunk_ids,
            retrieval_version=rag_context.retrieval_version,
            scenario_taxonomy_version=rag_context.scenario_taxonomy_version,
            rag_retrieval_strategy=rag_context.retrieval_strategy,
            rag_retrieval_buckets=rag_context.retrieval_buckets,
            rag_dimension_traces=(
                rag_context.retrieval_trace.get(
                    "dimension_traces",
                    {},
                )
                if isinstance(
                    rag_context.retrieval_trace,
                    dict,
                )
                else {}
            ),
            rag_routed_meeting_type=rag_context.routed_meeting_type,
            rag_routed_scenario=rag_context.routed_scenario,
            rag_fallback_reason=rag_context.fallback_reason,
            ollama_temperature=self.llm_client.temperature,
            ollama_top_p=self.llm_client.top_p,
            ollama_seed=self.llm_client.seed,
            ollama_format=self.llm_client.response_format,
        )

        return validated_result


_service_instance = None


def get_meeting_analyst_service():
    global _service_instance

    if _service_instance is None:
        _service_instance = (
            MeetingAnalystService()
        )

    return _service_instance


def analyze_meeting(
    transcript: str,
    top_k: int | None = None,
    semantic_action_candidates: list[dict] | None = None,
    semantic_decision_candidates: list[dict] | None = None,
    semantic_unresolved_candidates: list[dict] | None = None,
    transcript_segments: list[Any] | None = None,
) -> dict:
    service = (
        get_meeting_analyst_service()
    )

    return service.analyze(
        transcript=transcript,
        top_k=top_k,
        semantic_action_candidates=semantic_action_candidates,
        semantic_decision_candidates=semantic_decision_candidates,
        semantic_unresolved_candidates=semantic_unresolved_candidates,
        transcript_segments=transcript_segments,
    )
