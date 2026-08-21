from .schemas import BoundaryResult



def analyze_boundary(context: dict) -> BoundaryResult:
    """
    Boundary Engine（语义边界引擎）

    判断当前 Semantic Context（语义上下文）
    是否允许进入：

    Decision（决策）
    Action Item（待办事项）
    Risk（风险）
    """


    event_type = context.get(
        "event_type",
        ""
    )


    decision_commitment = context.get(
        "decision_commitment",
        "none"
    )


    action_commitment = context.get(
        "action_commitment",
        "none"
    )


    decision_status = context.get(
        "decision_status",
        "unknown"
    )


    risk_status = context.get(
        "risk_status",
        "unknown"
    )



    can_be_decision = False

    can_be_action = False

    can_be_risk = False



    boundary_type = "unknown"

    reason = ""



    # ==========================
    # Decision Boundary（决策边界）
    # ==========================


    if event_type == "proposal":

        boundary_type = (
            "proposal_not_decision"
        )

        reason = (
            "Proposal（提议） "
            "without confirmation（没有确认）"
        )



    elif (
        event_type == "decision"
        and decision_commitment == "strong"
    ):

        can_be_decision = True

        boundary_type = (
            "confirmed_decision"
        )

        reason = (
            "Confirmed Decision"
            "（已确认决策）"
        )



    # ==========================
    # Action Boundary（任务边界）
    # ==========================


    if event_type == "action_assignment":


        if action_commitment == "strong":


            can_be_action = True


            boundary_type = (
                "confirmed_action"
            )


            reason = (
                "Confirmed Action"
                "（已确认任务）"
            )


        else:


            boundary_type = (
                "weak_action"
            )


            reason = (
                "Weak Action Commitment"
                "（弱行动承诺）"
            )



    # ==========================
    # Risk Boundary（风险边界）
    # ==========================


    if (
        event_type == "risk_warning"
        and risk_status == "confirmed"
    ):


        can_be_risk = True


        boundary_type = (
            "confirmed_risk"
        )


        reason = (
            "Explicit Risk"
            "（明确风险）"
        )



    return BoundaryResult(

        can_be_decision=
            can_be_decision,


        can_be_action=
            can_be_action,


        can_be_risk=
            can_be_risk,


        boundary_type=
            boundary_type,


        reason=
            reason,


        confidence=
            0.85

    )