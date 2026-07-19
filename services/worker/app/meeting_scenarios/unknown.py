from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="unknown",
    display_name="未知会议类型",
    description="无法可靠识别会议场景时使用的安全默认策略。",
    focus_entities=(
        "action_item",
        "issue",
        "risk",
    ),
    validation_rules=(
        "未知会议类型必须进入人工复核。",
        "不得依据 unknown 策略自动修改项目状态。",
        "不得加载大量历史上下文或敏感上下文。",
        "不得生成高风险动作建议。",
    ),
    allowed_actions=(
        "create_action_item",
        "create_issue",
        "create_risk",
        "generate_next_meeting_agenda",
    ),
    classification_hints=(
        "无法识别",
        "未知会议",
    ),
    needs_review=True,
)
