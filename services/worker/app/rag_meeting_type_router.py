from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RagMeetingTypeRoute:
    meeting_type: str
    scenario: str
    score: int
    matched_keywords: list[str]


ROUTE_RULES: dict[str, dict[str, object]] = {
    "technical_incident": {
        "scenario": "technical_incident",
        "keywords": [
            "线上故障",
            "线上事故",
            "生产故障",
            "技术故障",
            "接口超时",
            "服务不可用",
            "系统异常",
            "宕机",
            "告警",
            "根因",
            "故障复盘",
            "事故复盘",
            "恢复服务",
            "应急处理",
        ],
    },
    "requirement_review": {
        "scenario": "requirement_review",
        "keywords": [
            "需求评审",
            "需求确认",
            "需求范围",
            "验收标准",
            "产品需求",
            "功能需求",
            "需求变更",
            "需求方案",
            "原型评审",
            "交互评审",
        ],
    },
    "project_weekly": {
        "scenario": "project_weekly",
        "keywords": [
            "项目周会",
            "项目周报",
            "本周进度",
            "下周计划",
            "进度同步",
            "项目进度",
            "任务进展",
            "联调进度",
            "测试进度",
            "开发进度",
            "延期风险",
        ],
    },
    "technical_review": {
        "scenario": "technical_review",
        "keywords": [
            "技术评审",
            "方案评审",
            "架构评审",
            "技术方案",
            "接口方案",
            "数据库设计",
            "系统架构",
            "技术选型",
        ],
    },
    "project_retrospective": {
        "scenario": "project_retrospective",
        "keywords": [
            "项目复盘",
            "迭代复盘",
            "阶段复盘",
            "经验总结",
            "问题复盘",
            "复盘会议",
        ],
    },
    "release_planning": {
        "scenario": "release_planning",
        "keywords": [
            "发布计划",
            "上线计划",
            "版本发布",
            "发版计划",
            "上线评审",
            "发布评审",
            "灰度发布",
        ],
    },
    "customer_requirement": {
        "scenario": "customer_requirement",
        "keywords": [
            "客户需求",
            "客户沟通",
            "客户反馈",
            "客户提出",
            "客户验收",
            "商务需求",
        ],
    },
}

ROUTE_RULES.update(
    {
        "management_decision": {
            "scenario": "management_decision",
            "keywords": [
                "management_decision",
                "management decision",
                "decision meeting",
            ],
        },
        "cross_team_coordination": {
            "scenario": "cross_team_coordination",
            "keywords": [
                "cross_team_coordination",
                "cross team coordination",
                "cross-team coordination",
            ],
        },
        "cross_department": {
            "scenario": "cross_team_coordination",
            "keywords": [
                "cross_department",
                "cross department",
                "cross-department",
            ],
        },
        "incident_review": {
            "scenario": "technical_incident",
            "keywords": [
                "incident_review",
                "incident review",
            ],
        },
    }
)


def route_rag_meeting_type(
    transcript: str,
) -> RagMeetingTypeRoute | None:
    text = str(transcript or "").strip()
    if not text:
        return None

    candidates: list[RagMeetingTypeRoute] = []

    for meeting_type, rule in ROUTE_RULES.items():
        scenario = str(rule["scenario"])
        keywords = [
            str(keyword)
            for keyword in rule["keywords"]
        ]

        matched_keywords = [
            keyword
            for keyword in keywords
            if keyword in text
        ]

        if not matched_keywords:
            continue

        score = sum(
            2 if len(keyword) >= 4 else 1
            for keyword in matched_keywords
        )

        candidates.append(
            RagMeetingTypeRoute(
                meeting_type=meeting_type,
                scenario=scenario,
                score=score,
                matched_keywords=matched_keywords,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            -item.score,
            -len(item.matched_keywords),
            item.meeting_type,
        )
    )

    best = candidates[0]

    if len(candidates) > 1:
        second = candidates[1]
        if (
            best.score == second.score
            and len(best.matched_keywords)
            == len(second.matched_keywords)
        ):
            return None

    return best
