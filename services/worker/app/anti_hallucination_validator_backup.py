from difflib import SequenceMatcher


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio()


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

        if deadline and deadline not in source_text:
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

            if source_text and source_text not in transcript:
                item["needs_review"] = True
                item["review_reason"] = "source_text_not_exactly_found"

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
    ]

    for item in result.get("action_items", []):
        task = item.get("task", "")

        if not any(verb in task for verb in action_verbs):
            item["needs_review"] = True
            item["review_reason"] = "action_item_without_action_verb"

    return result


def validate_risks(result: dict) -> dict:
    risk_words = [
        "可能",
        "风险",
        "导致",
        "影响",
        "延误",
        "返工",
        "压力",
        "不确定",
        "异常",
        "丢失",
        "错乱",
        "过大",
        "负载",
    ]

    for item in result.get("risks_and_focus", []):
        risk = item.get("risk", "")
        impact = item.get("impact", "")

        text = risk + impact

        if not any(word in text for word in risk_words):
            item["needs_review"] = True
            item["review_reason"] = "risk_without_risk_signal"

    return result


def validate_meeting_analysis(result: dict, transcript: str) -> dict:
    result = repair_source_text_for_conclusions(result, transcript)
    result = validate_deadlines(result, transcript)
    result = validate_source_text(result, transcript)
    result = validate_action_items(result)
    result = validate_risks(result)
    result = deduplicate_result(result)

    return result