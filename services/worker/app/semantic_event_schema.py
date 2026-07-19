from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =============================================================================
# 类型定义
# =============================================================================

IntentType = Literal[
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
]


EventType = Literal[
    "action",
    "state",
    "question",
    "decision",
    "risk",
    "information",
]


EventStatus = Literal[
    "proposed",
    "discussing",
    "confirmed",
    "rejected",
    "completed",
    "pending",
    "blocked",
    "cancelled",
    "unknown",
]


CertaintyType = Literal[
    "explicit",
    "contextual",
    "inferred",
    "unknown",
]


PolarityType = Literal[
    "positive",
    "negative",
    "neutral",
]


EvidenceType = Literal[
    "direct",
    "contextual",
]


# =============================================================================
# event_type 与 intent 映射
# =============================================================================

EVENT_TYPE_NORMALIZATION: dict[str, EventType] = {
    # 合法 event_type
    "action": "action",
    "state": "state",
    "question": "question",
    "decision": "decision",
    "risk": "risk",
    "information": "information",

    # primary_intent 被模型错误写入 event_type
    "agenda_statement": "information",
    "progress_update": "state",
    "proposal": "action",
    "commitment": "action",
    "task_assignment": "action",
    "open_issue": "state",
    "risk_warning": "risk",
    "requirement": "action",
    "rejection": "action",
    "non_event": "information",

    # status 被模型错误写入 event_type
    "proposed": "action",
    "discussing": "state",
    "confirmed": "decision",
    "rejected": "action",
    "completed": "state",
    "pending": "state",
    "blocked": "state",
    "cancelled": "state",
    "unknown": "information",
}


INTENT_TO_EVENT_TYPE: dict[str, EventType] = {
    "agenda_statement": "information",
    "progress_update": "state",
    "decision": "decision",
    "proposal": "action",
    "commitment": "action",
    "task_assignment": "action",
    "question": "question",
    "open_issue": "state",
    "risk_warning": "risk",
    "requirement": "action",
    "rejection": "action",
    "information": "information",
    "non_event": "information",
}


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


INTENT_ALIASES: dict[str, str] = {
    "agenda": "agenda_statement",
    "meeting_agenda": "agenda_statement",
    "progress": "progress_update",
    "status_update": "progress_update",
    "task": "task_assignment",
    "assignment": "task_assignment",
    "assign_task": "task_assignment",
    "risk": "risk_warning",
    "warning": "risk_warning",
    "issue": "open_issue",
    "open_question": "open_issue",
    "unresolved_issue": "open_issue",
    "fact": "information",
    "normal_information": "information",
    "none": "non_event",
    "flow": "non_event",
    "no_event": "non_event",
}


# =============================================================================
# 子模型
# =============================================================================

