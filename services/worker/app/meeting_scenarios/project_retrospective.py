from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="project_retrospective",
    display_name="项目复盘会",
    description="复盘项目事实、问题、风险、根因假设和改进措施。",
    optional_context=(
        "previous_meetings",
        "open_issues",
        "active_risks",
        "decisions",
    ),
    focus_entities=(
        "issue",
        "risk",
        "action_item",
        "decision",
    ),
    validation_rules=(
        "事实、观点、假设、根因和建议必须区分。",
        "Agent 不得自行确认根因。",
        "推测原因必须标记为需复核。",
        "改进措施必须与问题证据关联。",
    ),
    allowed_actions=(
        "create_issue",
        "resolve_issue",
        "create_risk",
        "create_action_item",
        "create_decision_record",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "resolve_issue",
        "create_decision_record",
    ),
    classification_hints=(
        "复盘",
        "根因",
        "经验教训",
        "改进措施",
    ),
)
