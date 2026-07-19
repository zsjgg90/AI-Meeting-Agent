from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="technical_review",
    display_name="技术方案评审",
    description="评审技术候选方案、记录决策依据、风险和待验证事项。",
    optional_context=(
        "decisions",
        "project_knowledge",
        "active_risks",
    ),
    focus_entities=(
        "decision",
        "risk",
        "action_item",
        "issue",
    ),
    validation_rules=(
        "Agent 不得自行选择方案。",
        "候选方案不等于最终方案。",
        "建议、偏好和正式决定必须区分。",
        "性能假设不得当作已验证事实。",
    ),
    allowed_actions=(
        "create_decision_record",
        "create_risk",
        "update_risk_level",
        "create_action_item",
        "create_issue",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "create_decision_record",
        "update_risk_level",
    ),
    classification_hints=(
        "技术方案",
        "架构评审",
        "候选方案",
        "性能假设",
    ),
)
