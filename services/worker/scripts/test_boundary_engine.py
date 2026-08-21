from app.semantic_intelligence.event_understanding import analyze_event
from app.semantic_intelligence.boundary_engine import analyze_boundary



cases=[

{
"event_type":"proposal",
"content":"这个功能后面可以研究一下"
},


{
"event_type":"decision",
"content":"确认下周上线这个功能"
},


{
"event_type":"action_assignment",
"content":"张伟下午测试接口"
}

]


for item in cases:

    context = analyze_event(item)


    print(
        "\nEVENT:"
    )

    print(
        item
    )


    print(
        "\nCONTEXT:"
    )

    print(
        context.model_dump()
    )


    result = analyze_boundary(
        context.model_dump()
    )


    print(
        "\nBOUNDARY:"
    )

    print(
        result.model_dump()
    )