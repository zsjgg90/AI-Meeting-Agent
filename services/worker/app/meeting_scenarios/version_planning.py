from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="version_planning",
    display_name="版本规划会",
    description="规划版本范围、里程碑、依赖、风险和后续行动。",
    optional_context=(
        "requirements",
        "milestones",
        "dependencies",
        "open_action_items",
        "active_risks",
        "project_state",
    ),
    focus_entities=(
        "requirement",
        "milestone",
        "action_item",
        "risk",
        "dependency",
    ),
    validation_rules=(
        "建议进入版本不等于已确认。",
        "目标日期不等于正式发布日期。",
        "资源不足属于风险或问题，不自动修改排期。",
        "延期需求必须保留原状态依据。",
    ),
    allowed_actions=(
        "update_requirement_status",
        "create_milestone",
        "update_milestone",
        "create_action_item",
        "create_risk",
        "create_dependency",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "update_requirement_status",
        "create_milestone",
        "update_milestone",
    ),
    classification_hints=(
        "版本规划",
        "里程碑",
        "排期",
        "发布范围",
    ),
)
