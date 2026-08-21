from app.semantic_intelligence.rag_adapter import (
    build_rag_request
)



cases=[


{
"query_intent":
"prevent_false_decision",

"rule_domains":[
"decision_boundary",
"negative_examples"
],

"dimension":
"key_conclusions",

"retrieval_keywords":[
"proposal",
"not_decision",
"confirmation"
]

},



{
"query_intent":
"extract_action_item",

"rule_domains":[
"action_rule",
"owner_deadline"
],

"dimension":
"action_items",

"retrieval_keywords":[
"owner",
"deadline",
"task"
]

}

]



for case in cases:

    result = build_rag_request(
        case
    )


    print(
        "\nINPUT:"
    )

    print(case)


    print(
        "\nRAG REQUEST:"
    )

    print(result)