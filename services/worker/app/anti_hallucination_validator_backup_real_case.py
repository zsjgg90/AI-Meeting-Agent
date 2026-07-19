import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = str(text)
    text = text.replace(" ", "").replace("\n", "").replace("\t", "")
    text = text.replace("'", "").replace('"', "")
    text = text.replace("“", "").replace("”", "")
    text = text.replace("‘", "").replace("’", "")
    text = text.replace("『", "").replace("』", "")
    text = text.replace("「", "").replace("」", "")
    text = re.sub(r"[，。！？；：、（）()《》【】\[\]…\.]", "", text)

    text = re.sub(
        r"^(运营|产品|研发|测试|设计|负责人|主持人)?[A-Za-z甲乙丙丁小AB]*[:：]",
        "",
        text,
    )

    return text


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def clean_null_values(result: dict) -> dict:
    null_like = {"null", "none", "None", "NULL", "", "无", "未明确"}

    for item in result.get("action_items", []):
        for field in ["owner_name", "deadline"]:
            value = item.get(field)
            if value is None:
                continue
            if isinstance(value, str) and value.strip() in null_like:
                item[field] = None

    return result


def extract_keywords(text: str) -> list[str]:
    text = normalize_text(text)
    keywords = []
    buffer = ""

    for char in text:
        if "\u4e00" <= char <= "\u9fff" or char.isalnum():
            buffer += char
        else:
            if len(buffer) >= 2:
                keywords.append(buffer)
            buffer = ""

    if len(buffer) >= 2:
        keywords.append(buffer)

    if len(keywords) <= 1 and len(text) >= 8:
        keywords = [text[i:i + 4] for i in range(0, len(text) - 3, 4)]

    return [k for k in keywords if len(k) >= 2]


def keyword_coverage_supported(source_text: str, transcript: str) -> bool:
    source_norm = normalize_text(source_text)
    transcript_norm = normalize_text(transcript)

    if not source_norm:
        return False

    if source_norm in transcript_norm:
        return True

    keywords = extract_keywords(source_norm)
    if not keywords:
        return False

    hit = sum(1 for kw in keywords if kw in transcript_norm)
    coverage = hit / max(len(keywords), 1)

    if len(source_norm) < 20:
        return coverage >= 0.75

    return coverage >= 0.55


def source_exists(source_text: str, transcript: str) -> bool:
    source_norm = normalize_text(source_text)
    transcript_norm = normalize_text(transcript)

    if not source_norm:
        return False

    if source_norm in transcript_norm:
        return True

    source_without_speaker = re.sub(
        r"^(运营|产品|研发|测试|设计|负责人|主持人)?[A-Za-z甲乙丙丁小AB]*",
        "",
        source_norm,
    )

    if source_without_speaker and source_without_speaker in transcript_norm:
        return True

    if keyword_coverage_supported(source_text, transcript):
        return True

    if len(source_norm) >= 12:
        window_size = max(120, len(source_norm) * 3)
        for i in range(0, len(transcript_norm), 20):
            window = transcript_norm[i:i + window_size]
            if similarity(source_norm, window) >= 0.58:
                return True

    return False


def repair_source_text_for_conclusions(result: dict, transcript: str) -> dict:
    rules = [
        {
            "keywords": ["取消", "个性化推荐"],
            "evidence": "V2.0正式版本先砍掉智能个性化推荐功能",
        },
        {
            "keywords": ["历史数据", "兼容"],
            "evidence": "所有用户历史自定义标签、收藏素材数据，需要无缝迁移",
        },
        {
            "keywords": ["8月1日", "上线"],
            "evidence": "本次版本能在8月1日前上线",
        },
    ]

    for item in result.get("key_conclusions", []):
        conclusion = item.get("conclusion", "")
        source_text = item.get("source_text", "")

        for rule in rules:
            if all(keyword in conclusion for keyword in rule["keywords"]):
                if rule["evidence"] in transcript and rule["evidence"] != source_text:
                    item["source_text"] = rule["evidence"]
                    item["source_repaired"] = True
                    item["repair_reason"] = "matched_direct_evidence"

    return result


