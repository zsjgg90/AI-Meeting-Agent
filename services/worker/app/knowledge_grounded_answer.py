from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.ollama_client import OllamaClient


FALLBACK_ANSWER = "暂未找到足够可靠的会议证据"


class KnowledgeAnswerSource(BaseModel):
    knowledge_id: str
    meeting_id: str
    meeting_title: str
    knowledge_type: str
    source_text: str
    speaker: str | None = None
    meeting_time: str | None = None
    source_segment_id: str | None = None


class KnowledgeGroundedAnswerRequest(BaseModel):
    query: str = Field(min_length=1)
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    structured_facts: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGroundedAnswerResponse(BaseModel):
    answer: str


def answer_from_sources(
    payload: KnowledgeGroundedAnswerRequest,
    *,
    llm_client: OllamaClient | None = None,
) -> KnowledgeGroundedAnswerResponse:
    sources = [source for source in payload.sources if source.source_text.strip()]
    structured_facts = _clean_structured_facts(payload.structured_facts)
    if not sources and not structured_facts:
        return KnowledgeGroundedAnswerResponse(answer=FALLBACK_ANSWER)

    client = llm_client or OllamaClient(response_format="")
    prompt = _build_prompt(payload.query, sources, structured_facts=structured_facts)
    raw = client.chat(prompt, system_prompt=_system_prompt())
    answer = _extract_answer(raw)
    if not answer:
        answer = FALLBACK_ANSWER
    answer = _append_evidence_notes(answer, sources)
    return KnowledgeGroundedAnswerResponse(answer=answer)


def _system_prompt() -> str:
    return (
        "You are a Knowledge grounded-answer assistant. "
        "You must answer only from the Structured Facts and Retrieved Evidence sections. "
        "Do not use outside knowledge, meeting assumptions, or general project knowledge. "
        "Never add or infer missing quantities, owners, deadlines, decisions, or risks. "
        "Preserve explicit names, dates, deadlines, owner names, decision terms, risk conditions, and domain terms exactly when evidence states them. "
        "Do not rewrite structured facts into new facts. "
        "For partial evidence, answer only the supported parts and explicitly say 暂未找到明确证据 for unsupported parts. "
        f"If no supported answer exists at all, return exactly: {FALLBACK_ANSWER}"
    )


def _build_prompt(
    query: str,
    sources: list[KnowledgeAnswerSource],
    *,
    structured_facts: dict[str, Any] | None = None,
) -> str:
    facts_text = json.dumps(structured_facts or {}, ensure_ascii=False, indent=2)
    evidence_lines = []
    for index, source in enumerate(sources, start=1):
        evidence_lines.append(
            "\n".join(
                [
                    f"[Evidence {index}]",
                    f"knowledge_id: {source.knowledge_id}",
                    f"meeting_id: {source.meeting_id}",
                    f"meeting_title: {source.meeting_title}",
                    f"knowledge_type: {source.knowledge_type}",
                    f"speaker: {source.speaker or ''}",
                    f"meeting_time: {source.meeting_time or ''}",
                    f"source_segment_id: {source.source_segment_id or ''}",
                    f"source_text: {source.source_text}",
                ]
            )
        )
    evidence_text = chr(10).join(evidence_lines) if evidence_lines else "(none)"
    return "\n\n".join(
        [
            "User Question",
            query.strip(),
            "Structured Facts",
            facts_text,
            "Retrieved Evidence",
            evidence_text,
            "Grounded Answer Rules",
            "\n".join(
                [
                    "1. Use only Structured Facts and Retrieved Evidence.",
                    "2. Keep FACT data unchanged. Do not ask Qwen3 to recalculate, reinterpret, or rewrite structured facts.",
                    "3. Counts, owners, deadlines, decisions, and risks must appear only when explicitly present in Structured Facts or Retrieved Evidence.",
                    "4. If one part of the question is supported and another part is unsupported, answer the supported part and write 暂未找到明确证据 for each unsupported part.",
                    "5. Preserve exact evidence wording for critical fields such as owner, deadline, decision, risk, product/project/feature names, and meeting date.",
                    f"6. If no part has support, return exactly: {FALLBACK_ANSWER}",
                    "7. Return plain text only.",
                ]
            ),
        ]
    )


def _clean_structured_facts(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return value


def _extract_answer(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        payload: Any = json.loads(text)
    except ValueError:
        return text
    if isinstance(payload, dict):
        return str(payload.get("answer") or "").strip()
    return text


def _append_evidence_notes(answer: str, sources: list[KnowledgeAnswerSource], *, limit: int = 4) -> str:
    clean_answer = str(answer or "").strip()
    if not clean_answer or "证据原文要点：" in clean_answer:
        return clean_answer
    lines = _evidence_note_lines(sources, limit=limit)
    if not lines:
        return clean_answer
    if clean_answer == FALLBACK_ANSWER:
        clean_answer = "暂未找到明确证据支持该结论。"
    return "\n".join([clean_answer, "证据原文要点：", *lines])


def _evidence_note_lines(sources: list[KnowledgeAnswerSource], *, limit: int, max_chars: int = 220) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for source in sources:
        text = " ".join(source.source_text.strip().split())
        if not text or text in seen:
            continue
        seen.add(text)
        if len(text) > max_chars:
            text = f"{text[:max_chars].rstrip()}..."
        lines.append(f"- {text}")
        if len(lines) >= limit:
            break
    return lines
