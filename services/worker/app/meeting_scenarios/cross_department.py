from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="cross_department",
    display_name="跨部门协调会",
    description="协调团队间任务、依赖、问题和风险传导。",
    required_context=(
        "previous_meetings",
        "open_action_items",
        "dependencies",
        "open_issues",
        "active_risks",
    ),
    focus_entities=(
        "action_item",
        "dependency",
        "issue",
        "risk",
    ),
    validation_rules=(
        "上游任务和下游任务必须分别建模。",
        "依赖关系必须有明确语言证据。",
        "团队责任不能自动映射到个人负责人。",
        "风险传导不能替代明确任务状态。",
    ),
    allowed_actions=(
        "create_action_item",
        "update_action_item",
        "defer_action_item",
        "create_dependency",
        "create_issue",
        "resolve_issue",
        "create_risk",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "update_action_item",
        "create_dependency",
    ),
    classification_hints=(
        "跨部门",
        "依赖协调",
        "上游",
        "下游",
    ),
)
