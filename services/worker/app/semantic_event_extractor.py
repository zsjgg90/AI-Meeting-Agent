from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.meeting_analyst_service import extract_json
from app.ollama_client import OllamaClient
from app.semantic_clause_splitter import split_semantic_clauses
from app.semantic_event_schema import (
    SemanticEvent,
    SemanticEventExtractionResult,
    SemanticIntent,
    UtteranceInput,
)
from app.semantic_event_validator import (
    ValidationSummary,
    validate_semantic_events,
)


class ChatClient(Protocol):
    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        ...


@dataclass
class ExtractionDebug:
    raw_output: str | None = None
    parsed_before_validation: list[dict[str, Any]] | None = None
    validated_after: list[dict[str, Any]] | None = None
    retry_count: int = 0
    failure_reason: str | None = None
    bypass_reason: str | None = None


PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "prompts"
    / "semantic_event_extractor.md"
)

SYSTEM_PROMPT = (
    "你是会议语义事件抽取器。必须严格输出合法 JSON。"
    "不要输出 Markdown、解释文字或代码块以外的内容。"
)

ALLOWED_INTENTS: set[str] = {
    "agenda_statement",
    "progress_update",
    "decision",
    "proposal",
    "commitment",
    "task_assignment",
    "question",
    "open_issue",
    "risk_warning",
    "requirement",
    "rejection",
    "information",
    "non_event",
}


def _read_prompt_template() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _stable_event_id(
    utterance_id: str,
    source_text: str,
    index: int,
) -> str:
    raw = f"{utterance_id}:{index}:{source_text}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _normalize_intent(value: object) -> SemanticIntent:
    if isinstance(value, str) and value in ALLOWED_INTENTS:
        return value  # type: ignore[return-value]
    return "information"


def _force_system_fields(
    event_data: dict[str, Any],
    utterance: UtteranceInput,
    index: int,
) -> dict[str, Any]:
    source_text = utterance.text

    event_data["event_id"] = _stable_event_id(
        utterance.utterance_id,
        source_text,
        index,
    )
    event_data["utterance_id"] = utterance.utterance_id
    event_data["segment_id"] = utterance.segment_id
    event_data["speaker"] = utterance.speaker
    event_data["speaker_role"] = utterance.speaker_role
    event_data["start_time"] = utterance.start_time
    event_data["end_time"] = utterance.end_time
    event_data["source_text"] = source_text
    event_data["primary_intent"] = _normalize_intent(
        event_data.get("primary_intent")
    )

    secondary = event_data.get("secondary_intents")
    if not isinstance(secondary, list):
        secondary = []
    event_data["secondary_intents"] = [
        item for item in secondary if isinstance(item, str) and item in ALLOWED_INTENTS
    ]

    normalized_text = event_data.get("normalized_text")
    if not isinstance(normalized_text, str) or not normalized_text.strip():
        event_data["normalized_text"] = source_text

    evidence = event_data.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    evidence["source_text"] = source_text
    event_data["evidence"] = evidence

    return event_data


def _fallback_event(
    utterance: UtteranceInput,
    intent: SemanticIntent,
    confidence: float,
    needs_review: bool,
) -> SemanticEvent:
    return SemanticEvent(
        event_id=_stable_event_id(utterance.utterance_id, utterance.text, 0),
        utterance_id=utterance.utterance_id,
        segment_id=utterance.segment_id,
        speaker=utterance.speaker,
        speaker_role=utterance.speaker_role,
        start_time=utterance.start_time,
        end_time=utterance.end_time,
        source_text=utterance.text,
        normalized_text=utterance.text.strip(),
        primary_intent=intent,
        secondary_intents=[],
        event_type="unknown",
        subject=None,
        action=None,
        object=None,
        evidence={"source_text": utterance.text, "quote": utterance.text},
        confidence={
            "intent": confidence,
            "entity": confidence,
            "overall": confidence,
        },
        needs_review=needs_review,
    )


