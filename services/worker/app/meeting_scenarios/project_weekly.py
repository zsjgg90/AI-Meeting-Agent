from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="project_weekly",
    display_name="项目周会",
    description="跟踪项目进展、开放事项、阻塞、风险和里程碑状态。",
    required_context=(
        "previous_same_type_meeting",
        "open_action_items",
        "active_risks",
        "open_issues",
        "milestones",
        "project_state",
    ),
    focus_entities=(
        "action_item",
        "issue",
        "risk",
        "milestone",
        "project_state",
    ),
    validation_rules=(
        "准备做不等于已完成。",
        "没有明确负责人不得推断。",
        "没有明确截止时间不得推断。",
        "阻塞与风险必须区分。",
        "下周计划不能标记为当前完成事项。",
    ),
    allowed_actions=(
        "create_action_item",
        "update_action_item",
        "complete_action_item",
        "defer_action_item",
        "create_issue",
        "resolve_issue",
        "create_risk",
        "update_risk_level",
        "update_milestone",
        "generate_next_meeting_agenda",
        "update_project_health",
    ),
    confirmation_required_actions=(
        "complete_action_item",
        "update_project_health",
    ),
    classification_hints=(
        "周会",
        "进展同步",
        "本周完成",
        "下周计划",
    ),
)
