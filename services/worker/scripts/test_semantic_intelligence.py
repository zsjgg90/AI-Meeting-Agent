from app.semantic_intelligence.event_understanding import analyze_event


cases = [

    {
        "event_type": "proposal",
        "content": "这个功能后面可以研究一下"
    },


    {
        "event_type": "decision",
        "content": "确认下周上线这个功能"
    },


    {
        "event_type": "action_assignment",
        "content": "张伟下午测试一下接口"
    }

]


for case in cases:

    result = analyze_event(case)

    print(
        result.model_dump()
    )