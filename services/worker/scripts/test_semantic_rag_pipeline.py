from app.semantic_intelligence.event_understanding import analyze_event
from app.semantic_intelligence.boundary_engine import analyze_boundary
from app.semantic_intelligence.rule_planner import build_rule_plan
from app.semantic_intelligence.dimension_mapper import map_dimension
from app.semantic_intelligence.rag_adapter import build_rag_request


cases = [

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


for event in cases:


    print("\n====================")
    print("EVENT")
    print(event)



    context = analyze_event(
        event
    )


    boundary = analyze_boundary(
        context.model_dump()
    )


    rule_plan = build_rule_plan(
        context.model_dump(),
        boundary.model_dump()
    )


    rag_request = build_rag_request(
        rule_plan.model_dump()
    )


    rag_request["metadata_filter"]["dimension"] = (
        map_dimension(
            rag_request["metadata_filter"]["dimension"]
        )
    )


    print("\nSEMANTIC CONTEXT")
    print(
        context.model_dump()
    )


    print("\nBOUNDARY")
    print(
        boundary.model_dump()
    )


    print("\nRULE PLAN")
    print(
        rule_plan.model_dump()
    )


    print("\nFINAL RAG REQUEST")
    print(
        rag_request
    )