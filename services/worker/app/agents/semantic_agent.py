from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.models import TranscriptSegment


@dataclass(frozen=True)
class SemanticEvent:
    event_type: str
    speaker_label: str | None
    start_time: float
    end_time: float
    text: str
    confidence: float


DECISION_HINTS = ("决定", "决议", "确认", "敲定", "通过", "同意", "定下来", "结论", "冻结", "取消", "上线")
TASK_HINTS = ("负责", "跟进", "完成", "提交", "安排", "处理", "推进", "输出", "对接", "配合", "截止")
RISK_HINTS = ("风险", "问题", "阻塞", "延期", "依赖", "不确定", "返工", "丢失", "压力", "投诉", "崩溃")
REQUIREMENT_HINTS = ("需求", "希望", "需要", "支持", "功能", "优化", "重构", "适配", "迁移")
QUESTION_HINTS = ("是否", "能否", "吗", "么", "如何", "为什么", "什么", "排期", "方案")


def classify_text(text: str) -> tuple[str, float] | None:
    if any(hint in text for hint in DECISION_HINTS):
        return "decision", 0.78
    if any(hint in text for hint in TASK_HINTS):
        return "task", 0.72
    if any(hint in text for hint in RISK_HINTS):
        return "risk", 0.7
    if text.endswith(("?", "？")) or any(hint in text for hint in QUESTION_HINTS):
        return "question", 0.66
    if any(hint in text for hint in REQUIREMENT_HINTS):
        return "requirement", 0.64
    return None


class SemanticAgent:
    name = "semantic"

    def run(self, db: Session, meeting_id: str, segments: list[TranscriptSegment]) -> tuple[list[SemanticEvent], AgentResult]:
        events: list[SemanticEvent] = []
        for segment in segments:
            classification = classify_text(segment.text)
            if classification is None:
                continue
            event_type, confidence = classification
            events.append(
                SemanticEvent(
                    event_type=event_type,
                    speaker_label=segment.speaker_label,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    text=segment.text,
                    confidence=confidence,
                )
            )

        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1

        return (
            events,
            AgentResult(
                agent=self.name,
                status="completed",
                data={"event_count": len(events), "event_counts": counts},
            ),
        )
