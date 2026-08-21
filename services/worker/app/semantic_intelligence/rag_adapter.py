from typing import Dict, Any



def build_rag_request(
    rule_plan: Dict[str, Any]
) -> Dict[str, Any]:
    """
    RAG Adapter（检索增强生成适配器）

    将 Rule Plan（规则计划）
    转换成 Retriever（检索器）
    可以使用的请求结构
    """



    query_intent = rule_plan.get(
        "query_intent",
        ""
    )


    domains = rule_plan.get(
        "rule_domains",
        []
    )


    keywords = rule_plan.get(
        "retrieval_keywords",
        []
    )


    dimension = rule_plan.get(
        "dimension",
        "general"
    )



    query_parts = []


    if query_intent:

        query_parts.append(
            query_intent
        )


    query_parts.extend(
        domains
    )


    query_parts.extend(
        keywords
    )



    query = " ".join(
        query_parts
    )



    return {

        "query": query,


        "metadata_filter": {

            "dimension": dimension

        },


        "top_k": 10,


        "intent": query_intent

    }