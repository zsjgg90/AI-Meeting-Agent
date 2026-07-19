def build_transcript_text(transcript_segments: list[dict]) -> str:
    """
    将 transcript_segments 拼接成适合 Meeting Analyst 分析的会议文本。
    每段保留 speaker、时间、正文，方便模型引用证据。
    """

    lines = []

    for segment in transcript_segments:
        speaker = (
            segment.get("speaker_name")
            or segment.get("speaker_label")
            or "未知说话人"
        )

        start_time = segment.get("start_time")
        end_time = segment.get("end_time")
        text = segment.get("text", "")

        if not text:
            continue

        if start_time is not None and end_time is not None:
            line = f"{speaker}（{start_time}-{end_time}）：{text}"
        else:
            line = f"{speaker}：{text}"

        lines.append(line)

    return "\n".join(lines)