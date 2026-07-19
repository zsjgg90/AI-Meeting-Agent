from __future__ import annotations

from app.meeting_scenarios.base import create_policy


POLICY = create_policy(
    meeting_type="customer_requirement",
    display_name="客户需求沟通会",
    description="记录客户需求、期望、商业风险、内部跟进行动和开放问题。",
    optional_context=(
        "customer_requests",
        "requirements",
        "previous_meetings",
        "project_knowledge",
    ),
    focus_entities=(
        "customer_request",
        "requirement",
        "risk",
        "action_item",
        "issue",
    ),
    validation_rules=(
        "客户期望不等于我方承诺。",
        "客户强烈要求不等于正式截止时间。",
        "询问开发周期不等于已确认排期。",
        "可能不续约应识别为商业风险，不是确定事实。",
        "客户需求与内部正式需求必须分开建模。",
    ),
    allowed_actions=(
        "create_requirement",
        "create_action_item",
        "create_issue",
        "create_risk",
        "generate_next_meeting_agenda",
    ),
    confirmation_required_actions=(
        "create_requirement",
    ),
    classification_hints=(
        "客户需求",
        "客户期望",
        "续约",
        "交付承诺",
    ),
)
