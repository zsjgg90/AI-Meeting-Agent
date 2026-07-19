import json
import re
import time

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
from app.prompt_registry import get_meeting_analyst_prompt_spec
from app.observability import log_event, log_stage
from app.config import get_settings

from app.anti_hallucination_validator import (
    validate_meeting_analysis,
)
from app.analysis_contract import normalize_meeting_analysis_result
from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor


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

        self.llm_client = (
            llm_client or OllamaClient()
        )

    def analyze(
        self,
        transcript: str,
        top_k: int | None = None,
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
                self.retriever.build_context_payload(
                    query=RAG_QUERY,
                    top_k=resolved_top_k,
                )
            )
        log_event(
            "analysis.rag_context",
            rag_chunk_count=len(rag_context.chunk_ids),
            rag_context_chars=len(rag_context.text),
            rag_chunk_ids=rag_context.chunk_ids,
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

        print(
            "[ANALYST] Step 5/5: normalizing, post-processing, and validating result"
        )

        parsed_result["_metadata"] = {
            "prompt_id": prompt_spec.prompt_id,
            "prompt_version": prompt_spec.prompt_version,
            "schema_version": prompt_spec.schema_version,
            "rag_chunk_ids": rag_context.chunk_ids,
            "rag_dataset_version": rag_context.dataset_version,
            "rag_chunk_schema_version": rag_context.chunk_schema_version,
            "rag_collection_name": rag_context.collection_name,
            "rag_embedding_model": rag_context.embedding_model,
            "result_source": "legacy_qwen_rag",
        }

        with log_stage("schema_normalize", schema_version=prompt_spec.schema_version):
            normalized_before_postprocess = normalize_meeting_analysis_result(
                parsed_result,
                model_name=f"{settings.ollama_model}+rag",
            )

        postprocessor = MeetingAnalysisPostProcessor()
        with log_stage("postprocess", schema_version=prompt_spec.schema_version):
            postprocessed = postprocessor.process(
                normalized_before_postprocess,
                transcript,
            )

        with log_stage(
            "validation",
            schema_version=prompt_spec.schema_version,
            postprocessor_audit_summary=postprocessor.audit_summary(),
        ):
            validated_result = (
                validate_meeting_analysis(
                    postprocessed.model_dump(),
                    transcript,
                )
            )

        validated_result["_metadata"] = {
            "prompt_id": prompt_spec.prompt_id,
            "prompt_version": prompt_spec.prompt_version,
            "schema_version": prompt_spec.schema_version,
            "rag_chunk_ids": rag_context.chunk_ids,
            "rag_dataset_version": rag_context.dataset_version,
            "rag_chunk_schema_version": rag_context.chunk_schema_version,
            "rag_collection_name": rag_context.collection_name,
            "rag_embedding_model": rag_context.embedding_model,
            "ollama_temperature": self.llm_client.temperature,
            "ollama_top_p": self.llm_client.top_p,
            "ollama_seed": self.llm_client.seed,
            "ollama_format": self.llm_client.response_format,
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
) -> dict:
    service = (
        get_meeting_analyst_service()
    )

    return service.analyze(
        transcript=transcript,
        top_k=top_k,
    )
