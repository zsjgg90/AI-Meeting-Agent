from app.rag_retriever import RagRetriever

from app.semantic_intelligence.retrieval_bridge import (
    RetrievalBridge
)


retriever = RagRetriever()


bridge = RetrievalBridge(
    retriever
)


cases = [

    {
        "name":
        "proposal",

        "request":
        {
            "query":
            "prevent_false_decision decision_boundary negative_examples proposal",

            "top_k":
            5,

            "metadata_filter":
            {
                "dimension":
                "decision"
            }
        }
    },


    {
        "name":
        "action",

        "request":
        {
            "query":
            "extract_action_item action_rule owner deadline task",

            "top_k":
            5,

            "metadata_filter":
            {
                "dimension":
                "action"
            }
        }
    }

]


for case in cases:

    print("\n================")
    print(case["name"])


    results = bridge.retrieve(
        case["request"]
    )


    print(
        "count:",
        len(results)
    )


    for item in results[:3]:

        print(
            item
        )