class SemanticEventExtractor:
    def __init__(
        self,
        llm_client: ChatClient | None = None,
    ):
        self.llm_client = llm_client or OllamaClient()
        self.prompt_template = _read_prompt_template()

    def build_prompt(
        self,
        utterance: UtteranceInput,
        repair_error: str | None = None,
    ) -> str:
        split_result = split_semantic_clauses(utterance.text)
        payload = {
            "current_utterance": {
                "utterance_id": utterance.utterance_id,
                "segment_id": utterance.segment_id,
                "speaker": utterance.speaker,
                "speaker_role": utterance.speaker_role,
                "start_time": utterance.start_time,
                "end_time": utterance.end_time,
                "source_text": utterance.text,
                "topic": utterance.topic,
            },
            "context": utterance.context[-3:],
            "candidate_clauses": split_result.clauses,
        }

        repair_block = ""
        if repair_error:
            repair_block = (
                "\n上一次输出不是合法 JSON 或不符合 Schema。"
                "请只修复 JSON，不改变系统提供字段。"
                f"\n错误信息：{repair_error}\n"
            )

        return (
            self.prompt_template
            + repair_block
            + "\n输入：\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    def extract(
        self,
        utterance: UtteranceInput,
    ) -> tuple[list[SemanticEvent], list[ValidationSummary]]:
        events, summaries, _ = self.extract_with_debug(utterance)
        return events, summaries

    def extract_with_debug(
        self,
        utterance: UtteranceInput,
    ) -> tuple[list[SemanticEvent], list[ValidationSummary], ExtractionDebug]:
        debug = ExtractionDebug()
        split_result = split_semantic_clauses(utterance.text)
        if split_result.is_pure_flow:
            event = _fallback_event(
                utterance,
                intent="non_event",
                confidence=0.95,
                needs_review=False,
            )
            events, summaries = validate_semantic_events([event], context=utterance.context)
            debug.bypass_reason = "pure_flow_non_event"
            debug.parsed_before_validation = [event.model_dump(mode="json")]
            debug.validated_after = [event.model_dump(mode="json") for event in events]
            return events, summaries, debug

        last_error = ""
        for attempt in range(2):
            prompt = self.build_prompt(
                utterance,
                repair_error=last_error if attempt else None,
            )
            try:
                print(
                    f"[SEMANTIC_EVENT] Extracting utterance={utterance.utterance_id} attempt={attempt + 1}"
                )
                raw_output = self.llm_client.chat(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                )
                debug.raw_output = raw_output
                debug.retry_count = attempt
                parsed = extract_json(raw_output)
                result = self._parse_result(parsed, utterance)
                debug.parsed_before_validation = [
                    event.model_dump(mode="json") for event in result.events
                ]
                events, summaries = validate_semantic_events(
                    result.events,
                    context=utterance.context,
                )
                debug.validated_after = [
                    event.model_dump(mode="json") for event in events
                ]
                return events, summaries, debug

            except (ValueError, ValidationError, RuntimeError) as exc:
                last_error = str(exc)
                debug.failure_reason = last_error
                print(
                    f"[SEMANTIC_EVENT] Extraction failed utterance={utterance.utterance_id} attempt={attempt + 1}: {last_error}"
                )

        print(f"[SEMANTIC_EVENT] Returning fallback event utterance={utterance.utterance_id}")
        fallback = _fallback_event(
            utterance,
            intent="information",
            confidence=0.0,
            needs_review=True,
        )
        events, summaries = validate_semantic_events([fallback], context=utterance.context)
        debug.validated_after = [event.model_dump(mode="json") for event in events]
        return events, summaries, debug

    def _parse_result(
        self,
        parsed: dict[str, Any],
        utterance: UtteranceInput,
    ) -> SemanticEventExtractionResult:
        raw_events = parsed.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raw_events = [
                {
                    "normalized_text": utterance.text,
                    "primary_intent": "information",
                    "event_type": "unknown",
                    "evidence": {"source_text": utterance.text, "quote": utterance.text},
                    "confidence": {"intent": 0.0, "entity": 0.0, "overall": 0.0},
                    "needs_review": True,
                }
            ]

        forced_events = [
            _force_system_fields(dict(event_data), utterance, index)
            for index, event_data in enumerate(raw_events[:3])
            if isinstance(event_data, dict)
        ]

        return SemanticEventExtractionResult.model_validate({"events": forced_events})


def extract_semantic_events(
    utterance: UtteranceInput,
    llm_client: ChatClient | None = None,
) -> tuple[list[SemanticEvent], list[ValidationSummary]]:
    extractor = SemanticEventExtractor(llm_client=llm_client)
    return extractor.extract(utterance)
