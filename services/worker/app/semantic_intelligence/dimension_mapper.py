def map_dimension(
    business_dimension: str
) -> str:
    """
    Dimension Mapper（维度映射器）

    将业务输出维度
    映射到 RAG Metadata（检索元数据）维度
    """


    mapping = {


        "key_conclusions":
            "decision",


        "action_items":
            "action",


        "risks_and_focus":
            "risk",


        "unresolved_issues":
            "general",


        "meeting_summary":
            "general"

    }


    return mapping.get(
        business_dimension,
        "general"
    )