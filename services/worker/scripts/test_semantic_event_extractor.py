from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(WORKER_ROOT),
    )

from app.semantic_event_extractor import (  # noqa: E402
    SemanticEventExtractor,
)
from app.semantic_event_schema import (  # noqa: E402
    UtteranceInput,
)


class FakeSemanticEventClient:
    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        payload = json.loads(
            prompt[prompt.rfind('"current_utterance"') - 4 : prompt.rfind("}") + 1]
        )
        utterance = payload["current_utterance"]
        text = utterance["source_text"]
        return json.dumps(
            {
                "events": self._events_for_text(text),
            },
            ensure_ascii=False,
        )

    def _base_event(
        self,
        text: str,
        primary_intent: str,
        status: str,
        owner: str | None = None,
        deadline: str | None = None,
        confidence: float = 0.82,
    ) -> dict[str, Any]:
        return {
            "normalized_text": text.replace("嗯，", "").replace("那个", ""),
            "primary_intent": primary_intent,
            "secondary_intents": [],
            "event_type": status,
            "subject": None,
            "action": None,
            "object": None,
            "entities": {
                "persons": [owner] if owner else [],
                "teams": [],
                "projects": [],
                "features": [],
                "dates": [deadline] if deadline else [],
                "versions": [],
                "numbers": [],
            },
            "attributes": {
                "owner": owner,
                "deadline": deadline,
                "priority": "high" if "高优" in text or "重点" in text else "unknown",
                "status": status,
                "polarity": "neutral",
                "certainty": "explicit" if confidence >= 0.8 else "contextual",
            },
            "evidence": {
                "source_text": text,
                "quote": text,
            },
            "confidence": {
                "intent": confidence,
                "entity": confidence,
                "overall": confidence,
            },
            "needs_review": confidence < 0.7,
        }

    def _events_for_text(
        self,
        text: str,
    ) -> list[dict[str, Any]]:
        if "今天主要讨论" in text:
            return [self._base_event(text, "agenda_statement", "discussing")]
        if "已经完成" in text:
            return [self._base_event(text, "progress_update", "completed")]
        if "完成了接口开发" in text:
            return [self._base_event(text, "progress_update", "completed")]
        if "还没完成" in text or "没有完成" in text:
            return [self._base_event(text, "progress_update", "pending")]
        if "决定" in text or "就这么定" in text:
            return [self._base_event(text, "decision", "confirmed")]
        if "大概" in text or "可能吧" in text:
            return [self._base_event(text, "information", "unknown", confidence=0.45)]
        if "建议" in text or "是不是可以" in text or "我觉得" in text:
            return [self._base_event(text, "decision", "confirmed")]
        if "你来负责" in text:
            return [self._base_event(text, "task_assignment", "confirmed", owner="张明")]
        if "我来负责" in text:
            return [self._base_event(text, "commitment", "confirmed", owner="我")]
        if "周五前" in text:
            return [self._base_event(text, "task_assignment", "confirmed", deadline="周五前")]
        if "吗" in text or "有没有" in text:
            return [self._base_event(text, "question", "discussing")]
        if "暂时没有方案" in text:
            return [self._base_event(text, "open_issue", "blocked")]
        if "风险" in text or "如果" in text:
            return [self._base_event(text, "risk_warning", "pending")]
        if "不做" in text or "不上线" in text:
            return [self._base_event(text, "rejection", "rejected")]
        if "需要" in text:
            return [self._base_event(text, "requirement", "confirmed")]
        if "同时" in text:
            return [
                self._base_event(text, "decision", "confirmed"),
                self._base_event(text, "task_assignment", "confirmed", owner="产品"),
            ]
        return [self._base_event(text, "information", "unknown")]


TEST_CASES = [
    "今天主要讨论 V2.0 的需求范围和上线节奏。",
    "我这边登录接口已经完成，联调也通过了。",
    "前端页面还没完成，预计还需要两天。",
    "我们决定本次不做个性化推荐。",
    "建议先把下载失败的问题优先解决。",
    "是不是可以把筛选入口放到首页？",
    "张明，你来负责补充默认标签分组规则。",
    "我来负责整理竞品素材和人群包数据。",
    "周五前需要完成灰度发布方案。",
    "这个接口有没有缓存兼容问题？",
    "数据迁移方案暂时没有方案，需要后续确认。",
    "如果旧数据映射失败，可能会导致返工风险。",
    "本次智能推荐不上线，等数据体系补齐后再看。",
    "需要支持批量下载失败后的自动重试。",
    "嗯，那个目前用户主要反馈入口太深。",
    "我们确认冻结需求，同时产品补充验收清单。",
    "这个可能吧，我觉得还要再看一下。",
    "后台任务已经跑完，报告也发给测试了。",
    "测试环境没有完成部署，联调被阻塞。",
    "普通说明一下，明天上午会有例行维护通知。",
]


def run(
    live: bool,
    limit: int | None = None,
) -> None:
    extractor = (
        SemanticEventExtractor()
        if live
        else SemanticEventExtractor(llm_client=FakeSemanticEventClient())
    )

    context: list[str] = []

    cases = TEST_CASES[:limit] if limit else TEST_CASES

    for index, text in enumerate(cases, start=1):
        utterance = UtteranceInput(
            utterance_id=f"utt_{index:03d}",
            segment_id=f"seg_{index:03d}",
            speaker=f"speaker_{index % 3}",
            speaker_role=None,
            start_time=float(index * 3),
            end_time=float(index * 3 + 2),
            text=text,
            topic="需求评审",
            context=context[-3:],
        )

        events, validation_summaries = extractor.extract(utterance)

        print(f"\nCASE {index:02d}")
        print(f"输入句子: {text}")

        for event_index, event in enumerate(events, start=1):
            summary = validation_summaries[event_index - 1]
            print(f"  Event {event_index}")
            print(f"  primary_intent: {event.primary_intent}")
            print(f"  owner: {event.attributes.owner}")
            print(f"  deadline: {event.attributes.deadline}")
            print(f"  status: {event.attributes.status}")
            print(f"  confidence: {event.confidence.overall:.2f}")
            print(f"  needs_review: {event.needs_review}")
            print("  Schema 是否通过: 是")
            print(f"  Validator 是否修改结果: {'是' if summary.changed else '否'}")
            if summary.reasons:
                print(f"  Validator 修改原因: {', '.join(summary.reasons)}")

        context.append(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call configured Ollama model instead of fake test client.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of test cases.",
    )
    args = parser.parse_args()
    run(
        live=args.live,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
