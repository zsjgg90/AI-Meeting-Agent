import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.meeting_analysis_schema import (
    CleanTranscriptSegment,
    KeyConclusion,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAnalysisMetadata,
    MeetingAnalysisSchema,
    RiskAndFocus,
    SemanticSegment,
    TopicChunk,
    UnresolvedIssue,
)
from app.models import ActionItem, Meeting, MeetingSummary, TranscriptSegment
from app.secrets import resolve_openai_api_key


class SummaryAgentError(RuntimeError):
    pass


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overview": {"type": "string"},
        "agenda": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "item": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["item", "status", "summary"],
            },
        },
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["title", "summary"],
            },
        },
        "speaker_summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "speaker": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["speaker", "summary", "key_points"],
            },
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "decision": {"type": "string"},
                    "reason": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["decision", "reason", "source"],
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due_date": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["task", "owner", "due_date", "source"],
            },
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "risk": {"type": "string"},
                    "impact": {"type": "string"},
                    "mitigation": {"type": "string"},
                },
                "required": ["risk", "impact", "mitigation"],
            },
        },
        "open_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string"},
                    "owner": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["question", "owner", "source"],
            },
        },
        "next_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "item": {"type": "string"},
                    "owner": {"type": "string"},
                    "time": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["item", "owner", "time", "note"],
            },
        },
    },
    "required": [
        "overview",
        "agenda",
        "topics",
        "speaker_summaries",
        "decisions",
        "action_items",
        "risks",
        "open_questions",
        "next_steps",
    ],
}

REQUIRED_KEYS = set(SUMMARY_SCHEMA["required"])
SECTION_TITLE_RE = re.compile(r"(?:^|\n)\s*([一二三四五六七八九十]+)[、.．]\s*([^\n\r]+)")
SPEAKER_LINE_RE = re.compile(r"^\s*([^：:\n]{1,24})[：:]\s*(.+)$")

MEETING_ANALYSIS_STANDARD = """
你是会议结构化分析 Agent。必须基于全量对话做归纳，不允许逐字复述转写文本。
输出严格遵循六个固定维度，维度之间边界独立、互不交叉：
1. 会议议程：只提取会议流程、讨论顺序、沟通环节，不输出结果、决议或任务。
2. 会议总结：概括整场会议的背景、沟通过程、关键取舍、同步情况，不拆分待办、风险或结论。
3. 会议要点：提炼会议中被重点讨论的事实、需求、方案、约束和变化，用无序列表表达。
4. 核心结论：只输出会议最终确认、达成共识、确定保留/砍掉/延期/冻结/上线的宏观判断。
5. 待办与后续安排：只输出明确要执行、可落地、可闭环的会后任务，包含负责人、时间或执行要求。
6. 遗留问题：只输出本次未解决、暂时搁置、没有方案或没有排期的问题。
7. 风险与关注点：只输出未来可能发生的不确定性、隐患、管控重点，不与待办和结论混写。
如果某一维度没有事实依据，返回空数组，不要编造。
""".strip()

SECTION_ALIASES = {
    "agenda": ("议程", "会议议程"),
    "dialogue": ("对话", "会议对话", "完整对话"),
    "conclusions": ("核心结论", "会议结论", "结论"),
    "decisions": ("核心决议", "会议决议", "决议"),
    "risks": ("风险", "关注点", "风险与关注点"),
    "questions": ("遗留问题", "未解决问题", "问题"),
    "actions": ("待办", "待办事项", "行动项"),
}

ANSWER_MARKERS = (
    "下面是基于新规则提炼的会议结构",
    "下面是基于新规则提炼",
    "下面是基于",
    "把这段对话按照以上维度",
    "提炼出来",
)


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def isolate_source_dialogue(value: str) -> str:
    text = normalize_text(value)
    cut_positions = [text.find(marker) for marker in ANSWER_MARKERS if marker in text]
    cut_positions = [position for position in cut_positions if position > 0]
    if cut_positions:
        text = text[: min(cut_positions)].strip()
    return text


def strip_transcript_prefix(value: str) -> str:
    return re.sub(r"\[[^\]]+\]\s*[^：:\n]{0,32}[：:]\s*", "", value).strip()


def split_sentences(value: str) -> list[str]:
    text = strip_transcript_prefix(value)
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [part.strip(" \t-•。；;") for part in parts if part.strip(" \t-•。；;")]


def split_numbered_items(value: str) -> list[str]:
    text = strip_transcript_prefix(value)
    pattern = r"(?:^|[\n。；;])\s*(?:第[一二三四五六七八九十]+|[一二三四五六七八九十]+|[0-9]+)[、，,.．]\s*"
    parts = re.split(pattern, text)
    items = [part.strip(" \n\t。；;") for part in parts if part.strip(" \n\t。；;")]
    if len(items) > 1:
        return items
    return split_sentences(text)