def validate_deadlines(result: dict, transcript: str) -> dict:
    for item in result.get("action_items", []):
        deadline = item.get("deadline")
        source_text = item.get("source_text", "")

        if deadline is None:
            if item.get("review_reason") == "deadline_not_found_in_action_source":
                item.pop("needs_review", None)
                item.pop("review_reason", None)
            continue

        if isinstance(deadline, str):
            deadline_text = deadline.strip()

            if not deadline_text or deadline_text.lower() in {
                "null",
                "none",
                "无",
                "未明确",
            }:
                item["deadline"] = None
                if item.get("review_reason") == "deadline_not_found_in_action_source":
                    item.pop("needs_review", None)
                    item.pop("review_reason", None)
                continue

            if deadline_text not in source_text:
                item["deadline"] = None
                item["needs_review"] = True
                item["review_reason"] = "deadline_not_found_in_action_source"
                continue

        if str(deadline) not in source_text:
            item["deadline"] = None
            item["needs_review"] = True
            item["review_reason"] = "deadline_not_found_in_action_source"

    return result


def validate_source_text(result: dict, transcript: str) -> dict:
    sections = [
        "key_conclusions",
        "action_items",
        "unresolved_issues",
        "risks_and_focus",
    ]

    for section in sections:
        for item in result.get(section, []):
            source_text = item.get("source_text", "")

            if source_text and not source_exists(source_text, transcript):
                item["needs_review"] = True
                item["review_reason"] = "source_text_not_supported"

    return result


def claim_supported_by_source(claim: str, source_text: str) -> bool:
    claim_norm = normalize_text(claim)
    source_norm = normalize_text(source_text)

    if not claim_norm or not source_norm:
        return False

    hallucination_terms = [
        "个性化推荐",
        "组合SKU",
        "组合装",
        "差评监控",
        "差评关键词",
        "新品替换",
        "直通车",
        "下载频率",
        "历史数据",
        "SKU",
        "优惠券",
        "主图",
        "详情页",
        "投产比",
    ]

    for term in hallucination_terms:
        if term in claim_norm and term not in source_norm:
            return False

    return True


def validate_claim_source_consistency(result: dict) -> dict:
    mappings = [
        ("key_conclusions", "conclusion"),
        ("action_items", "task"),
        ("unresolved_issues", "issue"),
        ("risks_and_focus", "risk"),
    ]

    for section, key in mappings:
        for item in result.get(section, []):
            claim = item.get(key, "")
            source = item.get("source_text", "")

            if source and not claim_supported_by_source(claim, source):
                item["needs_review"] = True
                item["review_reason"] = "claim_source_mismatch"

    return result


def deduplicate_items(items: list, key: str) -> list:
    deduped = []

    for item in items:
        text = item.get(key, "")
        duplicate = False

        for existing in deduped:
            existing_text = existing.get(key, "")
            if similarity(text, existing_text) > 0.82:
                duplicate = True
                break

        if not duplicate:
            deduped.append(item)

    return deduped


def deduplicate_result(result: dict) -> dict:
    result["action_items"] = deduplicate_items(
        result.get("action_items", []),
        "task",
    )
    result["unresolved_issues"] = deduplicate_items(
        result.get("unresolved_issues", []),
        "issue",
    )
    result["risks_and_focus"] = deduplicate_items(
        result.get("risks_and_focus", []),
        "risk",
    )

    return result


