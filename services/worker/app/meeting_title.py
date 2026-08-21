from __future__ import annotations

import re
from typing import Any

DEFAULT_TITLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:实时录音|文件导入)$")
MEETING_TYPES = {
    "project_weekly",
    "progress_sync",
    "requirement_review",
    "solution_review",
    "project_retrospective",
    "risk_review",
    "release_review",
    "customer_communication",
    "training",
    "interview",
    "one_on_one",
    "other",
}
GENERIC_TITLES = {
    "会议",
    "项目会议",
    "工作讨论",
    "会议总结",
    "周会",
    "项目周会",
    "工作会议",
    "会议纪要",
    "讨论会议",
    "业务会议",
    "项目讨论",
    "工作会",
    "例会",
}
EXPLANATION_PATTERNS = (
    r"^本次会议",
    r"^会议主要",
    r"^本次主要",
    r"^主要讨论",
    r"^会议围绕",
    r"^以下",
)
TIME_WORD_RE = re.compile(
    r"(今天|明天|后天|上午|下午|晚上|今晚|本周|下周|本月|月底|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,2}月\d{1,2}[日号]?|\d{1,2}[日号]|截止|期限|之前|以前|前)"
)
ACTION_WORD_RE = re.compile(r"(完成|提交|优化|修复|跟进|补充|更新|交付|处理|对接|联调|上线|排查|确认|整理)")
ROLE_TASK_RE = re.compile(
    r"(前端|后端|测试|产品经理|设计师|UI设计师|运维|算法|数据分析师).{0,8}"
    r"(完成|提交|优化|修复|跟进|补充|更新|交付|处理|对接|联调|排查|确认)"
)
TITLE_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9＋+#（）()、与和及暨：]{6,24}$")
VERSION_DOT_RE = re.compile(r"[A-Za-z]?\d+(?:\.\d+)+")


def _format_check_text(title: str) -> str:
    return VERSION_DOT_RE.sub(lambda match: match.group(0).replace(".", ""), title)


def is_default_title(title: str | None) -> bool:
    return bool(title and DEFAULT_TITLE_RE.match(title.strip()))


def is_valid_ai_title(title: str | None) -> bool:
    if not title:
        return False
    clean = title.strip().strip('"“”\'`')
    if clean != title.strip():
        return False
    if clean.startswith("{") or clean.startswith("["):
        return False
    if "```" in clean:
        return False
    if not clean or clean in GENERIC_TITLES:
        return False
    if any(re.search(pattern, clean) for pattern in EXPLANATION_PATTERNS):
        return False
    if len(clean) < 6 or len(clean) > 24:
        return False
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", clean))
    if chinese_count < 6 or chinese_count > 20:
        return False
    if re.search(r"[:。！？!?，,；;\n\r{}\[\]<>#*_]", clean):
        return False
    if TIME_WORD_RE.search(clean) and ACTION_WORD_RE.search(clean):
        return False
    if ROLE_TASK_RE.search(clean):
        return False
    return bool(TITLE_RE.match(_format_check_text(clean)))


def has_valid_title_basis(payload: dict[str, Any]) -> bool:
    items = payload.get("title_basis")
    if not isinstance(items, list):
        return False
    valid_count = 0
    for item in items:
        text = str(item or "").strip()
        if len(re.findall(r"[\u4e00-\u9fff]", text)) >= 6 and not re.search(r"[\n\r{}\[\]<>#*_`]", text):
            valid_count += 1
    return valid_count >= 2


def has_valid_meeting_type(payload: dict[str, Any]) -> bool:
    meeting_type = str(payload.get("meeting_type") or "").strip()
    if meeting_type not in MEETING_TYPES:
        return False
    try:
        confidence = float(payload.get("meeting_type_confidence"))
    except (TypeError, ValueError):
        return False
    return confidence >= 0.70


def maybe_apply_ai_title(meeting: Any, payload: dict[str, Any]) -> str | None:
    title_source = getattr(meeting, "title_source", None) or "fallback"
    if title_source == "user_edited":
        return None
    if title_source == "ai_generated":
        return None
    if title_source != "text_debug" and not is_default_title(getattr(meeting, "title", None)):
        return None
    if not has_valid_meeting_type(payload):
        return None
    if not has_valid_title_basis(payload):
        return None
    candidate = str(payload.get("meeting_title_candidate") or payload.get("meeting_title") or "").strip()
    if not is_valid_ai_title(candidate):
        return None
    meeting.title = candidate
    meeting.title_source = "ai_generated"
    return candidate
