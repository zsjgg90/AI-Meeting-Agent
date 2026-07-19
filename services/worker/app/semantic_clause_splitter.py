from __future__ import annotations

import re
from dataclasses import dataclass


FLOW_PHRASES = [
    "大家好",
    "各位好",
    "我补充一下",
    "我来说一下",
    "我来说两点",
    "大家有没有问题",
    "有没有异议",
    "无问题",
    "无异议",
    "好的",
    "好",
    "会议结束",
    "今天会议到这里",
]

BUSINESS_SIGNALS = [
    "需求",
    "问题",
    "风险",
    "延期",
    "接口",
    "数据",
    "上线",
    "测试",
    "开发",
    "设计",
    "方案",
    "确认",
    "决定",
    "同意",
    "建议",
    "必须",
    "需要",
    "负责",
    "完成",
    "排期",
    "版本",
    "功能",
    "指标",
    "成本",
    "质量",
    "用户",
    "流程",
]

SPLIT_PATTERN = re.compile(
    r"(?:；|;|，(?=同时|另外|其次|第一|第二|第三|第四|第五|但|因此|如果|需要|必须|否则)|"
    r"(?<=。)|(?<=！)|(?<=？))"
)


@dataclass(frozen=True)
class ClauseSplitResult:
    clauses: list[str]
    is_pure_flow: bool


def normalize_flow_text(text: str) -> str:
    return re.sub(r"[\s，,。.!！?？、]+", "", text.strip())


def is_pure_flow_utterance(text: str) -> bool:
    normalized = normalize_flow_text(text)
    if not normalized:
        return True

    if normalized in {normalize_flow_text(item) for item in FLOW_PHRASES}:
        return True

    if any(signal in text for signal in BUSINESS_SIGNALS):
        return False

    if len(normalized) <= 12 and any(
        normalized.startswith(normalize_flow_text(item))
        for item in FLOW_PHRASES
    ):
        return True

    return False


def split_semantic_clauses(text: str) -> ClauseSplitResult:
    stripped = text.strip()
    if not stripped:
        return ClauseSplitResult(clauses=[], is_pure_flow=True)

    is_flow = is_pure_flow_utterance(stripped)
    if is_flow:
        return ClauseSplitResult(clauses=[stripped], is_pure_flow=True)

    rough = [item.strip(" ，,。；;") for item in SPLIT_PATTERN.split(stripped)]
    clauses: list[str] = []
    for item in rough:
        if not item:
            continue
        pieces = re.split(
            r"(?=(?:同时|另外|其次|第一[，、]|第二[，、]|第三[，、]|第四[，、]|但|因此|如果|需要|必须|否则))",
            item,
        )
        for piece in pieces:
            piece = piece.strip(" ，,。；;")
            if len(piece) >= 4:
                clauses.append(piece)

    if not clauses:
        clauses = [stripped]

    return ClauseSplitResult(clauses=clauses[:6], is_pure_flow=False)
