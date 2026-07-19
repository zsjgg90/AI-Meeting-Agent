from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="requirement_review",
    display_name="需求评审会",
    description="评审候选需求、确认边界、识别待澄清问题和后续行动。",
    optional_context=(
        "requirements",
        "decisions",
        "milestones",
        "project_knowledge",
    ),
    focus_entities=(
        "requirement",
        "decision",
        "action_item",
        "issue",
        "risk",
    ),
    validation_rules=(
        "建议不等于正式确认。",
        "提问不等于决策。",
        "后续评估不得识别为确认需求。",
        "未明确版本和日期不得推断。",
        "延期和取消必须区分。",
    ),
    allowed_actions=(
        "create_requirement",
        "update_requirement_status",
        "create_decision_record",
        "create_action_item",
        "create_issue",
        "create_risk",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "update_requirement_status",
        "create_decision_record",
    ),
    classification_hints=(
        "需求评审",
        "PRD",
        "验收标准",
        "需求范围",
    ),
)
