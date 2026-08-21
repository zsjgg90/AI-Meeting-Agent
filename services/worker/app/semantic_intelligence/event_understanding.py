from .schemas import SemanticContext



def detect_decision_commitment(content:str):

    strong_words = [
        "确认",
        "决定",
        "确定",
        "采用",
        "同意",
        "批准",
        "上线"
    ]


    weak_words = [
        "考虑",
        "研究一下",
        "看看",
        "关注一下",
        "后面再说",
        "可以考虑"
    ]


    if any(
        w in content
        for w in strong_words
    ):

        return "strong"


    if any(
        w in content
        for w in weak_words
    ):

        return "weak"


    return "none"



def detect_action_commitment(content:str):


    action_words = [

        "测试",

        "整理",

        "开发",

        "修改",

        "修复",

        "提交",

        "跟进",

        "处理",

        "检查"

    ]


    has_action = any(
        w in content
        for w in action_words
    )


    has_person = any(

        name in content

        for name in [
            "张",
            "李",
            "王",
            "陈",
            "赵",
            "负责人",
            "前端",
            "后端"
        ]

    )


    has_time = any(

        t in content

        for t in [
            "今天",
            "下午",
            "明天",
            "本周",
            "下周"
        ]

    )


    if has_action and (
        has_person or has_time
    ):

        return "strong"


    return "none"



def analyze_event(event:dict):


    event_type = event.get(
        "event_type",
        "unknown"
    )


    content = event.get(
        "content",
        ""
    )


    decision_commitment = (
        detect_decision_commitment(
            content
        )
    )


    action_commitment = (
        detect_action_commitment(
            content
        )
    )


    decision_status="unknown"

    action_status="unknown"

    risk_status="unknown"


    if event_type=="proposal":

        decision_status="not_confirmed"


    elif event_type=="decision":

        decision_status="confirmed"



    if event_type=="action_assignment":

        action_status="confirmed"



    if event_type=="risk_warning":

        risk_status="confirmed"



    allowed_dimensions=[]


    if decision_status=="confirmed":

        allowed_dimensions.append(
            "key_conclusions"
        )


    if action_status=="confirmed":

        allowed_dimensions.append(
            "action_items"
        )


    if risk_status=="confirmed":

        allowed_dimensions.append(
            "risks_and_focus"
        )



    return SemanticContext(

        event_type=event_type,

        decision_commitment=
            decision_commitment,

        action_commitment=
            action_commitment,

        decision_status=
            decision_status,

        action_status=
            action_status,

        risk_status=
            risk_status,

        allowed_dimensions=
            allowed_dimensions,

        confidence=0.85

    )