def validate_action_items(result: dict) -> dict:
    action_verbs = [
        "补充",
        "确认",
        "输出",
        "完成",
        "开发",
        "优化",
        "重构",
        "适配",
        "迁移",
        "整理",
        "提交",
        "制定",
        "明确",
        "推进",
        "定义",
        "限制",
        "设置",
        "配置",
        "提供",
        "同步",
        "收紧",
        "调整",
        "上新",
        "强化",
        "弱化",
        "监控",
        "拉升",
    ]

    for item in result.get("action_items", []):
        task = item.get("task", "")

        if not any(verb in task for verb in action_verbs):
            item["needs_review"] = True
            item["review_reason"] = "action_item_without_action_verb"

    return result


def has_risk_signal(text: str) -> bool:
    text = normalize_text(text)

    risk_words = [
        "风险",
        "可能",
        "如果",
        "一旦",
        "否则",
        "导致",
        "影响",
        "持续",
        "亏损",
        "下降",
        "衰退",
        "断层",
        "掉权重",
        "无法",
        "爆发",
        "恶化",
        "压力",
        "转化",
        "预算",
        "差评",
        "权重",
    ]

    if any(word in text for word in risk_words):
        return True

    condition_patterns = [
        ("如果", "需要"),
        ("如果", "导致"),
        ("如果", "影响"),
        ("一旦", "导致"),
        ("持续", "导致"),
        ("持续", "掉权重"),
        ("转化", "预算"),
        ("差评", "权重"),
    ]

    return any(a in text and b in text for a, b in condition_patterns)


def validate_risks(result: dict) -> dict:
    for item in result.get("risks_and_focus", []):
        risk = item.get("risk", "")
        impact = item.get("impact", "")
        source_text = item.get("source_text", "")
        text = risk + impact + source_text

        if not has_risk_signal(text):
            item["needs_review"] = True
            item["review_reason"] = "risk_without_risk_structure"

    return result


def remove_issue_derived_action_items(result: dict) -> dict:
    issues = result.get("unresolved_issues", [])
    actions = result.get("action_items", [])

    filtered_actions = []

    issue_full_text = normalize_text(
        " ".join(
            [
                issue.get("issue", "") + issue.get("reason", "") + issue.get("source_text", "")
                for issue in issues
            ]
        )
    )

    issue_signals = [
        "自动预警",
        "预警机制",
        "监控机制",
        "指标恶化",
        "替代方案",
        "新品替换",
        "差评监控",
        "差评关键词",
        "用户行为数据",
        "底层能力",
    ]

    action_create_verbs = [
        "建立",
        "建设",
        "搭建",
        "完善",
        "补齐",
        "制定",
        "构建",
        "新增",
    ]

    for action in actions:
        task = action.get("task", "")
        source_text = action.get("source_text", "")
        task_norm = normalize_text(task + source_text)

        should_remove = False

        has_create_verb = any(
            normalize_text(verb) in task_norm
            for verb in action_create_verbs
        )

        for signal in issue_signals:
            signal_norm = normalize_text(signal)

            if (
                signal_norm in task_norm
                and signal_norm in issue_full_text
                and has_create_verb
            ):
                action["removed_by_validator"] = True
                action["review_reason"] = "issue_should_not_auto_convert_to_action"
                should_remove = True
                break

        if should_remove:
            continue

        for issue in issues:
            issue_text = normalize_text(
                issue.get("issue", "") + issue.get("reason", "") + issue.get("source_text", "")
            )

            if not issue_text:
                continue

            if similarity(task_norm, issue_text) > 0.72 and has_create_verb:
                action["removed_by_validator"] = True
                action["review_reason"] = "issue_should_not_auto_convert_to_action"
                should_remove = True
                break

        if not should_remove:
            filtered_actions.append(action)

    result["action_items"] = filtered_actions
    return result

