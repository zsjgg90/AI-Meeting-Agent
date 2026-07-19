from __future__ import annotations

import html
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.models import Meeting


ExportFormat = str
ExportKind = str


def _clean_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", value.strip())
    return cleaned[:80] or "meeting"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "未设置"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _speaker_names(meeting: Meeting) -> dict[str, str]:
    return {mapping.speaker_label: mapping.display_name for mapping in meeting.speaker_mappings}


def _replace_speakers(value: str, speakers: dict[str, str]) -> str:
    result = value
    for label, name in speakers.items():
        result = result.replace(label, name)
    return result


def _text_value(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "; ".join(f"{key}: {value}" for key, value in item.items() if value not in (None, "", []))


def _bullet_section(title: str, rows: list[str]) -> str:
    if not rows:
        rows = ["暂无"]
    return f"## {title}\n" + "\n".join(f"- {row}" for row in rows) + "\n"


def build_transcript_markdown(meeting: Meeting) -> str:
    speakers = _speaker_names(meeting)
    lines = [
        f"# {meeting.title} - 原始分人转写文稿",
        "",
        "## 会议基本信息",
        f"- 会议名称：{meeting.title}",
        f"- 开始时间：{_format_datetime(meeting.start_at)}",
        f"- 结束时间：{_format_datetime(meeting.end_at)}",
        f"- 会议地址：{meeting.location or '未填写'}",
        "",
        "## 发言人信息",
    ]
    if meeting.speaker_mappings:
        for mapping in meeting.speaker_mappings:
            note = f"；备注：{mapping.note}" if mapping.note else ""
            lines.append(f"- {mapping.speaker_label}：{mapping.display_name}{note}")
    else:
        lines.append("- 暂无发言人映射")

    lines.extend(["", "## 分人转写"])
    for segment in meeting.transcript_segments:
        speaker = speakers.get(segment.speaker_label or "", segment.speaker_label or "发言人")
        start = f"{segment.start_time:.2f}s"
        end = f"{segment.end_time:.2f}s"
        lines.append(f"- [{start}-{end}] {speaker}：{segment.text}")
    if not meeting.transcript_segments:
        lines.append("- 暂无转写内容")

    return "\n".join(lines).strip() + "\n"


def build_summary_markdown(meeting: Meeting) -> str:
    summary = meeting.summary
    speakers = _speaker_names(meeting)
    participants = ", ".join(speakers.values()) if speakers else "待识别"
    lines = [
        f"# {meeting.title} - 结构化会议纪要",
        "",
        "## 会议基本信息",
        f"- 会议名称：{meeting.title}",
        f"- 开始时间：{_format_datetime(meeting.created_at)}",
        f"- 结束时间：{_format_datetime(meeting.end_at)}",
        f"- 会议地址：{meeting.location or '未填写'}",
        f"- 参会人员：{participants}",
        f"- 当前状态：{meeting.status}",
        "",
        "## 会议概览",
        _replace_speakers((summary.meeting_summary or summary.overview) if summary else "暂无会议纪要。", speakers),
        "",
    ]

    agenda = (summary.meeting_agenda or summary.agenda) if summary else []
    lines.append(
        _bullet_section(
            "会议议程",
            [_replace_speakers(_text_value(item, ["item", "summary", "status"]), speakers) for item in agenda],
        )
    )

    decisions = (summary.key_conclusions or summary.decisions) if summary else []
    lines.append(
        _bullet_section(
            "核心结论",
            [_replace_speakers(_text_value(item, ["conclusion", "decision", "title", "summary", "reason"]), speakers) for item in decisions],
        )
    )

    action_rows = []
    for item in meeting.action_items:
        owner_value = item.owner_name or item.owner
        due_value = item.deadline or item.due_date
        owner = f"；负责人：{_replace_speakers(owner_value, speakers)}" if owner_value else ""
        due = f"；截止时间：{due_value}" if due_value else ""
        action_rows.append(f"{_replace_speakers(item.task, speakers)}{owner}{due}；状态：{item.status}")
    lines.append(_bullet_section("待办与后续安排", action_rows))

    questions = (summary.unresolved_issues or summary.open_questions) if summary else []
    lines.append(
        _bullet_section(
            "遗留问题",
            [_replace_speakers(_text_value(item, ["issue", "question", "reason", "blocker", "source_text", "source"]), speakers) for item in questions],
        )
    )

    risks = (summary.risks_and_focus or summary.risks) if summary else []
    lines.append(
        _bullet_section(
            "风险与关注点",
            [_replace_speakers(_text_value(item, ["risk", "impact", "focus_area", "mitigation", "source_text"]), speakers) for item in risks],
        )
    )

    return "\n".join(lines).strip() + "\n"


def _write_docx(path: Path, markdown_text: str) -> None:
    paragraphs = markdown_text.splitlines()
    body = []
    for line in paragraphs:
        if not line.strip():
            body.append("<w:p/>")
            continue
        escaped = html.escape(line)
        body.append(f"<w:p><w:r><w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>")
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}<w:sectPr/></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def _write_pdf(path: Path, markdown_text: str) -> None:
    registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    x = 48
    y = height - 48
    pdf.setFont("STSong-Light", 11)
    for raw_line in markdown_text.splitlines():
        line = raw_line or " "
        while len(line) > 45:
            pdf.drawString(x, y, line[:45])
            line = line[45:]
            y -= 18
            if y < 48:
                pdf.showPage()
                pdf.setFont("STSong-Light", 11)
                y = height - 48
        pdf.drawString(x, y, line)
        y -= 18
        if y < 48:
            pdf.showPage()
            pdf.setFont("STSong-Light", 11)
            y = height - 48
    pdf.save()


def create_export_file(meeting: Meeting, kind: ExportKind, file_format: ExportFormat) -> Path:
    if kind not in {"transcript", "summary"}:
        raise ValueError("Unsupported export kind.")
    if file_format not in {"md", "markdown", "txt", "pdf", "docx", "word"}:
        raise ValueError("Unsupported export format.")

    normalized_format = {"markdown": "md", "word": "docx"}.get(file_format, file_format)
    markdown_text = build_transcript_markdown(meeting) if kind == "transcript" else build_summary_markdown(meeting)

    export_dir = Path(get_settings().storage_dir) / "meetings" / meeting.id / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    suffix = "原始分人转写" if kind == "transcript" else "结构化会议纪要"
    path = export_dir / f"{_clean_filename(meeting.title)}_{suffix}.{normalized_format}"

    if normalized_format in {"md", "txt"}:
        path.write_text(markdown_text, encoding="utf-8")
    elif normalized_format == "docx":
        _write_docx(path, markdown_text)
    elif normalized_format == "pdf":
        _write_pdf(path, markdown_text)
    return path
