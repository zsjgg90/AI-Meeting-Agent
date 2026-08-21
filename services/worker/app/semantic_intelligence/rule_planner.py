from .schemas import RulePlan



def build_rule_plan(
    context: dict,
    boundary: dict
) -> RulePlan:
    """
    Rule Planner（规则规划器）

    根据语义状态决定：
    RAG（检索增强生成）应该寻找什么规则
    """



    event_type = context.get(
        "event_type",
        ""
    )


    boundary_type = boundary.get(
        "boundary_type",
        ""
    )



    query_intent = "general_analysis"


    rule_domains = []

    dimension = "general"


    keywords = []



    # =========================
    # Decision（决策）
    # =========================


    if boundary_type == (
        "proposal_not_decision"
    ):


        query_intent = (
            "prevent_false_decision"
        )


        rule_domains = [

            "decision_boundary",

            "negative_examples"

        ]


        dimension = (
            "key_conclusions"
        )


        keywords = [

            "proposal",

            "not_decision",

            "confirmation"

        ]



    elif boundary_type == (
        "confirmed_decision"
    ):


        query_intent = (
            "extract_confirmed_decision"
        )


        rule_domains = [

            "decision_rule",

            "positive_examples"

        ]


        dimension = (
            "key_conclusions"
        )


        keywords = [

            "decision",

            "confirmed",

            "approved"

        ]



    # =========================
    # Action（任务）
    # =========================


    elif boundary_type == (
        "confirmed_action"
    ):


        query_intent = (
            "extract_action_item"
        )


        rule_domains = [

            "action_rule",

            "owner_deadline"

        ]


        dimension = (
            "action_items"
        )


        keywords = [

            "owner",

            "deadline",

            "task"

        ]



    # =========================
    # Risk（风险）
    # =========================


    elif boundary_type == (
        "confirmed_risk"
    ):


        query_intent = (
            "extract_risk"
        )


        rule_domains = [

            "risk_rule"

        ]


        dimension = (
            "risks_and_focus"
        )


        keywords = [

            "risk",

            "impact",

            "uncertainty"

        ]



    return RulePlan(

        query_intent=query_intent,

        rule_domains=rule_domains,

        dimension=dimension,

        retrieval_keywords=keywords,

        confidence=0.9

    )