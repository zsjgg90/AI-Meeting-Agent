from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="management_decision",
    display_name="管理决策会",
    description="记录管理层决策、项目健康度影响、风险和后续执行事项。",
    optional_context=(
        "decisions",
        "project_state",
        "active_risks",
        "open_issues",
    ),
    focus_entities=(
        "decision",
        "risk",
        "action_item",
        "issue",
        "project_state",
    ),
    validation_rules=(
        "管理意见、建议和正式决策必须区分。",
        "项目健康度变更必须保留明确决策证据。",
        "关闭重大风险必须经过人工确认。",
        "修改负责人必须经过人工确认。",
        "对外发送或发布决定必须经过人工确认。",
    ),
    allowed_actions=(
        "create_decision_record",
        "create_action_item",
        "update_action_item",
        "create_risk",
        "update_risk_level",
        "create_issue",
        "resolve_issue",
        "update_project_health",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "create_decision_record",
        "update_action_item",
        "update_risk_level",
        "resolve_issue",
        "update_project_health",
    ),
    classification_hints=(
        "管理决策",
        "项目健康度",
        "重大风险",
        "负责人调整",
    ),
)
