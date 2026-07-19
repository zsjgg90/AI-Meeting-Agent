from app.prompt_registry import (
    MEETING_ANALYST_PROMPT_VERSION,
    get_meeting_analyst_prompt_spec,
    load_prompt_template,
)


RAG_QUERY = """
会议六大维度分析规则。

重点检索：
会议议程、
会议总结、
核心结论、
待办与后续安排、
遗留问题、
风险与关注点。

尤其关注：
待办和遗留问题边界、
遗留问题和风险边界、
建议和核心结论边界、
会议总结禁止原文摘录、
截止时间证据绑定、
负责人证据绑定、
限流风险、
数据迁移返工风险。
""".strip()


def build_meeting_analyst_prompt(
    rag_context: str,
    transcript: str,
) -> str:
    if not transcript or not transcript.strip():
        raise ValueError("Meeting transcript cannot be empty")

    spec = get_meeting_analyst_prompt_spec()
    template = load_prompt_template(spec.prompt_version)
    return (
        template.replace("{{RAG_CONTEXT}}", rag_context)
        .replace("{{TRANSCRIPT}}", transcript)
        .strip()
    )