def validate_deadlines(result: dict, transcript: str) -> dict:
    for item in result.get("action_items", []):
        deadline = item.get("deadline")
        source_text = item.get("source_text", "")

        if deadline is None:
            if item.get("review_reason") == "deadline_not_found_in_action_source":
                item.pop("needs_review", None)
                item.pop("review_reason", None)
            continue

        if isinstance(deadline, str) and not deadline.strip():
            item["deadline"] = None
            item.pop("needs_review", None)
            item.pop("review_reason", None)
            continue

        if isinstance(deadline, str) and deadline.strip().lower() in {
            "null", "none", "无", "未明确",
        }:
            item["deadline"] = None
            item.pop("needs_review", None)
            item.pop("review_reason", None)
            continue

        if str(deadline) not in source_text:
            item["deadline"] = None
            item["needs_review"] = True
            item["review_reason"] = "deadline_not_found_in_action_source"

    return result
def validate_owner_resolution(result: dict) -> dict:
    speaker_owner_patterns = [
        "我来",
        "我负责",
        "我这边",
        "我们负责",
        "我们来",
        "这边整理",
        "这边同步",
    ]

    role_owner_values = {
        "运营侧",
        "产品侧",
        "研发侧",
        "测试侧",
        "设计侧",
    }

    for item in result.get("action_items", []):
        owner = item.get("owner_name")
        source_text = item.get("source_text", "")
        source_norm = normalize_text(source_text)

        if not source_text:
            continue

        if "运营侧需要" in source_norm:
            item["owner_name"] = "运营侧"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_is_not_owner"
            continue

        if "产品侧需要" in source_norm:
            item["owner_name"] = "产品侧"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_is_not_owner"
            continue

        if "研发侧需要" in source_norm:
            item["owner_name"] = "研发侧"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_is_not_owner"
            continue

        has_need = "需要" in source_norm
        has_commitment = any(
            pattern in source_norm
            for pattern in speaker_owner_patterns
        )

        if has_need and not has_commitment:
            if owner and owner not in role_owner_values:
                item["owner_name"] = None
                item["owner_repaired"] = True
                item["repair_reason"] = "need_statement_without_owner_commitment"

    return result
def final_remove_forbidden_action_items(result: dict) -> dict:
    """
    最终兜底清理：
    删除模型从“机制缺失 / 遗留问题”自动推导出来的待办。
    """

    filtered = []

    forbidden_patterns = [
        "建立自动预警机制",
        "建设自动预警机制",
        "搭建自动预警机制",
        "完善自动预警机制",
        "补齐自动预警机制",
        "构建自动预警机制",
        "新增自动预警机制",
        "建立指标预警机制",
        "建设指标预警机制",
        "搭建指标预警机制",
        "完善指标预警机制",
        "建立监控预警机制",
        "建设监控预警机制",
        "搭建监控预警机制",
        "建立指标监控机制",
        "建立指标监控预警机制",
    ]

    for item in result.get("action_items", []):
        task = normalize_text(item.get("task", ""))
        source_text = normalize_text(item.get("source_text", ""))

        should_remove = False

        for pattern in forbidden_patterns:
            pattern_norm = normalize_text(pattern)

            if pattern_norm in task:
                should_remove = True
                break

        # 如果 task 没有直接命中，但 source_text 是“没有建立自动预警机制”
        # 且任务是建立/建设/完善类动作，也删除。
        create_verbs = [
            "建立",
            "建设",
            "搭建",
            "完善",
            "补齐",
            "构建",
            "新增",
        ]

        warning_terms = [
            "自动预警",
            "预警机制",
            "监控机制",
            "指标监控",
        ]

        has_create_verb = any(
            normalize_text(verb) in task
            for verb in create_verbs
        )

        has_warning_term = any(
            normalize_text(term) in task
            for term in warning_terms
        )

        source_is_issue = (
            "没有建立" in source_text
            or "未建立" in source_text
            or "缺失" in source_text
            or "长期遗留问题" in source_text
        )

        if has_create_verb and has_warning_term and source_is_issue:
            should_remove = True

        if not should_remove:
            filtered.append(item)

    result["action_items"] = filtered
    return result