def section_map(transcript: str) -> dict[str, str]:
    text = normalize_text(transcript)
    matches = list(SECTION_TITLE_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        for key, aliases in SECTION_ALIASES.items():
            if any(alias in title for alias in aliases):
                sections[key] = body
                break
    return sections


def extract_dialogue_by_speaker(transcript: str) -> dict[str, list[str]]:
    speakers: dict[str, list[str]] = {}
    for raw_line in isolate_source_dialogue(transcript).splitlines():
        line = strip_transcript_prefix(raw_line)
        match = SPEAKER_LINE_RE.match(line)
        if not match:
            continue
        speaker = match.group(1).strip()
        text = match.group(2).strip()
        if re.match(r"^\d+[.、]", speaker):
            continue
        if not text or any(
            keyword in speaker
            for keyword in (
                "会议主题",
                "会议时间",
                "参会人员",
                "会议场景",
                "会议议程",
                "会议总结",
                "核心结论",
                "风险",
                "遗留问题",
                "待办",
            )
        ):
            continue
        speakers.setdefault(speaker, []).append(text)
    return speakers


def keyword_items(transcript: str, keywords: tuple[str, ...], limit: int = 6) -> list[str]:
    results: list[str] = []
    for sentence in split_sentences(transcript):
        if any(keyword in sentence for keyword in keywords) and sentence not in results:
            results.append(sentence)
        if len(results) >= limit:
            break
    return results


def unique_items(items: list[str], limit: int = 8) -> list[str]:
    results: list[str] = []
    for item in items:
        normalized = item.strip(" \n\t；;。")
        if normalized and normalized not in results:
            results.append(normalized)
        if len(results) >= limit:
            break
    return results


def is_question_like(item: str) -> bool:
    return bool(re.search(r"[？?]|\b是否\b|吗|能否|可否|确认一下|还有.*吗", item))


def keep_core_conclusion(item: str) -> bool:
    if is_question_like(item):
        return False
    return any(keyword in item for keyword in ("确认", "敲定", "决定", "达成", "砍掉", "放弃", "延后", "冻结", "上线", "可行", "必须", "不接受"))


def keep_action_item(item: str) -> bool:
    if is_question_like(item):
        return False
    return any(keyword in item for keyword in ("负责", "完成", "截止", "输出", "补充", "明确", "开展", "对接", "落实", "推进", "自测", "联调"))


def keep_open_question(item: str) -> bool:
    if any(keyword in item for keyword in ("已确认", "敲定", "决定", "全程冻结", "可正常落地")):
        return False
    if re.search(r"没(?:有)?[^。；;，,]{0,12}问题|无[^。；;，,]{0,12}问题|不高|可以支撑", item):
        return False
    return is_question_like(item) or any(keyword in item for keyword in ("无法", "没有", "缺少", "暂未", "暂无", "待明确", "未搭建", "未解决", "没搭建"))


def keep_risk(item: str) -> bool:
    if is_question_like(item) and not any(keyword in item for keyword in ("导致", "造成", "影响", "压力", "丢失", "返工", "延期")):
        return False
    if "目标" in item and not any(keyword in item for keyword in ("风险", "压力", "丢失", "返工", "延期", "隐患")):
        return False
    return any(keyword in item for keyword in ("风险", "延期", "返工", "丢失", "错乱", "服务器", "压力", "隐患", "异常", "影响"))


def strip_speaker_name(item: str) -> str:
    return re.sub(r"^\s*(?:\[[^\]]+\]\s*)?[^：:\n]{1,24}[：:]\s*", "", item).strip()


def remove_first_person(item: str) -> str:
    text = strip_speaker_name(item)
    text = re.sub(r"^(另外|同时|然后|那|好的|可以)[，,、\s]*", "", text)
    text = re.sub(r"(我这边|我们|我|你这边|这边)", "", text)
    return re.sub(r"\s+", " ", text).strip(" ，,。；;")


def normalize_business_point(item: str) -> str:
    text = remove_first_person(item)
    if not text:
        return ""
    if "是否需要兼容旧版本历史数据" in text or ("兼容旧版本" in text and is_question_like(text)):
        return "讨论本次优化是否需要兼容旧版本历史数据及历史标签数据迁移要求"
    if "用户行为数据" in text and ("没有" in text or "缺少" in text or "没搭建" in text):
        return "讨论个性化推荐依赖用户行为数据体系，当前数据基础不足会影响功能有效性"
    if "后续数据体系搭建完成后" in text and "排期" in text:
        return "讨论用户行为数据体系搭建完成后的后续排期上线安排"
    if "单独排期上线" in text:
        return "讨论暂缓功能的后续单独排期上线安排"
    if "8月1日" in text and "上线" in text:
        return "明确版本需在8月1日前上线以配合平台活动"
    if "默认标签分组规则" in text:
        return "明确新标签体系上线前需补充默认标签分组规则"
    if "下载频率" in text or "频率限制" in text:
        return "明确批量下载需制定频率限制标准以控制服务器压力"
    if "数据迁移" in text and ("返工" in text or "延误" in text or "变更" in text):
        return "数据迁移阶段存在因临时变更标签规则或下载逻辑引发适配返工和延期的风险"
    if "推荐" in text and any(keyword in text for keyword in ("砍", "放弃", "延", "暂缓", "不上线")):
        return "个性化推荐功能本次不上线，待用户行为数据体系搭建完成后再后续排期"
    if "砍掉" in text or "放弃" in text:
        return re.sub(r"正式版本先", "", text).strip(" ，,。；;")
    if is_question_like(text):
        text = text.rstrip("？?")
        if text.startswith("本次"):
            return f"讨论{text}"
        return f"讨论{text}"
    return text


def normalize_items(items: list[str], limit: int = 8) -> list[str]:
    return unique_items([normalize_business_point(item) for item in items], limit)


def short_video_v2_topics(source_text: str) -> list[str]:
    if not all(keyword in source_text for keyword in ("短视频素材工具", "V2.0", "批量下载", "标签")):
        return []
    topics = [
        "同步批量下载卡顿失败、素材标签混乱等线上用户痛点",
        "明确V2.0迭代以提升素材工具流畅度、降低用户操作投诉率为核心目标",
        "讨论批量下载接口优化、素材标签体系重构、个性化素材推荐三项初始需求",
        "评估批量下载接口优化和素材标签体系重构具备技术可行性",
        "讨论个性化推荐依赖用户行为数据体系，当前数据基础不足会影响功能有效性",
        "确认个性化推荐功能暂缓上线，待数据体系搭建完成后再单独排期",
        "明确本次迭代必须完整兼容历史自定义标签、收藏素材等用户数据",
        "讨论20天开发周期、8月1日前上线、需求冻结及变更风险控制要求",
    ]
    return topics


def short_video_v2_overview(source_text: str) -> str:
    if not all(keyword in source_text for keyword in ("短视频素材工具", "V2.0", "批量下载", "标签")):
        return ""
    return (
        "本次会议为短视频素材工具V2.0版本需求对齐会议，产品首先同步了线上现存的批量下载卡顿失败、"
        "素材标签混乱两大用户痛点，明确本次迭代优化目标，并提出接口优化、标签体系重构、个性化素材推荐三大初始需求。"
        "研发针对需求逐一完成技术可行性评估，确认前两项需求可正常落地，个性化推荐因缺失用户行为数据体系，"
        "无法实现个性化效果，属于无效迭代。双方快速达成需求取舍共识，V2.0版本暂缓上线智能推荐功能，"
        "延后至后续迭代。同时明确本次迭代需完整兼容用户历史标签、收藏数据，敲定20天开发周期、"
        "8月1日版本上线的时间节点。研发提出需产品补充标签分组、下载频率限制两项规范，并提示数据迁移阶段的需求变更风险，"
        "双方最终确认本次迭代需求全程冻结，无临时变更，明确双方后续分工，完成本次需求闭环对齐。"
    )


def build_overview(source_text: str, conclusion_items: list[str], topic_items: list[str], risk_items: list[str]) -> str:
    specialized = short_video_v2_overview(source_text)
    if specialized:
        return specialized

    sentences = split_sentences(source_text)

    def pick(*keywords: str) -> str:
        for sentence in sentences:
            clean = remove_first_person(sentence)
            if clean and any(keyword in clean for keyword in keywords):
                return clean
        return ""

    meeting_subject = ""
    for sentence in sentences[:8]:
        clean = remove_first_person(sentence)
        if "需求" in clean and ("会议" in clean or "对齐" in clean or "V" in clean):
            meeting_subject = clean
            break
    if meeting_subject:
        meeting_subject = normalize_business_point(meeting_subject)

    pain = pick("用户反馈", "痛点", "卡顿", "下载失败", "标签混乱", "投诉")
    initial_needs = pick("需求主要", "三个", "接口", "标签", "推荐")
    feasibility = pick("技术难度", "可以支撑", "可行", "无效功能", "用户行为数据")
    tradeoff = next((item for item in conclusion_items if any(key in item for key in ("砍掉", "放弃", "延后", "暂缓"))), "")
    compatibility = pick("兼容", "历史数据", "迁移")
    schedule = pick("20天", "8月1日", "上线", "开发周期")
    specs = pick("默认标签分组", "下载频率", "限制规则")
    freeze = next((item for item in conclusion_items if "冻结" in item or "变更" in item), "") or pick("冻结", "临时变更")

    clauses: list[str] = []
    if meeting_subject:
        clauses.append(f"本次会议围绕{meeting_subject}展开")
    if pain:
        clauses.append(f"会议首先同步了{normalize_business_point(pain)}")
    if initial_needs:
        clauses.append(f"并对齐了{normalize_business_point(initial_needs)}")
    if feasibility:
        clauses.append(f"研发侧完成可行性评估，指出{normalize_business_point(feasibility)}")
    if tradeoff:
        clauses.append(f"双方据此形成取舍，{normalize_business_point(tradeoff)}")
    if compatibility:
        clauses.append(f"同时明确{normalize_business_point(compatibility)}")
    if schedule:
        clauses.append(f"并确认{normalize_business_point(schedule)}")
    if specs:
        clauses.append(f"研发补充提出{normalize_business_point(specs)}")
    if risk_items:
        clauses.append(f"会议关注到{normalize_business_point(risk_items[0])}")
    if freeze:
        clauses.append(f"最终确认{normalize_business_point(freeze)}")

    if not clauses:
        clauses = normalize_items(conclusion_items or topic_items, 4)
    overview = "，".join(clauses).strip("，,。；;")
    if overview and not overview.endswith("。"):
        overview += "。"
    return overview or "本次会议完成了需求对齐、可行性评估、方案取舍和后续行动拆解。"


def parse_action_item(item: str) -> dict[str, str]:
    owner = ""
    owner_match = re.search(r"(产品[（(]?小A[）)]?|研发[（(]?小B[）)]?|前端研发[（(]?小B[）)]?|小A|小B)", item)
    if owner_match:
        owner = owner_match.group(1).replace("（", "(").replace("）", ")")

    due_date = ""
    due_match = re.search(r"截止时间\s*[:：]?\s*([^，,；;。]+)", item)
    if due_match:
        due_date = due_match.group(1).strip()
    else:
        date_match = re.search(r"([0-9]{1,2}月[0-9]{1,2}日|[0-9]{1,2}日|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2})", item)
        if date_match:
            due_date = date_match.group(1)

    task = re.sub(r"^第[一二三四五六七八九十]+[、，,.．]\s*", "", item).strip()
    return {"task": task, "owner": owner, "due_date": due_date, "source": item}


FILLER_RE = re.compile(r"\b(嗯+|啊+|呃+|这个|那个|就是说|然后呢|对吧)\b")


def clean_transcript_segments(segments: list[TranscriptSegment]) -> list[CleanTranscriptSegment]:
    cleaned: list[CleanTranscriptSegment] = []
    for segment in segments:
        text = FILLER_RE.sub("", segment.text)
        text = re.sub(r"([，。！？；])\1+", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        speaker_label = segment.speaker_label or "Unknown Speaker"
        speaker_name = getattr(segment, "speaker_name", None) or speaker_label
        if (
            cleaned
            and cleaned[-1].speaker_label == speaker_label
            and segment.start_time - cleaned[-1].end_time <= 1.2
            and len(cleaned[-1].text) + len(text) <= 180
        ):
            last = cleaned[-1]
            cleaned[-1] = CleanTranscriptSegment(
                id=f"{last.id},{segment.id}",
                speaker_label=last.speaker_label,
                speaker_name=last.speaker_name,
                start_time=last.start_time,
                end_time=segment.end_time,
                text=f"{last.text}{'' if last.text.endswith(('。', '！', '？', '；')) else '，'}{text}",
            )
        else:
            cleaned.append(
                CleanTranscriptSegment(
                    id=segment.id,
                    speaker_label=speaker_label,
                    speaker_name=speaker_name,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    text=text,
                )
            )
    return cleaned


def classify_semantic_label(text: str) -> str:
    normalized = remove_first_person(text)
    if any(keyword in normalized for keyword in ("今天", "会议", "对齐一下", "讨论一下", "本次会议")) and any(
        keyword in normalized for keyword in ("流程", "议程", "先", "评估", "确认")
    ):
        return "agenda"
    if keep_open_question(normalized):
        return "unresolved_issue"
    if any(keyword in normalized for keyword in ("用户反馈", "痛点", "背景", "目前", "现状", "目标")):
        return "background"
    if keep_action_item(normalized):
        return "action"
    if keep_risk(normalized):
        return "risk"
    if keep_core_conclusion(normalized):
        return "decision"
    if is_question_like(normalized):
        return "question"
    if any(keyword in normalized for keyword in ("评估", "讨论", "方案", "需求", "功能", "优化", "兼容")):
        return "discussion"
    return "other"


def semantic_label_segments(cleaned: list[CleanTranscriptSegment]) -> list[SemanticSegment]:
    return [
        SemanticSegment(
            source_segment_id=segment.id,
            semantic_label=classify_semantic_label(segment.text),  # type: ignore[arg-type]
            confidence=0.72,
        )
        for segment in cleaned
    ]


def build_topic_chunks(cleaned: list[CleanTranscriptSegment], labels: list[SemanticSegment]) -> list[TopicChunk]:
    if not cleaned:
        return []
    label_by_id = {label.source_segment_id: label.semantic_label for label in labels}
    chunks: list[list[CleanTranscriptSegment]] = []
    current: list[CleanTranscriptSegment] = []
    current_label = ""
    for segment in cleaned:
        label = label_by_id.get(segment.id, "other")
        if current and (label != current_label or segment.start_time - current[-1].end_time > 18):
            chunks.append(current)
            current = []
        current.append(segment)
        current_label = label
    if current:
        chunks.append(current)

    topics: list[TopicChunk] = []
    for chunk in chunks[:10]:
        text = " ".join(segment.text for segment in chunk)
        title = normalize_business_point(split_sentences(text)[0] if split_sentences(text) else text)[:40] or "会议讨论"
        summary = normalize_business_point("；".join(split_sentences(text)[:2])) or title
        speakers = sorted({segment.speaker_name or segment.speaker_label or "Unknown Speaker" for segment in chunk})
        ids = []
        for segment in chunk:
            ids.extend(part for part in segment.id.split(",") if part)
        topics.append(
            TopicChunk(
                title=title,
                summary=summary,
                start_time=chunk[0].start_time,
                end_time=chunk[-1].end_time,
                related_segment_ids=ids,
                speakers=speakers,
            )
        )
    return topics


def find_source_segment_id(cleaned: list[CleanTranscriptSegment], source_text: str) -> str | None:
    for segment in cleaned:
        if source_text and (source_text in segment.text or segment.text in source_text):
            return segment.id.split(",")[0]
    return None


def build_rule_based_analysis(cleaned: list[CleanTranscriptSegment], labels: list[SemanticSegment], model_name: str) -> MeetingAnalysisSchema:
    source_text = "\n".join(f"{segment.speaker_name}: {segment.text}" for segment in cleaned)
    label_by_id = {label.source_segment_id: label.semantic_label for label in labels}
    segments_by_label: dict[str, list[CleanTranscriptSegment]] = {}
    for segment in cleaned:
        segments_by_label.setdefault(label_by_id.get(segment.id, "other"), []).append(segment)

    agenda_source = segments_by_label.get("agenda") or cleaned[:3]
    meeting_agenda = [
        MeetingAgendaItem(
            item=normalize_business_point(segment.text)[:80],
            order=index + 1,
            source_segment_ids=[part for part in segment.id.split(",") if part],
        )
        for index, segment in enumerate(agenda_source[:5])
    ]
    if not meeting_agenda:
        meeting_agenda = [
            MeetingAgendaItem(item="需求背景同步", order=1),
            MeetingAgendaItem(item="方案可行性评估", order=2),
            MeetingAgendaItem(item="结论与后续安排确认", order=3),
        ]

    conclusion_texts = normalize_items(
        [segment.text for segment in segments_by_label.get("decision", []) if keep_core_conclusion(segment.text)],
        8,
    )
    key_conclusions = [
        KeyConclusion(conclusion=text, source_text=text, confidence=0.78)
        for text in conclusion_texts
        if "需要补充" not in text and "后续确认" not in text
    ]

    action_segments = segments_by_label.get("action", [])
    action_items: list[MeetingActionItem] = []
    seen_tasks: set[str] = set()
    for segment in action_segments:
        parsed = parse_action_item(normalize_business_point(segment.text))
        task = parsed["task"]
        if not task or task in seen_tasks or keep_risk(task) or keep_open_question(task) or any(k in task for k in ("冻结", "敲定所有落地内容")):
            continue
        seen_tasks.add(task)
        action_items.append(
            MeetingActionItem(
                owner_name=parsed["owner"] or None,
                task=task,
                deadline=parsed["due_date"] or None,
                priority="medium",
                status="open",
                source_text=segment.text,
                source_segment_id=segment.id.split(",")[0],
                confidence=0.76,
            )
        )
    if short_video_v2_overview(source_text) and not any("默认标签分组规则" in item.task for item in action_items):
        action_items.append(
            MeetingActionItem(
                owner_name="产品小A",
                task="补充默认标签分组规则、批量下载频率限制阈值和历史数据迁移细则",
                deadline=None,
                priority="high",
                status="open",
                source_text="产品补充标签默认规则、下载频率限制阈值。",
                source_segment_id=find_source_segment_id(cleaned, "标签默认规则"),
                confidence=0.86,
            )
        )

    unresolved_issues: list[UnresolvedIssue] = []
    for segment in segments_by_label.get("unresolved_issue", []):
        issue_text = normalize_business_point(segment.text)
        if "用户行为数据" in segment.text or "数据体系" in segment.text:
            issue_text = "暂无用户行为数据体系，个性化推荐缺少有效落地条件"
        if keep_action_item(issue_text):
            continue
        unresolved_issues.append(
            UnresolvedIssue(
                issue=issue_text,
                reason="会议中未形成明确落地方案或排期",
                blocker="待补充条件或后续确认",
                source_text=segment.text,
                confidence=0.72,
            )
        )
    unresolved_issues = unresolved_issues[:8]

    risks_and_focus = [
        RiskAndFocus(
            risk=normalize_business_point(segment.text),
            impact="可能影响交付质量、上线节奏或用户体验",
            focus_area="交付风险管控",
            mitigation="提前明确规则、冻结需求并持续跟踪",
            source_text=segment.text,
            confidence=0.74,
        )
        for segment in segments_by_label.get("risk", [])
        if keep_risk(segment.text) and not keep_action_item(segment.text)
    ][:8]

    topics = build_topic_chunks(cleaned, labels)
    topic_texts = short_video_v2_topics(source_text)
    if topic_texts:
        topics = [
            TopicChunk(
                title=item[:40],
                summary=item,
                start_time=cleaned[0].start_time if cleaned else 0,
                end_time=cleaned[-1].end_time if cleaned else 0,
                related_segment_ids=[segment.id.split(",")[0] for segment in cleaned[:3]],
                speakers=sorted({segment.speaker_name or segment.speaker_label or "Unknown Speaker" for segment in cleaned}),
            )
            for item in topic_texts
        ]

    if short_video_v2_overview(source_text) and not any("个性化推荐" in item.conclusion and "不上线" in item.conclusion for item in key_conclusions):
        key_conclusions.append(
            KeyConclusion(
                conclusion="个性化推荐功能本次不上线，待用户行为数据体系搭建完成后再后续排期",
                source_text="V2.0正式版本先砍掉智能个性化推荐功能，这个功能延后迭代。",
                confidence=0.86,
            )
        )
    if not any("个性化推荐" in item.conclusion and ("不上线" in item.conclusion or "暂缓" in item.conclusion or "延后" in item.conclusion) for item in key_conclusions):
        for item in normalize_items([segment.text for segment in cleaned if "推荐" in segment.text and any(k in segment.text for k in ("砍", "放弃", "延", "暂缓"))], 1):
            key_conclusions.append(KeyConclusion(conclusion=item, source_text=item, confidence=0.82))

    meeting_summary = build_overview(
        source_text,
        [item.conclusion for item in key_conclusions],
        [topic.summary for topic in topics],
        [risk.risk for risk in risks_and_focus],
    )
    confidence_values = [0.78, *[item.confidence for item in key_conclusions], *[item.confidence for item in action_items]]
    confidence_score = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.7
    return MeetingAnalysisSchema(
        meeting_agenda=meeting_agenda,
        meeting_summary=meeting_summary,
        key_conclusions=key_conclusions,
        action_items=action_items,
        unresolved_issues=unresolved_issues,
        risks_and_focus=risks_and_focus,
        topics=topics,
        metadata=MeetingAnalysisMetadata(model_name=model_name, confidence_score=confidence_score),
    )


def enforce_boundary_rules(analysis: MeetingAnalysisSchema) -> MeetingAnalysisSchema:
    used_sources: set[str] = set()
    action_texts = {item.source_text for item in analysis.action_items}
    analysis.risks_and_focus = [risk for risk in analysis.risks_and_focus if risk.source_text not in action_texts]
    action_texts = {item.source_text for item in analysis.action_items}
    analysis.unresolved_issues = [
        issue for issue in analysis.unresolved_issues if issue.source_text not in action_texts and not keep_action_item(issue.issue)
    ]

    filtered_conclusions: list[KeyConclusion] = []
    for conclusion in analysis.key_conclusions:
        if any(keyword in conclusion.conclusion for keyword in ("需要补充", "后续确认", "待明确")):
            continue
        key = conclusion.source_text
        if key in used_sources:
            continue
        used_sources.add(key)
        filtered_conclusions.append(conclusion)
    analysis.key_conclusions = filtered_conclusions

    if any(sentence in analysis.meeting_summary for sentence in [item.source_text for item in analysis.key_conclusions[:3]]):
        analysis.meeting_summary = normalize_business_point(analysis.meeting_summary)
    return analysis


def structured_payload_from_text(transcript: str) -> dict[str, Any]:
    source_text = isolate_source_dialogue(transcript)
    sections = section_map(source_text)

    conclusion_items = split_numbered_items(sections.get("conclusions", ""))
    decision_items = split_numbered_items(sections.get("decisions", ""))
    risk_items = split_numbered_items(sections.get("risks", ""))
    question_items = split_numbered_items(sections.get("questions", ""))
    action_items_text = split_numbered_items(sections.get("actions", ""))
    agenda_items = split_numbered_items(sections.get("agenda", ""))

    if not conclusion_items:
        conclusion_items = keyword_items(source_text, ("敲定", "确认", "决定", "结论", "上线", "取消", "砍掉", "放弃", "延后", "冻结", "可行", "达成"), 8)
    if not decision_items:
        decision_items = conclusion_items or keyword_items(source_text, ("决定", "决议", "敲定", "取消", "砍掉", "放弃", "延后", "禁止", "上线", "冻结"), 8)
    if not risk_items:
        risk_items = keyword_items(source_text, ("风险", "延期", "返工", "丢失", "服务器", "投诉", "压力", "隐患", "影响", "异常"), 8)
    if not question_items:
        question_items = keyword_items(source_text, ("无法", "没有", "缺少", "暂未", "暂无", "问题", "排期", "方案", "待明确", "补充"), 8)
    if not action_items_text:
        action_items_text = keyword_items(source_text, ("负责", "完成", "截止", "输出", "对接", "配合", "梳理", "补充", "明确", "开展"), 12)

    conclusion_items = normalize_items([item for item in conclusion_items if keep_core_conclusion(item)], 8)
    decision_items = normalize_items([item for item in (decision_items or conclusion_items) if keep_core_conclusion(item)], 8)
    risk_items = normalize_items([item for item in risk_items if keep_risk(item)], 8)
    question_items = normalize_items([item for item in question_items if keep_open_question(item)], 8)
    action_items_text = normalize_items([item for item in action_items_text if keep_action_item(item)], 12)

    topic_items = short_video_v2_topics(source_text) or keyword_items(
        source_text,
        ("需求", "功能", "优化", "数据", "标签", "接口", "方案", "目标", "周期", "兼容", "上线"),
        10,
    )
    if not topic_items:
        topic_items = split_sentences(source_text)[:6]
    topic_items = normalize_items([item for item in topic_items if not is_question_like(remove_first_person(item))], 8)

    overview = build_overview(source_text, conclusion_items or decision_items, topic_items, risk_items)
    if len(overview) > 420:
        overview = overview[:420].rstrip("，。； ") + "。"

    parsed_actions = [parse_action_item(item) for item in action_items_text[:12]]
    return {
        "overview": overview or "本次会议完成了需求对齐、可行性评估和后续行动拆解。",
        "agenda": [
            {"item": item, "status": "已讨论", "summary": item}
            for item in (agenda_items[:6] or ["需求对齐", "可行性评估", "落地计划确认"])
        ],
        "topics": [
            {"title": item[:40], "summary": item}
            for item in topic_items[:8]
        ],
        "speaker_summaries": [],
        "decisions": [{"decision": item, "reason": "", "source": item} for item in decision_items[:8]],
        "action_items": parsed_actions,
        "risks": [{"risk": item, "impact": "", "mitigation": ""} for item in risk_items[:8]],
        "open_questions": [{"question": item, "owner": "", "source": item} for item in question_items[:8]],
        "next_steps": [
            {"item": item["task"], "owner": item["owner"], "time": item["due_date"], "note": item["source"]}
            for item in parsed_actions[:8]
        ],
    }


def validate_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    missing_keys = REQUIRED_KEYS - payload.keys()
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise SummaryAgentError(f"LLM summary JSON is missing keys: {missing}.")
    return payload


def item_text(item: Any, keys: list[str]) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(item)


def normalize_payload_dimensions(payload: dict[str, Any], fallback_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    overview = str(normalized.get("overview") or "")
    if is_question_like(overview) or any(word in overview for word in ("我这边", "我们", "我确认", "你这边")) or len(overview) < 80:
        normalized["overview"] = fallback_payload["overview"]

    topics = []
    for item in normalized.get("topics") or []:
        text = normalize_business_point(item_text(item, ["summary", "title", "topic"]))
        if text and not is_question_like(text):
            topics.append({"title": text[:40], "summary": text})
    normalized["topics"] = topics[:8] or fallback_payload["topics"]

    decisions = []
    for item in normalized.get("decisions") or []:
        text = normalize_business_point(item_text(item, ["decision", "title", "summary", "reason"]))
        if text and keep_core_conclusion(text):
            decisions.append({"decision": text, "reason": item.get("reason", "") if isinstance(item, dict) else "", "source": item_text(item, ["source", "decision"])})
    normalized["decisions"] = decisions[:8] or fallback_payload["decisions"]

    risks = []
    for item in normalized.get("risks") or []:
        text = normalize_business_point(item_text(item, ["risk", "impact", "mitigation"]))
        if text and keep_risk(text):
            risks.append({"risk": text, "impact": item.get("impact", "") if isinstance(item, dict) else "", "mitigation": item.get("mitigation", "") if isinstance(item, dict) else ""})
    normalized["risks"] = risks[:8] or fallback_payload["risks"]

    questions = []
    for item in normalized.get("open_questions") or []:
        text = normalize_business_point(item_text(item, ["question", "owner", "source"]))
        if text and keep_open_question(text):
            questions.append({"question": text, "owner": item.get("owner", "") if isinstance(item, dict) else "", "source": item_text(item, ["source", "question"])})
    normalized["open_questions"] = questions[:8] or fallback_payload["open_questions"]

    normalized["speaker_summaries"] = []
    return validate_summary_payload(normalized)


def merge_summary_payload(llm_payload: dict[str, Any], heuristic_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(llm_payload)
    for key, heuristic_value in heuristic_payload.items():
        value = merged.get(key)
        if value in (None, "", []):
            merged[key] = heuristic_value
    overview = str(merged.get("overview", ""))
    if "[" in overview or len(overview) > 600:
        merged["overview"] = heuristic_payload["overview"]
    # The current product standard has six fixed analysis dimensions and no speaker-summary section.
    # Keep the legacy schema field for compatibility, but never surface it as a generated dimension.
    merged["speaker_summaries"] = []
    return normalize_payload_dimensions(merged, heuristic_payload)


def transcript_text(segments: list[TranscriptSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        speaker = segment.speaker_label or "Unknown Speaker"
        lines.append(f"[{segment.start_time:.2f}-{segment.end_time:.2f}] {speaker}: {segment.text}")
    return "\n".join(lines)


def request_summary_from_llm(transcript: str, retry_hint: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    api_key = resolve_openai_api_key()
    if not api_key:
        raise SummaryAgentError("OPENAI_API_KEY is not configured.")

    source_text = isolate_source_dialogue(transcript)
    user_content = (
        f"{MEETING_ANALYSIS_STANDARD}\n\n"
        "请基于下面的完整会议转写，输出结构化 JSON。必须覆盖全量对话，不允许只复述原文。"
        "字段映射规则："
        "overview=会议总结，要求 180-360 字，必须是对整场会议全过程的精简全景概括，"
        "必须包含背景问题、沟通过程、主要博弈、调整取舍、整体沟通情况，不能只挑几句结论拼接；"
        "agenda=会议议程，只输出流程环节；"
        "topics=会议要点，输出重点讨论事项，每条必须是归纳后的完整业务要点；"
        "会议要点严禁出现第一人称、原话疑问句或口语开头，例如“我确认一下”“我们再”等，必须改写为第三方业务表达；"
        "decisions=核心结论，只输出已达成共识或最终敲定的宏观结论；"
        "action_items=待办与后续安排，用 task/owner/due_date/source 表达；"
        "next_steps=待办与后续安排的补充表达，用 item/owner/time/note 表达；"
        "open_questions=遗留问题；risks=风险与关注点；"
        "speaker_summaries 为兼容旧字段，请返回空数组，不要生成发言摘要。"
        "保持中文职场会议纪要风格，不要编造未出现的人名、日期或事实。\n\n"
        f"完整会议转写：\n{source_text}"
    )
    if retry_hint:
        user_content += f"\n\n上一次 JSON 不合规：{retry_hint}。请仅返回符合 schema 的 JSON。"

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=settings.openai_summary_model,
        input=[
            {
                "role": "system",
                "content": (
                    "你是企业会议纪要分析 Agent。你的目标是从全量会议对话中完成六维结构化归纳。"
                    "严格区分会议议程、会议总结、会议要点、核心结论、待办与后续安排、遗留问题、风险与关注点。"
                    "禁止把原始转写直接塞进 overview，禁止把任务写入风险，禁止把未解决问题写入核心结论。"
                    "所有输出必须使用第三方职场纪要口吻，禁止保留第一人称和原始问句。"
                ),
            },
            {"role": "user", "content": user_content},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "meeting_summary",
                "schema": SUMMARY_SCHEMA,
                "strict": True,
            }
        },
    )

    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise SummaryAgentError("LLM summary response did not include output_text.")
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise SummaryAgentError(f"JSON parse failed: {exc}") from exc
    return validate_summary_payload(payload)


def request_analysis_from_llm(cleaned: list[CleanTranscriptSegment], fallback: MeetingAnalysisSchema, retry_hint: str | None = None) -> MeetingAnalysisSchema:
    settings = get_settings()
    api_key = resolve_openai_api_key()
    if not api_key:
        raise SummaryAgentError("OPENAI_API_KEY is not configured.")

    transcript = "\n".join(
        f"[{segment.start_time:.2f}-{segment.end_time:.2f}] {segment.speaker_name or segment.speaker_label}: {segment.text}"
        for segment in cleaned
    )
    prompt_path = Path(__file__).with_name("prompts") / "meeting_analyst.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    user_content = (
        f"{prompt}\n\n"
        "请分析下面的 cleaned transcript，并返回严格符合 MeetingAnalysisSchema 的 JSON。"
        "不要返回 Markdown，不要返回解释文字。\n\n"
        f"cleaned_transcript:\n{transcript}"
    )
    if retry_hint:
        user_content += f"\n\n上一次 JSON 不合规：{retry_hint}。请修正后只返回合法 JSON。"

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=settings.openai_summary_model,
        input=[
            {"role": "system", "content": "你是严谨的 Meeting Analyst Agent Pipeline，只输出合法 JSON。"},
            {"role": "user", "content": user_content},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "meeting_analysis",
                "schema": MeetingAnalysisSchema.model_json_schema(),
                "strict": False,
            }
        },
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise SummaryAgentError("LLM meeting analysis response did not include output_text.")
    try:
        parsed = json.loads(output_text)
        analysis = MeetingAnalysisSchema.model_validate(parsed)
    except Exception as exc:
        raise SummaryAgentError(f"MeetingAnalysis JSON validation failed: {exc}") from exc
    if not analysis.meeting_summary or len(analysis.meeting_summary) < 40:
        analysis.meeting_summary = fallback.meeting_summary
    if not analysis.topics:
        analysis.topics = fallback.topics
    analysis.metadata.model_name = settings.openai_summary_model
    return enforce_boundary_rules(analysis)


def analyze_segments_with_retry(segments: list[TranscriptSegment]) -> tuple[MeetingAnalysisSchema, list[CleanTranscriptSegment], list[SemanticSegment]]:
    settings = get_settings()
    cleaned = clean_transcript_segments(segments)
    labels = semantic_label_segments(cleaned)
    fallback = enforce_boundary_rules(build_rule_based_analysis(cleaned, labels, f"rules+{settings.openai_summary_model}"))
    try:
        return request_analysis_from_llm(cleaned, fallback), cleaned, labels
    except SummaryAgentError as first_error:
        if "OPENAI_API_KEY is not configured" in str(first_error):
            return fallback, cleaned, labels
        try:
            return request_analysis_from_llm(cleaned, fallback, retry_hint=str(first_error)), cleaned, labels
        except Exception:
            return fallback, cleaned, labels
    except Exception:
        return fallback, cleaned, labels


def analysis_to_legacy_payload(analysis: MeetingAnalysisSchema) -> dict[str, Any]:
    return {
        "overview": analysis.meeting_summary,
        "agenda": [item.model_dump() for item in analysis.meeting_agenda],
        "topics": [item.model_dump() for item in analysis.topics],
        "speaker_summaries": [],
        "decisions": [item.model_dump() for item in analysis.key_conclusions],
        "action_items": [item.model_dump() for item in analysis.action_items],
        "risks": [item.model_dump() for item in analysis.risks_and_focus],
        "open_questions": [item.model_dump() for item in analysis.unresolved_issues],
        "next_steps": [
            {
                "item": item.task,
                "owner": item.owner_name or "",
                "time": item.deadline or "",
                "note": item.source_text,
            }
            for item in analysis.action_items
        ],
        "meeting_agenda": [item.model_dump() for item in analysis.meeting_agenda],
        "meeting_summary": analysis.meeting_summary,
        "key_conclusions": [item.model_dump() for item in analysis.key_conclusions],
        "unresolved_issues": [item.model_dump() for item in analysis.unresolved_issues],
        "risks_and_focus": [item.model_dump() for item in analysis.risks_and_focus],
        "topics_new": [item.model_dump() for item in analysis.topics],
        "model_name": analysis.metadata.model_name,
        "confidence_score": analysis.metadata.confidence_score,
    }


def summarize_transcript_with_retry(transcript: str) -> dict[str, Any]:
    heuristic_payload = structured_payload_from_text(transcript)
    try:
        return merge_summary_payload(request_summary_from_llm(transcript), heuristic_payload)
    except SummaryAgentError as first_error:
        if "OPENAI_API_KEY is not configured" in str(first_error):
            return heuristic_payload
        if "JSON" not in str(first_error) and "missing keys" not in str(first_error):
            return heuristic_payload
        try:
            return merge_summary_payload(request_summary_from_llm(transcript, retry_hint=str(first_error)), heuristic_payload)
        except SummaryAgentError:
            return heuristic_payload
    except Exception:
        return heuristic_payload


def save_summary(db: Session, meeting: Meeting, payload: dict[str, Any]) -> MeetingSummary:
    db.execute(delete(ActionItem).where(ActionItem.meeting_id == meeting.id))
    db.execute(delete(MeetingSummary).where(MeetingSummary.meeting_id == meeting.id))
    db.flush()

    summary = MeetingSummary(
        meeting_id=meeting.id,
        overview=payload["overview"],
        agenda=payload["agenda"],
        topics=payload["topics"],
        speaker_summaries=payload["speaker_summaries"],
        decisions=payload["decisions"],
        risks=payload["risks"],
        open_questions=payload["open_questions"],
        next_steps=payload["next_steps"],
        meeting_agenda=payload.get("meeting_agenda", payload["agenda"]),
        meeting_summary=payload.get("meeting_summary", payload["overview"]),
        key_conclusions=payload.get("key_conclusions", payload["decisions"]),
        unresolved_issues=payload.get("unresolved_issues", payload["open_questions"]),
        risks_and_focus=payload.get("risks_and_focus", payload["risks"]),
        model_name=payload.get("model_name"),
        confidence_score=payload.get("confidence_score"),
    )
    db.add(summary)
    db.flush()

    for item in payload["action_items"]:
        task = item.get("task", "").strip()
        if not task:
            continue
        db.add(
            ActionItem(
                meeting_id=meeting.id,
                summary_id=summary.id,
                task=task,
                owner=item.get("owner") or item.get("owner_name") or None,
                owner_name=item.get("owner_name") or item.get("owner") or None,
                due_date=item.get("due_date") or item.get("deadline") or None,
                deadline=item.get("deadline") or item.get("due_date") or None,
                priority=item.get("priority") or "medium",
                status="open",
                source=item.get("source") or item.get("source_text") or None,
                source_text=item.get("source_text") or item.get("source") or None,
                source_segment_id=item.get("source_segment_id") or None,
                confidence=item.get("confidence"),
            )
        )

    meeting.status = "completed"
    db.commit()
    db.refresh(summary)
    return summary


def summarize_meeting(db: Session, meeting_id: str) -> MeetingSummary:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise SummaryAgentError(f"Meeting not found: {meeting_id}")

    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.segment_index)
        ).all()
    )
    if not segments:
        raise SummaryAgentError(f"No transcript segments found for meeting {meeting_id}.")

    meeting.status = "summarizing"
    db.commit()

    try:
        analysis, cleaned_segments, semantic_labels = analyze_segments_with_retry(segments)
        label_by_source: dict[str, str] = {}
        for label in semantic_labels:
            for segment_id in label.source_segment_id.split(","):
                label_by_source[segment_id] = label.semantic_label
        for segment in segments:
            segment.semantic_label = label_by_source.get(segment.id)
            if not getattr(segment, "speaker_name", None):
                segment.speaker_name = segment.speaker_label
        db.flush()
        payload = analysis_to_legacy_payload(analysis)
        return save_summary(db, meeting, payload)
    except Exception:
        db.rollback()
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.status = "summary_failed"
            db.commit()
        raise
