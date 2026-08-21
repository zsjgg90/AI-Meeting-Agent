from app.semantic_intelligence.event_understanding import analyze_event
from app.semantic_intelligence.boundary_engine import analyze_boundary
from app.semantic_intelligence.rule_planner import build_rule_plan



cases=[


{
"event_type":
"proposal",

"content":
"这个功能后面可以研究一下"

},



{
"event_type":
"decision",

"content":
"确认下周上线这个功能"

},



{
"event_type":
"action_assignment",

"content":
"张伟下午测试接口"

}

]



for item in cases:


    context = analyze_event(item)


    boundary = analyze_boundary(
        context.model_dump()
    )


    plan = build_rule_plan(

        context.model_dump(),

        boundary.model_dump()

    )


    print("\n==========")

    print("EVENT")

    print(item)


    print("\nBOUNDARY")

    print(
        boundary.model_dump()
    )


    print("\nRULE PLAN")

    print(
        plan.model_dump()
    )