class SemanticEntities(BaseModel):
    """语义事件中识别出的实体。"""

    model_config = ConfigDict(extra="ignore")

    persons: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)

    @field_validator(
        "persons",
        "teams",
        "projects",
        "features",
        "dates",
        "versions",
        "numbers",
        mode="before",
    )
    @classmethod
    def normalize_entity_list(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []

        if isinstance(value, (list, tuple, set)):
            result: list[str] = []

            for item in value:
                if item is None:
                    continue

                text = str(item).strip()

                if text and text not in result:
                    result.append(text)

            return result

        return []


class EventAttributes(BaseModel):
    """事件属性。"""

    model_config = ConfigDict(extra="ignore")

    owner: str | None = None
    deadline: str | None = None
    priority: str | None = None

    status: EventStatus = "unknown"
    polarity: PolarityType = "neutral"
    certainty: CertaintyType = "unknown"

    @field_validator("owner", "deadline", "priority", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        if not text or text.lower() in {
            "null",
            "none",
            "unknown",
            "未知",
            "未明确",
            "无",
        }:
            return None

        return text

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> EventStatus:
        if value is None:
            return "unknown"

        normalized = str(value).strip().lower()

        allowed_statuses: set[str] = {
            "proposed",
            "discussing",
            "confirmed",
            "rejected",
            "completed",
            "pending",
            "blocked",
            "cancelled",
            "unknown",
        }

        if normalized in allowed_statuses:
            return normalized  # type: ignore[return-value]

        aliases: dict[str, EventStatus] = {
            "proposal": "proposed",
            "suggested": "proposed",
            "discussion": "discussing",
            "in_discussion": "discussing",
            "confirm": "confirmed",
            "approved": "confirmed",
            "done": "completed",
            "complete": "completed",
            "finished": "completed",
            "in_progress": "pending",
            "in progress": "pending",
            "waiting": "pending",
            "block": "blocked",
            "reject": "rejected",
            "cancel": "cancelled",
            "canceled": "cancelled",
        }

        return aliases.get(normalized, "unknown")

    @field_validator("polarity", mode="before")
    @classmethod
    def normalize_polarity(cls, value: Any) -> PolarityType:
        if value is None:
            return "neutral"

        normalized = str(value).strip().lower()

        if normalized in {"positive", "negative", "neutral"}:
            return normalized  # type: ignore[return-value]

        aliases: dict[str, PolarityType] = {
            "正向": "positive",
            "积极": "positive",
            "负向": "negative",
            "消极": "negative",
            "否定": "negative",
            "中性": "neutral",
        }

        return aliases.get(normalized, "neutral")

    @field_validator("certainty", mode="before")
    @classmethod
    def normalize_certainty(cls, value: Any) -> CertaintyType:
        if value is None:
            return "unknown"

        normalized = str(value).strip().lower()

        if normalized in {
            "explicit",
            "contextual",
            "inferred",
            "unknown",
        }:
            return normalized  # type: ignore[return-value]

        aliases: dict[str, CertaintyType] = {
            "direct": "explicit",
            "明确": "explicit",
            "显式": "explicit",
            "context": "contextual",
            "上下文": "contextual",
            "推断": "inferred",
            "inference": "inferred",
        }

        return aliases.get(normalized, "unknown")


class EventEvidence(BaseModel):
    """语义事件的原文证据。"""

    model_config = ConfigDict(extra="ignore")

    source_text: str = ""
    quote: str | None = None
    evidence_type: EvidenceType = "direct"

    @field_validator("source_text", mode="before")
    @classmethod
    def normalize_source_text(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value)

    @field_validator("quote", mode="before")
    @classmethod
    def normalize_quote(cls, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        if not text or text.lower() in {"null", "none"}:
            return None

        return text

    @field_validator("evidence_type", mode="before")
    @classmethod
    def normalize_evidence_type(cls, value: Any) -> EvidenceType:
        if value is None:
            return "direct"

        normalized = str(value).strip().lower()

        if normalized in {"contextual", "context"}:
            return "contextual"

        return "direct"


class EventConfidence(BaseModel):
    """模型置信度。"""

    model_config = ConfigDict(extra="ignore")

    intent: float = Field(default=0.0, ge=0.0, le=1.0)
    entity: float = Field(default=0.0, ge=0.0, le=1.0)
    overall: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("intent", "entity", "overall", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0

        if result < 0.0:
            return 0.0

        if result > 1.0:
            return 1.0

        return result


# =============================================================================
# 主事件模型
# =============================================================================

class SemanticEvent(BaseModel):
    """
    单条句子级语义事件。

    注意：

    primary_intent:
        表示会议业务意图。

    event_type:
        表示通用事件形态。

    attributes.status:
        表示事件当前状态。
    """

    # 不启用 validate_assignment。
    # 否则 after model_validator 中修改字段时可能反复触发校验，
    # 从而造成 RecursionError。
    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=False,
    )

    event_id: str = ""
    utterance_id: str = ""
    segment_id: str | None = None

    speaker: str | None = None
    speaker_role: str | None = None

    start_time: float | None = None
    end_time: float | None = None

    source_text: str = ""
    normalized_text: str = ""

    primary_intent: IntentType = "information"
    secondary_intents: list[IntentType] = Field(default_factory=list)

    event_type: EventType = "information"

    subject: str | None = None
    action: str | None = None
    object: str | None = None

    entities: SemanticEntities = Field(default_factory=SemanticEntities)
    attributes: EventAttributes = Field(default_factory=EventAttributes)
    evidence: EventEvidence = Field(default_factory=EventEvidence)
    confidence: EventConfidence = Field(default_factory=EventConfidence)

    needs_review: bool = False

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: Any) -> EventType:
        """
        在 Literal 校验前修复模型常见输出错误。

        例如：

        agenda_statement -> information
        progress_update  -> state
        proposal         -> action
        proposed         -> action
        confirmed        -> decision
        """
        if value is None:
            return "information"

        normalized = str(value).strip().lower()

        return EVENT_TYPE_NORMALIZATION.get(
            normalized,
            "information",
        )

    @field_validator("primary_intent", mode="before")
    @classmethod
    def normalize_primary_intent(cls, value: Any) -> str:
        if value is None:
            return "information"

        normalized = str(value).strip().lower()
        normalized = INTENT_ALIASES.get(normalized, normalized)

        if normalized not in ALLOWED_INTENTS:
            return "information"

        return normalized

    @field_validator("secondary_intents", mode="before")
    @classmethod
    def normalize_secondary_intents(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            raw_values = [value]

        elif isinstance(value, (list, tuple, set)):
            raw_values = list(value)

        else:
            return []

        result: list[str] = []

        for item in raw_values:
            if item is None:
                continue

            intent = str(item).strip().lower()
            intent = INTENT_ALIASES.get(intent, intent)

            if intent not in ALLOWED_INTENTS:
                continue

            if intent not in result:
                result.append(intent)

        return result

    @field_validator(
        "source_text",
        "normalized_text",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value)

    @field_validator(
        "event_id",
        "utterance_id",
        mode="before",
    )
    @classmethod
    def normalize_required_ids(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()

    @field_validator(
        "segment_id",
        "speaker",
        "speaker_role",
        "subject",
        "action",
        "object",
        mode="before",
    )
    @classmethod
    def normalize_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        if not text or text.lower() in {
            "null",
            "none",
            "unknown",
        }:
            return None

        return text

    @model_validator(mode="after")
    def normalize_semantic_consistency(self) -> "SemanticEvent":
        """
        执行跨字段归一化。

        validate_assignment 已关闭，因此这里的赋值不会递归触发
        model_validator。
        """

        # 去掉与主意图相同的辅助意图。
        normalized_secondary: list[IntentType] = []

        for intent in self.secondary_intents:
            if intent == self.primary_intent:
                continue

            if intent not in normalized_secondary:
                normalized_secondary.append(intent)

        self.secondary_intents = normalized_secondary

        # 根据 primary_intent 强制统一 event_type。
        expected_event_type = INTENT_TO_EVENT_TYPE.get(
            self.primary_intent,
            "information",
        )

        if self.event_type != expected_event_type:
            self.event_type = expected_event_type
            self.needs_review = True

        # 根据主意图补充基础状态。
        if (
            self.primary_intent == "proposal"
            and self.attributes.status == "unknown"
        ):
            self.attributes.status = "proposed"

        elif (
            self.primary_intent == "decision"
            and self.attributes.status == "unknown"
        ):
            self.attributes.status = "confirmed"

        elif (
            self.primary_intent == "rejection"
            and self.attributes.status == "unknown"
        ):
            self.attributes.status = "rejected"

        elif self.primary_intent == "question":
            if self.attributes.status == "unknown":
                self.attributes.status = "discussing"

        elif self.primary_intent == "non_event":
            self.event_type = "information"
            self.attributes.status = "unknown"

        # normalized_text 缺失时使用 source_text。
        if not self.normalized_text:
            self.normalized_text = self.source_text

        # evidence.source_text 缺失时使用 source_text。
        if not self.evidence.source_text:
            self.evidence.source_text = self.source_text

        # quote 必须存在于 source_text，否则清空。
        if (
            self.evidence.quote
            and self.evidence.quote not in self.source_text
        ):
            self.evidence.quote = None
            self.needs_review = True

        # 低置信度进入人工复核。
        if self.confidence.overall < 0.7:
            self.needs_review = True

        return self


# =============================================================================
# 提取结果
# =============================================================================

class SemanticEventExtractionResult(BaseModel):
    """一条 utterance 的语义事件提取结果。"""

    model_config = ConfigDict(extra="ignore")

    utterance_id: str = ""
    events: list[SemanticEvent] = Field(default_factory=list)

    @field_validator("utterance_id", mode="before")
    @classmethod
    def normalize_utterance_id(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()

    @field_validator("events", mode="before")
    @classmethod
    def normalize_events(cls, value: Any) -> list[Any]:
        if value is None:
            return []

        if isinstance(value, dict):
            return [value]

        if isinstance(value, (list, tuple)):
            return list(value)

        return []

    @model_validator(mode="after")
    def normalize_result(self) -> "SemanticEventExtractionResult":
        # 每条 utterance 最多保留3个事件。
        if len(self.events) > 3:
            self.events = self.events[:3]

        # 补充事件的 utterance_id。
        for event in self.events:
            if not event.utterance_id:
                event.utterance_id = self.utterance_id

        return self


# =============================================================================
# 提取器输入
# =============================================================================

class UtteranceInput(BaseModel):
    """语义事件提取器的标准输入。"""

    model_config = ConfigDict(extra="allow")

    utterance_id: str
    segment_id: str | None = None

    speaker: str | None = None
    speaker_role: str | None = None

    start_time: float | None = None
    end_time: float | None = None

    text: str

    previous_utterances: list[str] = Field(default_factory=list)
    topic: str | None = None
    candidate_clauses: list[str] = Field(default_factory=list)

    @field_validator("utterance_id", "text", mode="before")
    @classmethod
    def normalize_input_required_text(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value)

    @field_validator(
        "previous_utterances",
        "candidate_clauses",
        mode="before",
    )
    @classmethod
    def normalize_input_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            value = [value]

        if not isinstance(value, (list, tuple)):
            return []

        result: list[str] = []

        for item in value:
            if item is None:
                continue

            text = str(item).strip()

            if text:
                result.append(text)

        return result


# =============================================================================
# 兼容旧代码使用的名称
# =============================================================================

# 新旧类型名称兼容
SemanticIntent = IntentType
SemanticEventType = EventType
SemanticEventStatus = EventStatus
SemanticCertainty = CertaintyType
SemanticPolarity = PolarityType
SemanticEvidenceType = EvidenceType

# 新旧模型名称兼容
SemanticEventResult = SemanticEventExtractionResult
SemanticEventEntities = SemanticEntities
SemanticEventAttributes = EventAttributes
SemanticEventEvidence = EventEvidence
SemanticEventConfidence = EventConfidence


__all__ = [
    # 当前类型名称
    "IntentType",
    "EventType",
    "EventStatus",
    "CertaintyType",
    "PolarityType",
    "EvidenceType",

    # 旧代码兼容名称
    "SemanticIntent",
    "SemanticEventType",
    "SemanticEventStatus",
    "SemanticCertainty",
    "SemanticPolarity",
    "SemanticEvidenceType",

    # 映射配置
    "EVENT_TYPE_NORMALIZATION",
    "INTENT_TO_EVENT_TYPE",

    # 当前模型
    "SemanticEntities",
    "EventAttributes",
    "EventEvidence",
    "EventConfidence",
    "SemanticEvent",
    "SemanticEventExtractionResult",
    "UtteranceInput",

    # 旧模型兼容名称
    "SemanticEventResult",
    "SemanticEventEntities",
    "SemanticEventAttributes",
    "SemanticEventEvidence",
    "SemanticEventConfidence",
]