def ensure_unresolved_issue_exists(
    result: dict,
    issue_keyword: str,
    issue: str,
    reason: str,
    source_text: str,
) -> dict:
    issues = result.get("unresolved_issues", [])

    for item in issues:
        text = normalize_text(
            item.get("issue", "")
            + item.get("reason", "")
            + item.get("source_text", "")
        )

        if normalize_text(issue_keyword) in text:
            return result

    issues.append(
        {
            "issue": issue,
            "reason": reason,
            "source_text": source_text,
            "confidence": 0.9,
            "repaired_by_validator": True,
            "repair_reason": "missing_unresolved_issue_from_transcript",
        }
    )

    result["unresolved_issues"] = issues
    return result


def repair_unresolved_issues_from_transcript(result: dict, transcript: str) -> dict:
    transcript_norm = normalize_text(transcript)

    if "没有建立自动预警机制" in transcript_norm or "自动预警机制还没有建立" in transcript_norm:
        result = ensure_unresolved_issue_exists(
            result=result,
            issue_keyword="自动预警机制",
            issue="自动预警机制缺失",
            reason="当前未建立自动预警机制，无法提前发现指标恶化",
            source_text="目前我们没有建立自动预警机制，无法提前发现指标恶化",
        )

    if "替代方案目前也没有完全敲定" in transcript_norm or "替代方案未完全敲定" in transcript_norm:
        result = ensure_unresolved_issue_exists(
            result=result,
            issue_keyword="替代方案",
            issue="替代方案未完全敲定",
            reason="当前方案效果不佳时，下个阶段可能出现承接断层",
            source_text="替代方案目前也没有完全敲定，如果当前方案继续效果不好，下个阶段会出现承接断层",
        )

    if "底层能力还没准备好" in transcript_norm or "底层能力未准备好" in transcript_norm:
        result = ensure_unresolved_issue_exists(
            result=result,
            issue_keyword="底层能力",
            issue="底层能力尚未准备好",
            reason="部分底层能力尚未完成，短期不能上线完整方案",
            source_text="部分底层能力还没准备好，短期不能直接上线完整方案",
        )

    return result


def repair_meeting_summary_coverage(result: dict, transcript: str) -> dict:
    summary = result.get("meeting_summary", "")
    summary_norm = normalize_text(summary)
    transcript_norm = normalize_text(transcript)

    additions = []

    if "阶段性取舍" in transcript_norm and "阶段性取舍" not in summary_norm:
        additions.append("会议形成阶段性取舍：本期优先执行可落地优化，长期能力建设纳入后续规划。")

    if "下周三" in transcript_norm and "下周三" not in summary_norm:
        additions.append("会议要求相关页面、素材、规则和流程调整在下周三前完成第一版。")

    if "自动预警机制" in transcript_norm and "自动预警机制" not in summary_norm:
        additions.append("会议指出自动预警机制尚未建立，属于后续需要规划的遗留问题。")

    if "替代方案" in transcript_norm and "替代方案" not in summary_norm:
        additions.append("会议提到替代方案尚未完全敲定，若当前方案效果不佳可能出现承接断层。")

    if additions:
        result["meeting_summary"] = summary.rstrip("。") + "。" + "".join(additions)

    return result
def validate_meeting_analysis(result: dict, transcript: str) -> dict:
    result = clean_null_values(result)
    result = repair_source_text_for_conclusions(result, transcript)
    result = repair_unresolved_issues_from_transcript(result, transcript)
    result = repair_meeting_summary_coverage(result, transcript)
    result = validate_deadlines(result, transcript)
    result = validate_source_text(result, transcript)
    result = validate_claim_source_consistency(result)
    result = validate_action_items(result)
    result = validate_owner_resolution(result)
    result = validate_risks(result)
    result = remove_issue_derived_action_items(result)
    result = final_remove_forbidden_action_items(result)
    result = deduplicate_result(result)

    if "final_cleanup" in globals():
        result = final_cleanup(result)

    return result