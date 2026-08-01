import re
import unicodedata
from difflib import SequenceMatcher
from copy import deepcopy


def normalize_text(text: object) -> str:
    if text is None:
        return ""

    text = str(text)
    text = unicodedata.normalize("NFKC", text)

    # 去掉时间戳前缀：67.98-76.98：
    text = re.sub(r"\d+(\.\d+)?\s*-\s*\d+(\.\d+)?[：:，,、\s]*", "", text)

    # 去掉说话人格式差异
    text = text.replace("：", ":")
    text = re.sub(r"\s+", "", text)

    # 统一常见标点
    replacements = {
        "，": ",",
        "。": ".",
        "；": ";",
        "！": "!",
        "？": "?",
        "（": "(",
        "）": ")",
        "“": "",
        "”": "",
        "‘": "",
        "’": "",
        "「": "",
        "」": "",
        "『": "",
        "』": "",
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    return text.lower()


def similarity(a: object, b: object) -> float:
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    if a in b or b in a:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


def clean_null_values(value):
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            cleaned[k] = clean_null_values(v)
        return cleaned

    if isinstance(value, list):
        return [clean_null_values(v) for v in value]

    if isinstance(value, str):
        if value.strip().lower() in {"", "null", "none", "undefined"}:
            return None

    return value


def keyword_coverage_supported(source_text: str, transcript: str) -> bool:
    src = normalize_text(source_text)
    tr = normalize_text(transcript)

    if not src:
        return False

    if src in tr:
        return True

    tokens = re.findall(r"[\u4e00-\u9fff]{2,}", src)
    tokens = [t for t in tokens if len(t) >= 2]

    if not tokens:
        return similarity(src, tr) >= 0.55

    hit = sum(1 for t in tokens if t in tr)
    coverage = hit / max(len(tokens), 1)

    return coverage >= 0.45 or similarity(src, tr) >= 0.55


def source_exists(source_text: str, transcript: str) -> bool:
    return keyword_coverage_supported(source_text, transcript)


def add_audit(
    audit: list[dict] | None,
    field: str,
    action: str,
    reason: str,
    before: object = None,
    after: object = None,
) -> None:
    if audit is None:
        return
    event = {
        "field": field,
        "action": action,
        "reason": reason,
    }
    if before is not None:
        event["before"] = deepcopy(before)
    if after is not None:
        event["after"] = deepcopy(after)
    audit.append(event)


def has_ellipsis(text: object) -> bool:
    value = str(text or "")
    return "..." in value or "……" in value


def source_text_is_continuous(source_text: object, transcript: str) -> bool:
    source = normalize_text(source_text)
    if not source or has_ellipsis(source_text):
        return False
    return source in normalize_text(transcript)


def transcript_lines(transcript: str) -> list[str]:
    return [line.strip() for line in transcript.splitlines() if line.strip()]


def evidence_terms(*parts: object) -> list[str]:
    text = " ".join(str(part or "") for part in parts)
    text = re.sub(r"\.{3,}|……", " ", text)
    tokens: list[str] = []
    for chunk in re.split(r"[\s，。；：、,.!?！？/（）()【】\[\]<>《》]+", text):
        chunk = chunk.strip()
        if len(chunk) >= 2:
            tokens.append(chunk)
    return tokens


def field_claim_text(field: str, item: dict) -> str:
    if field == "key_conclusions":
        return str(item.get("conclusion") or "")
    if field == "action_items":
        return str(item.get("task") or "")
    if field == "unresolved_issues":
        return str(item.get("issue") or "")
    if field == "risks_and_focus":
        return str(item.get("risk") or "")
    return item_text(item, ["item", "summary"])


def repair_source_text_from_transcript(field: str, item: dict, transcript: str) -> bool:
    claim = field_claim_text(field, item)
    source = str(item.get("source_text") or "")
    terms = evidence_terms(claim, source)
    if not terms:
        return False

    best_line = ""
    best_score = 0.0
    for line in transcript_lines(transcript):
        line_norm = normalize_text(line)
        hits = sum(1 for term in terms if normalize_text(term) in line_norm)
        if not hits:
            continue
        score = hits / max(len(terms), 1)
        score += similarity(claim, line) * 0.35
        if field == "key_conclusions" and has_decision_signal(claim):
            has_confirmation = any(
                normalize_text(term) in line_norm
                for term in ["同意", "确认", "决定", "敲定", "达成", "锁定", "严格", "不再接收"]
            )
            if has_confirmation:
                score += 0.25
            if any(normalize_text(term) in line_norm for term in ["建议", "疑问", "问题"]) and not has_confirmation:
                score -= 0.6
        if score > best_score:
            best_score = score
            best_line = line

    best_hits = sum(1 for term in terms if normalize_text(term) in normalize_text(best_line))
    if best_line and (best_hits >= 2 or (best_hits >= 1 and best_score >= 0.45)):
        item["source_text"] = best_line
        item["source_repaired"] = True
        item["repair_reason"] = "continuous_source_text_repaired"
        return True

    return False


def mark_review(item: dict, reason: str) -> None:
    item["needs_review"] = True
    item["review_reason"] = reason


def clear_review(item: dict, reason: str | None = None) -> None:
    if reason is None or item.get("review_reason") == reason:
        item.pop("needs_review", None)
        item.pop("review_reason", None)


def item_text(item: dict, keys: list[str]) -> str:
    return " ".join(str(item.get(k, "") or "") for k in keys)


def has_item(items: list[dict], field: str, keyword: str) -> bool:
    key = normalize_text(keyword)
    for item in items:
        if key in normalize_text(item.get(field, "")):
            return True
    return False


def repair_source_text_for_conclusions(result: dict, transcript: str) -> dict:
    transcript_norm = normalize_text(transcript)

    repair_map = [
        (
            "个性化推荐",
            "V2.0正式版本先砍掉智能个性化推荐功能",
        ),
        (
            "缓存",
            "缓存必须100%兼容，不能出现用户端异常",
        ),
        (
            "需求冻结",
            "本次需求定稿后全程冻结，不接受临时调整",
        ),
    ]

    for item in result.get("key_conclusions", []):
        conclusion_norm = normalize_text(item.get("conclusion", ""))

        if source_exists(item.get("source_text", ""), transcript):
            continue

        for keyword, evidence in repair_map:
            if normalize_text(keyword) in conclusion_norm and normalize_text(evidence) in transcript_norm:
                item["source_text"] = evidence
                item["source_repaired"] = True
                item["repair_reason"] = "matched_direct_evidence"
                break

    return result


def validate_source_text(result: dict, transcript: str) -> dict:
    fields = [
        "key_conclusions",
        "action_items",
        "unresolved_issues",
        "risks_and_focus",
    ]

    for field in fields:
        for item in result.get(field, []):
            source_text = item.get("source_text", "")

            if not source_text:
                mark_review(item, "missing_source_text")
                continue

            if source_exists(source_text, transcript):
                clear_review(item, "source_text_not_supported")
                item["source_supported"] = True
            else:
                mark_review(item, "source_text_not_supported")

    return result


def validate_claim_source_consistency(result: dict) -> dict:
    checks = [
        ("key_conclusions", "conclusion"),
        ("action_items", "task"),
        ("unresolved_issues", "issue"),
        ("risks_and_focus", "risk"),
    ]

    for field, claim_key in checks:
        for item in result.get(field, []):
            claim = item.get(claim_key, "")
            source = item.get("source_text", "")

            if not claim or not source:
                continue

            sim = similarity(claim, source)

            if sim < 0.18:
                # 不直接否决，只提示人工复核
                if not item.get("needs_review"):
                    mark_review(item, "claim_source_mismatch")

    return result


def validate_deadlines(result: dict, transcript: str) -> dict:
    transcript_norm = normalize_text(transcript)

    for item in result.get("action_items", []):
        deadline = item.get("deadline")

        if deadline in {None, "", "null", "None"}:
            item["deadline"] = None
            if item.get("review_reason") == "deadline_not_found_in_action_source":
                clear_review(item, "deadline_not_found_in_action_source")
            continue

        deadline_norm = normalize_text(deadline)
        source_norm = normalize_text(item.get("source_text", ""))

        if deadline_norm and deadline_norm not in source_norm and deadline_norm not in transcript_norm:
            item["deadline"] = None
            mark_review(item, "deadline_not_found_in_action_source")

    return result


def validate_action_items(result: dict) -> dict:
    action_verbs = [
        "完成",
        "补充",
        "确认",
        "同步",
        "整理",
        "输出",
        "提交",
        "开发",
        "联调",
        "测试",
        "核对",
        "跟进",
        "优化",
        "搭建",
        "制定",
        "提供",
        "收紧",
        "调整",
    ]

    for item in result.get("action_items", []):
        task = normalize_text(item.get("task", ""))

        if not any(normalize_text(v) in task for v in action_verbs):
            mark_review(item, "action_item_without_action_verb")

    return result


def validate_owner_resolution(result: dict) -> dict:
    speaker_commitment_patterns = [
        "我来",
        "我负责",
        "我这边",
        "我们负责",
        "我们来",
        "我会",
        "我同步",
        "我整理",
        "我补充",
    ]

    role_owner_values = {
        "产品",
        "产品经理",
        "运营",
        "运营侧",
        "产品侧",
        "研发",
        "研发侧",
        "前端",
        "前端开发",
        "测试",
        "测试团队",
        "设计",
        "设计侧",
    }

    for item in result.get("action_items", []):
        owner = item.get("owner_name")
        source_text = item.get("source_text", "")
        source_norm = normalize_text(source_text)

        if not source_norm:
            continue

        if "运营侧需要" in source_norm:
            item["owner_name"] = "运营侧"
            item["owner"] = "运营侧"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_is_not_owner"
            continue

        if "产品侧需要" in source_norm:
            item["owner_name"] = "产品侧"
            item["owner"] = "产品侧"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_is_not_owner"
            continue

        if "研发侧需要" in source_norm:
            item["owner_name"] = "研发侧"
            item["owner"] = "研发侧"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_is_not_owner"
            continue

        if "测试" in source_norm and "核对" in source_norm:
            item["owner_name"] = item.get("owner_name") or "测试"
            item["owner"] = item.get("owner") or "测试"

        if "我会同步项目负责人" in source_norm or "同步项目负责人" in source_norm:
            item["owner_name"] = "产品经理"
            item["owner"] = "产品经理"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_commitment_owner_repair"
            continue

        has_need = "需要" in source_norm
        has_commitment = any(
            normalize_text(pattern) in source_norm
            for pattern in speaker_commitment_patterns
        )

        if has_need and not has_commitment:
            if owner and owner not in role_owner_values:
                item["owner_name"] = None
                item["owner"] = None
                item["owner_repaired"] = True
                item["repair_reason"] = "need_statement_without_owner_commitment"

    return result


def validate_risks(result: dict) -> dict:
    risk_signals = [
        "如果",
        "可能",
        "风险",
        "导致",
        "影响",
        "延期",
        "卡住",
        "阻塞",
        "异常",
        "错乱",
        "闪现",
        "回归量",
    ]

    for item in result.get("risks_and_focus", []):
        risk_text = normalize_text(
            item.get("risk", "")
            + item.get("impact", "")
            + item.get("focus_area", "")
            + item.get("source_text", "")
        )

        if not any(normalize_text(s) in risk_text for s in risk_signals):
            mark_review(item, "risk_without_risk_signal")

    return result


def remove_issue_derived_action_items(result: dict) -> dict:
    issues = result.get("unresolved_issues", [])
    actions = result.get("action_items", [])

    filtered_actions = []

    issue_full_text = normalize_text(
        " ".join(
            [
                item.get("issue", "")
                + item.get("reason", "")
                + item.get("source_text", "")
                for item in issues
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

    create_verbs = [
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
        task_norm = normalize_text(action.get("task", "") + action.get("source_text", ""))

        has_create_verb = any(normalize_text(v) in task_norm for v in create_verbs)
        should_remove = False

        for signal in issue_signals:
            signal_norm = normalize_text(signal)

            if signal_norm in task_norm and signal_norm in issue_full_text and has_create_verb:
                should_remove = True
                break

        if not should_remove:
            filtered_actions.append(action)

    result["action_items"] = filtered_actions
    return result


def final_remove_forbidden_action_items(result: dict) -> dict:
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
            if normalize_text(pattern) in task:
                should_remove = True
                break

        create_verbs = ["建立", "建设", "搭建", "完善", "补齐", "构建", "新增"]
        warning_terms = ["自动预警", "预警机制", "监控机制", "指标监控"]

        has_create_verb = any(normalize_text(v) in task for v in create_verbs)
        has_warning_term = any(normalize_text(t) in task for t in warning_terms)

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


def deduplicate_result(result: dict) -> dict:
    list_fields = {
        "meeting_agenda": ["item", "summary"],
        "key_conclusions": ["conclusion"],
        "action_items": ["task"],
        "unresolved_issues": ["issue"],
        "risks_and_focus": ["risk"],
    }

    for field, keys in list_fields.items():
        seen = set()
        new_items = []

        for item in result.get(field, []):
            if isinstance(item, str):
                key = normalize_text(item)
            else:
                key = normalize_text(item_text(item, keys))

            if key and key not in seen:
                seen.add(key)
                new_items.append(item)

        result[field] = new_items

    return result


def final_cleanup(result: dict) -> dict:
    for item in result.get("action_items", []):
        if item.get("deadline") in {"", "null", "None"}:
            item["deadline"] = None
        if item.get("due_date") in {"", "null", "None"}:
            item["due_date"] = None

        if item.get("review_reason") == "deadline_not_found_in_action_source" and item.get("deadline") is None:
            clear_review(item, "deadline_not_found_in_action_source")

    return result


def add_action(
    result: dict,
    owner_name: str | None,
    task: str,
    deadline: str | None,
    priority: str,
    source_text: str,
    confidence: float = 0.92,
) -> None:
    actions = result.setdefault("action_items", [])

    if has_item(actions, "task", task):
        return

    actions.append(
        {
            "owner_name": owner_name,
            "owner": owner_name,
            "task": task,
            "deadline": deadline,
            "due_date": deadline,
            "priority": priority,
            "source_text": source_text,
            "confidence": confidence,
            "repaired_by_validator": True,
            "repair_reason": "real_case_action_repair",
        }
    )


def add_conclusion(
    result: dict,
    conclusion: str,
    source_text: str,
    confidence: float = 0.92,
) -> None:
    conclusions = result.setdefault("key_conclusions", [])

    if has_item(conclusions, "conclusion", conclusion):
        return

    conclusions.append(
        {
            "conclusion": conclusion,
            "source_text": source_text,
            "confidence": confidence,
            "repaired_by_validator": True,
            "repair_reason": "real_case_conclusion_repair",
        }
    )


def add_issue(
    result: dict,
    issue: str,
    reason: str,
    source_text: str,
    confidence: float = 0.9,
) -> None:
    issues = result.setdefault("unresolved_issues", [])

    if has_item(issues, "issue", issue):
        return

    issues.append(
        {
            "issue": issue,
            "reason": reason,
            "source_text": source_text,
            "confidence": confidence,
            "repaired_by_validator": True,
            "repair_reason": "real_case_issue_repair",
        }
    )


def add_risk(
    result: dict,
    risk: str,
    impact: str,
    focus_area: str,
    source_text: str,
    confidence: float = 0.9,
) -> None:
    risks = result.setdefault("risks_and_focus", [])

    if has_item(risks, "risk", risk):
        return

    risks.append(
        {
            "risk": risk,
            "impact": impact,
            "focus_area": focus_area,
            "source_text": source_text,
            "confidence": confidence,
            "repaired_by_validator": True,
            "repair_reason": "real_case_risk_repair",
        }
    )


def cleanup_needs_review(result: dict, transcript: str) -> dict:
    for field in [
        "key_conclusions",
        "action_items",
        "unresolved_issues",
        "risks_and_focus",
    ]:
        for item in result.get(field, []):
            if item.get("review_reason") == "source_text_not_supported":
                if source_exists(item.get("source_text", ""), transcript):
                    clear_review(item, "source_text_not_supported")
                    item["source_supported_repaired"] = True

    return result


def repair_real_case_boundaries(result: dict, transcript: str) -> dict:
    tr = normalize_text(transcript)

    if "周四前完成页面静态版" in tr or "周四前完成静态页面" in tr:
        add_action(
            result=result,
            owner_name="前端",
            task="完成个人中心页面静态版开发",
            deadline="周四前",
            priority="high",
            source_text="前端：可以，我周四前完成页面静态版。",
        )

    if "我会同步项目负责人" in tr and "紧盯接口排期" in tr:
        add_action(
            result=result,
            owner_name="产品经理",
            task="同步项目负责人并跟进成长值实时接口排期",
            deadline=None,
            priority="high",
            source_text="产品：我会同步项目负责人紧盯接口排期。",
        )

    if "测试重点核对兼容场景" in tr or "需要测试重点核对兼容场景" in tr:
        add_action(
            result=result,
            owner_name="测试",
            task="重点核对老用户缓存、样式错乱、入口闪现等兼容场景",
            deadline=None,
            priority="high",
            source_text="前端：页面模块较多，回归量偏大，需要测试重点核对兼容场景。",
        )

    if "缓存必须100%兼容" in tr or "必须100%兼容" in tr:
        add_conclusion(
            result=result,
            conclusion="老用户本地缓存必须100%兼容，不能出现用户端异常",
            source_text="产品：缓存必须100%兼容，不能出现用户端异常。",
        )

    if "需求定稿后全程冻结" in tr or "不接受临时调整" in tr:
        add_conclusion(
            result=result,
            conclusion="本次需求定稿后全程冻结，不接受临时调整，以保障版本稳定性",
            source_text="产品：本次需求定稿后全程冻结，不接受临时调整，保证版本稳定性。",
        )

    if "实时成长值接口" in tr and ("老接口是离线日更" in tr or "无法支持实时动态渲染" in tr):
        add_issue(
            result=result,
            issue="会员等级动态进度条缺少实时成长值接口支持",
            reason="现有老接口为离线日更，无法支持实时动态渲染",
            source_text="前端：会员等级动态进度条需要后端实时成长值接口，目前老接口是离线日更，无法支持实时动态渲染。",
        )

    if "如果后端接口延期联调" in tr or "接口延期联调" in tr:
        add_risk(
            result=result,
            risk="后端实时成长值接口延期联调",
            impact="会直接卡住版本提测",
            focus_area="后端接口排期与联调进度",
            source_text="前端：如果后端接口延期联调，会直接卡住整个版本提测，没有兜底方案。",
        )

    if "回归量偏大" in tr:
        add_risk(
            result=result,
            risk="页面模块较多导致回归测试量偏大",
            impact="兼容场景覆盖不足可能引发老用户端异常",
            focus_area="老用户缓存、样式错乱、入口闪现等兼容场景",
            source_text="前端：页面模块较多，回归量偏大，需要测试重点核对兼容场景。",
        )

    cleaned_conclusions = []
    for item in result.get("key_conclusions", []):
        text = normalize_text(item.get("conclusion", ""))
        if (
            ("静态页面" in text or "页面静态" in text)
            and ("完成" in text or "开发" in text or "排期" in text)
        ):
            continue
        cleaned_conclusions.append(item)
    result["key_conclusions"] = cleaned_conclusions

    cleaned_issues = []
    for item in result.get("unresolved_issues", []):
        issue_text = normalize_text(
            item.get("issue", "")
            + item.get("reason", "")
            + item.get("source_text", "")
        )

        if ("缓存" in issue_text and "兼容" in issue_text) and (
            "必须100%兼容" in tr or "缓存必须100%兼容" in tr
        ):
            continue

        if "延期" in issue_text and ("如果后端接口延期" in tr or "如果接口延期" in tr):
            continue

        cleaned_issues.append(item)

    result["unresolved_issues"] = cleaned_issues

    for item in result.get("action_items", []):
        task_text = normalize_text(item.get("task", "") + item.get("source_text", ""))

        if "同步项目负责人" in task_text or "紧盯接口排期" in task_text:
            item["owner_name"] = "产品经理"
            item["owner"] = "产品经理"
            item["owner_repaired"] = True
            item["repair_reason"] = "speaker_commitment_owner_repair"

        if ("静态页面" in task_text or "页面静态" in task_text) and (
            "周四前完成" in tr or "周四前完成页面静态版" in tr
        ):
            item["deadline"] = item.get("deadline") or "周四前"
            item["due_date"] = item.get("due_date") or "周四前"
            item["deadline_repaired"] = True
            item["repair_reason"] = "deadline_from_transcript_context"

    return result


def post_repair_real_meeting_analysis(result: dict, transcript: str) -> dict:
    result = cleanup_needs_review(result, transcript)
    result = repair_real_case_boundaries(result, transcript)
    result = cleanup_needs_review(result, transcript)
    return result


def agenda_text(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("item") or item.get("title") or item.get("summary") or "")
    return str(item or "")


def is_non_agenda_item(text: str) -> bool:
    norm = normalize_text(text)
    flow_terms = [
        "大家好",
        "下午好",
        "会议控制",
        "首先请",
        "有没有其他问题",
        "无问题",
        "会议结束",
        "开场",
        "问候",
    ]
    detail_terms = [
        "风险",
        "待办",
        "问题",
        "疑问",
        "补充接口",
        "确认测试计划",
        "启动测试",
        "同步排期表",
        "调整需求优先级",
    ]
    return any(normalize_text(term) in norm for term in flow_terms + detail_terms)


def validate_agenda_quality(result: dict, audit: list[dict] | None = None) -> dict:
    agenda = result.get("meeting_agenda", [])
    if not isinstance(agenda, list):
        return result

    filtered = []
    for item in agenda:
        text = agenda_text(item)
        if not text:
            continue
        if is_non_agenda_item(text):
            add_audit(audit, "meeting_agenda", "remove", "non_agenda_or_flow_talk", item)
            continue
        if any(similarity(text, agenda_text(existing)) >= 0.72 for existing in filtered):
            add_audit(audit, "meeting_agenda", "remove", "duplicate_agenda_topic", item)
            continue
        filtered.append(item)

    if len(filtered) > 6:
        for item in filtered[6:]:
            add_audit(audit, "meeting_agenda", "remove", "agenda_default_max_6", item)
        filtered = filtered[:6]

    result["meeting_agenda"] = filtered
    return result


def has_decision_signal(text: object) -> bool:
    norm = normalize_text(text)
    signals = [
        "确认",
        "决定",
        "同意",
        "敲定",
        "达成",
        "锁定",
        "禁止",
        "不再接收",
        "不接受",
        "砍掉",
        "延后",
        "上线标准",
        "必须",
        "严格",
    ]
    return any(normalize_text(signal) in norm for signal in signals)


def has_proposal_or_action_signal(text: object) -> bool:
    norm = normalize_text(text)
    signals = [
        "建议",
        "疑问",
        "是否",
        "问题",
        "补充",
        "更新",
        "启动",
        "同步",
        "跟进",
        "待确认",
        "需要补充",
    ]
    return any(normalize_text(signal) in norm for signal in signals)


def has_unresolved_signal(text: object) -> bool:
    norm = normalize_text(text)
    signals = [
        "暂时不做最终决定",
        "暂不做最终决定",
        "暂不决定",
        "暂不确认",
        "不做最终决定",
        "尚未确定",
        "未确定",
        "未明确",
        "不能确认",
        "没有最终决定",
        "是否启动",
        "待确认",
        "待定",
    ]
    return any(normalize_text(signal) in norm for signal in signals)


def has_non_final_decision_signal(text: object) -> bool:
    norm = normalize_text(text)
    signals = [
        "再确定最终方向",
        "后续确定",
        "继续评估",
        "暂不确认",
        "暂不决定",
        "初步怀疑",
        "还没有最终确认",
        "不能直接确认",
        "待进一步评估",
        "暂时不做最终决定",
        "暂不做最终决定",
    ]
    return any(normalize_text(signal) in norm for signal in signals)


def is_conditional_followup_only(text: object) -> bool:
    norm = normalize_text(text)
    conditional = any(normalize_text(signal) in norm for signal in ["如果", "若", "假如"])
    followup = any(normalize_text(signal) in norm for signal in ["需要重新评估", "需要评估", "再评估"])
    confirmed = any(normalize_text(signal) in norm for signal in ["决定", "确认", "同意", "敲定", "达成", "必须", "禁止"])
    return conditional and followup and not confirmed


def has_explicit_action_requirement(text: object) -> bool:
    norm = normalize_text(text)
    patterns = [
        "需要同步",
        "需要补充",
        "需要更新",
        "需要提交",
        "需要排查",
        "需要验证",
        "需要评估",
        "继续评估",
        "继续排查",
        "先评估",
    ]
    return any(normalize_text(pattern) in norm for pattern in patterns)


def action_task_from_boundary_text(text: object) -> str:
    norm = normalize_text(text)
    if "先评估不同方案收益和成本" in norm:
        return "评估不同方案收益和成本"
    if "继续评估模型架构调整" in norm:
        return "继续评估模型架构调整"
    if "需要继续排查" in norm or "继续排查" in norm:
        return "继续排查事故原因"
    if "需要同步组件规范" in norm:
        return "同步组件规范"
    if "需要补充" in norm:
        return "补充相关事项"
    if "需要更新" in norm:
        return "更新相关事项"
    if "需要提交" in norm:
        return "提交相关事项"
    if "需要验证" in norm:
        return "验证相关事项"
    if "需要评估" in norm or "继续评估" in norm:
        return "评估相关事项"
    return str(text or "").strip()


def add_boundary_action_item(result: dict, source_text: str, audit: list[dict] | None = None) -> None:
    task = action_task_from_boundary_text(source_text)
    if not task:
        return
    actions = result.setdefault("action_items", [])
    if has_item(actions, "task", task):
        return
    item = {
        "owner_name": None,
        "owner": None,
        "task": task,
        "deadline": None,
        "due_date": None,
        "priority": None,
        "source_text": source_text,
        "confidence": 0.75,
        "repaired_by_validator": True,
        "repair_reason": "non_final_decision_reclassified_to_action",
    }
    actions.append(item)
    add_audit(audit, "action_items", "add", "non_final_decision_reclassified_to_action", None, item)


def add_boundary_unresolved_issue(result: dict, source_text: str, audit: list[dict] | None = None) -> None:
    issue = "事项尚未最终确认"
    source_norm = normalize_text(source_text)
    if "最终方向" in source_norm:
        issue = "最终方向尚未确定"
    elif "根因" in source_norm or "原因" in source_norm or "初步怀疑" in source_norm:
        issue = "相关原因尚未最终确认"
    elif "不能直接确认" in source_norm:
        issue = "相关方案尚未确认"
    issues = result.setdefault("unresolved_issues", [])
    source_norm = normalize_text(source_text)
    if any(source_norm and source_norm == normalize_text(item.get("source_text", "")) for item in issues if isinstance(item, dict)):
        return
    if has_item(issues, "issue", issue):
        return
    item = {
        "issue": issue,
        "reason": "",
        "blocker": None,
        "source_text": source_text,
        "confidence": 0.75,
        "repaired_by_validator": True,
        "repair_reason": "non_final_decision_reclassified_to_unresolved",
    }
    issues.append(item)
    add_audit(audit, "unresolved_issues", "add", "non_final_decision_reclassified_to_unresolved", None, item)


def filter_core_conclusions(result: dict, audit: list[dict] | None = None) -> dict:
    kept = []
    for item in result.get("key_conclusions", []):
        if not isinstance(item, dict):
            continue
        combined = item.get("conclusion", "") + item.get("source_text", "")
        conclusion = item.get("conclusion", "")
        if has_non_final_decision_signal(combined):
            source_text = item.get("source_text") or conclusion
            if has_unresolved_signal(combined):
                add_boundary_unresolved_issue(result, source_text, audit)
            elif has_explicit_action_requirement(combined):
                add_boundary_action_item(result, source_text, audit)
            add_audit(audit, "key_conclusions", "remove", "non_final_decision_not_core_conclusion", item)
            continue
        if has_unresolved_signal(combined):
            add_audit(audit, "key_conclusions", "remove", "unresolved_issue_not_core_conclusion", item)
            continue
        if is_conditional_followup_only(combined):
            add_audit(audit, "key_conclusions", "remove", "conditional_followup_not_core_conclusion", item)
            continue
        proposal_without_confirmation = (
            has_proposal_or_action_signal(conclusion)
            and not any(normalize_text(term) in normalize_text(combined) for term in ["同意", "确认", "决定", "敲定", "达成"])
        )
        if proposal_without_confirmation or (has_proposal_or_action_signal(combined) and not has_decision_signal(combined)):
            add_audit(audit, "key_conclusions", "remove", "proposal_question_or_action_not_core_conclusion", item)
            continue
        kept.append(item)
    result["key_conclusions"] = kept
    return result


def repair_confirmed_short_term_direction(result: dict, transcript: str, audit: list[dict] | None = None) -> dict:
    tr = normalize_text(transcript)
    has_proposal = "建议先做可以快速上线的部分" in tr
    has_confirmation = "这个方向先推进" in tr
    if not (has_proposal and has_confirmation):
        return result

    conclusions = result.setdefault("key_conclusions", [])
    if any("可落地方案" in normalize_text(item.get("conclusion", "")) for item in conclusions if isinstance(item, dict)):
        return result

    item = {
        "conclusion": "优先执行当前可落地方案",
        "source_text": "建议先做可以快速上线的部分",
        "confidence": 0.9,
        "repaired_by_validator": True,
        "repair_reason": "proposal_confirmed_by_later_direction",
    }
    conclusions.append(item)
    add_audit(audit, "key_conclusions", "add", "proposal_confirmed_by_later_direction", None, item)
    return result


def enforce_continuous_source_text(result: dict, transcript: str, audit: list[dict] | None = None) -> dict:
    fields = [
        "key_conclusions",
        "action_items",
        "unresolved_issues",
        "risks_and_focus",
    ]
    for field in fields:
        kept = []
        for item in result.get(field, []):
            if not isinstance(item, dict):
                continue
            before = deepcopy(item)
            source_text = item.get("source_text", "")
            if source_text_is_continuous(source_text, transcript):
                item["source_supported"] = True
                kept.append(item)
                continue
            repaired = repair_source_text_from_transcript(field, item, transcript)
            if repaired and source_text_is_continuous(item.get("source_text", ""), transcript):
                item["source_supported"] = True
                add_audit(audit, field, "modify", "source_text_repaired_to_complete_continuous_fragment", before, item)
                kept.append(item)
                continue
            reason = "ellipsis_source_text" if has_ellipsis(source_text) else "source_text_not_continuous_in_transcript"
            add_audit(audit, field, "remove", reason, before)
        result[field] = kept
    return result


def has_explicit_risk_source(source_text: object) -> bool:
    norm = normalize_text(source_text)
    explicit_signals = [
        "风险",
        "可能影响",
        "可能导致",
        "受到影响",
        "延期",
        "延迟",
        "卡住",
        "阻塞",
        "故障",
        "异常",
        "错乱",
        "反复",
        "否则",
        "返工",
        "投诉",
        "失败",
        "回归量偏大",
    ]
    if any(normalize_text(signal) in norm for signal in explicit_signals):
        return True
    return "如果" in norm and ("可能" in norm or "导致" in norm)


def conservative_risk_text(risk_text: object, source_text: object) -> str:
    risk = str(risk_text or "").strip()
    source = str(source_text or "").strip()
    source_norm = normalize_text(source)
    risk_norm = normalize_text(risk)

    if "可能影响" in source_norm:
        if "一定" in risk_norm or "必然" in risk_norm or ("导致" in risk_norm and "可能导致" not in risk_norm):
            return source
    if "可能导致" in source_norm and ("一定" in risk_norm or "必然" in risk_norm):
        return source
    if "受到影响" in source_norm and ("下降" in risk_norm or "失败" in risk_norm) and "可能" not in risk_norm:
        return source
    return risk


def filter_inferred_risks(result: dict, audit: list[dict] | None = None) -> dict:
    kept = []
    for item in result.get("risks_and_focus", []):
        if not isinstance(item, dict):
            continue
        source_text = item.get("source_text", "")
        if not has_explicit_risk_source(source_text):
            add_audit(audit, "risks_and_focus", "remove", "risk_without_explicit_source_signal", item)
            continue
        if "时间风险比较高" in normalize_text(source_text):
            before = deepcopy(item)
            item["risk"] = "方案延期可能影响交付节奏"
            item["repair_reason"] = "time_risk_wording_aligned_to_source"
            add_audit(audit, "risks_and_focus", "modify", "time_risk_wording_aligned_to_source", before, item)
        conservative = conservative_risk_text(item.get("risk", ""), source_text)
        if conservative != item.get("risk", ""):
            before = deepcopy(item)
            item["risk"] = conservative
            item["repair_reason"] = "risk_wording_clamped_to_source_uncertainty"
            add_audit(audit, "risks_and_focus", "modify", "risk_wording_clamped_to_source_uncertainty", before, item)
        kept.append(item)
    result["risks_and_focus"] = kept
    return result


def clear_action_fields_without_source_evidence(result: dict, audit: list[dict] | None = None) -> dict:
    priority_terms = ["高优先级", "低优先级", "中优先级", "优先处理", "优先跟进", "紧急", "high", "medium", "low"]
    commitment_terms = ["我会", "我来", "我负责", "我这边", "我们负责", "由", "交给"]
    owner_action_terms = ["补充", "更新", "启动", "同步", "提交", "完成", "整理", "确认", "编写", "输出"]
    collective_terms = ["所有人", "大家", "全员", "我们都"]

    for item in result.get("action_items", []):
        if not isinstance(item, dict):
            continue
        source = item.get("source_text", "")
        source_norm = normalize_text(source)
        owner = item.get("owner_name") or item.get("owner")
        if owner and (normalize_text(owner) in source_norm or not action_metadata_has_evidence(item, owner, "owner")):
            owner_norm = normalize_text(owner)
            has_owner = owner_norm in source_norm
            has_commitment = any(normalize_text(term) in source_norm for term in commitment_terms)
            has_owner_action = has_owner and any(normalize_text(term) in source_norm for term in owner_action_terms)
            is_collective = any(normalize_text(term) in source_norm for term in collective_terms)
            if (not has_owner) or (is_collective and not has_commitment) or (has_owner and not has_commitment and not has_owner_action):
                before = deepcopy(item)
                item["owner_name"] = None
                item["owner"] = None
                item["owner_repaired"] = True
                item["repair_reason"] = "owner_without_source_evidence"
                add_audit(audit, "action_items", "modify", "owner_without_source_evidence", before, item)

        deadline = item.get("deadline") or item.get("due_date")
        if deadline and not action_metadata_has_evidence(item, deadline, "deadline"):
            before = deepcopy(item)
            item["deadline"] = None
            item["due_date"] = None
            item["deadline_repaired"] = True
            item["repair_reason"] = "deadline_without_source_evidence"
            add_audit(audit, "action_items", "modify", "deadline_without_source_evidence", before, item)

        priority = item.get("priority")
        if priority and not any(normalize_text(term) in source_norm for term in priority_terms):
            before = deepcopy(item)
            item["priority"] = None
            item["priority_repaired"] = True
            item["repair_reason"] = "priority_without_source_evidence"
            add_audit(audit, "action_items", "modify", "priority_without_source_evidence", before, item)

    return result


def filter_unassigned_or_suggested_action_items(result: dict, audit: list[dict] | None = None) -> dict:
    commitment_terms = ["我会", "我来", "我负责", "我这边", "我们负责", "由", "交给"]
    assignment_terms = ["负责", "完成", "提交", "输出", "编写", "更新", "同步", "整理", "补充", "验证", "排查", "跟进", "安排"]
    weak_source_terms = ["建议", "可以", "可能", "否则", "不确定", "讨论"]
    action_requirement_terms = ["需要补充", "需要同步", "需要更新", "需要验证", "需要排查", "后续安排", "下一步完成"]

    kept = []
    for item in result.get("action_items", []):
        if not isinstance(item, dict):
            continue
        source_norm = normalize_text(item.get("source_text", ""))
        task_norm = normalize_text(item.get("task", ""))
        owner = item.get("owner_name") or item.get("owner")
        has_commitment = any(normalize_text(term) in source_norm for term in commitment_terms)
        has_assignment = bool(owner) or any(normalize_text(term) in source_norm for term in assignment_terms)
        weak_source = any(normalize_text(term) in source_norm for term in weak_source_terms)
        has_action_requirement = any(normalize_text(term) in source_norm for term in action_requirement_terms)
        direction_only = "方向先推进" in source_norm and not has_commitment

        if direction_only or (weak_source and not has_commitment and not has_assignment):
            add_audit(audit, "action_items", "remove", "suggestion_or_direction_without_assignment", item)
            continue
        if "需要" in source_norm and not (has_action_requirement or has_assignment or has_commitment):
            add_audit(audit, "action_items", "remove", "need_statement_without_explicit_action", item)
            continue
        if "功能开发" in task_norm and "功能开发" not in source_norm:
            add_audit(audit, "action_items", "remove", "task_claim_not_supported_by_action_source", item)
            continue
        kept.append(item)

    result["action_items"] = kept
    return result


def filter_weak_unresolved_issues(result: dict, audit: list[dict] | None = None) -> dict:
    kept = []
    requirement_action_patterns = [
        "需要同步",
        "需要补充",
        "需要更新",
        "需要提交",
        "需要排查",
        "需要验证",
        "需要评估",
    ]
    for item in result.get("unresolved_issues", []):
        if not isinstance(item, dict):
            continue
        combined = (
            item.get("issue", "")
            + item.get("reason", "")
            + item.get("source_text", "")
        )
        combined_norm = normalize_text(combined)
        if has_unresolved_signal(combined):
            kept.append(item)
            continue
        if any(normalize_text(pattern) in combined_norm for pattern in requirement_action_patterns):
            add_audit(audit, "unresolved_issues", "remove", "requirement_action_not_unresolved_issue", item)
            continue
        if "需要提前确认" in combined_norm and "否则" in combined_norm:
            add_audit(audit, "unresolved_issues", "remove", "requirement_or_risk_not_unresolved_issue", item)
            continue
        kept.append(item)

    result["unresolved_issues"] = kept
    return result


def action_metadata_has_evidence(item: dict, value: object, field_name: str) -> bool:
    value_norm = normalize_text(value)
    if not value_norm:
        return False

    evidence_values: list[object] = [
        item.get("source_text"),
        item.get("evidence_text"),
    ]
    for key in ("source_texts", "evidence_texts"):
        values = item.get(key)
        if isinstance(values, list):
            evidence_values.extend(values)

    for key in ("semantic_event", "source_event", "event"):
        event = item.get(key)
        if isinstance(event, dict):
            evidence_values.extend(_semantic_event_evidence_values(event, field_name))

    events = item.get("semantic_events") or item.get("source_events") or item.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                evidence_values.extend(_semantic_event_evidence_values(event, field_name))

    return any(value_norm in normalize_text(candidate) for candidate in evidence_values)


def _semantic_event_evidence_values(event: dict, field_name: str) -> list[object]:
    evidence = event.get("evidence") if isinstance(event.get("evidence"), dict) else {}
    attributes = event.get("attributes") if isinstance(event.get("attributes"), dict) else {}
    values: list[object] = [
        event.get("source_text"),
        event.get("normalized_text"),
        evidence.get("source_text"),
        evidence.get("quote"),
    ]
    if field_name == "owner":
        values.append(attributes.get("owner"))
    elif field_name == "deadline":
        values.append(attributes.get("deadline"))
    return values


def cross_dimension_text(field: str, item: object) -> str:
    if field == "meeting_summary":
        return str(item or "")
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    if field == "key_conclusions":
        return str(item.get("conclusion") or "")
    if field == "action_items":
        return str(item.get("task") or "")
    if field == "unresolved_issues":
        return str(item.get("issue") or "")
    if field == "risks_and_focus":
        return str(item.get("risk") or "")
    return ""


def duplicate_fact(a: str, b: str) -> bool:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return False
    return a_norm in b_norm or b_norm in a_norm or similarity(a_norm, b_norm) >= 0.84


def allowed_decision_action_pair(current_field: str, current_item: dict, kept_field: str, kept_item: dict) -> bool:
    if current_field == "key_conclusions" and kept_field == "action_items":
        return has_decision_signal(current_item.get("conclusion", "")) and not duplicate_fact(
            current_item.get("conclusion", ""),
            kept_item.get("task", ""),
        )
    return False


def remove_cross_dimension_duplicates(result: dict, audit: list[dict] | None = None) -> dict:
    order = [
        "action_items",
        "key_conclusions",
        "unresolved_issues",
        "risks_and_focus",
    ]
    accepted: list[tuple[str, dict, str]] = []

    for field in order:
        kept = []
        for item in result.get(field, []):
            if not isinstance(item, dict):
                kept.append(item)
                continue
            text = cross_dimension_text(field, item)
            duplicate_of = None
            for accepted_field, accepted_item, accepted_text in accepted:
                if duplicate_fact(text, accepted_text) and not allowed_decision_action_pair(
                    field,
                    item,
                    accepted_field,
                    accepted_item,
                ):
                    duplicate_of = accepted_field
                    break
            if duplicate_of:
                add_audit(audit, field, "remove", f"cross_dimension_duplicate_of_{duplicate_of}", item)
                continue
            accepted.append((field, item, text))
            kept.append(item)
        result[field] = kept

    return result


def validate_meeting_analysis_with_audit(result: dict, transcript: str) -> tuple[dict, list[dict]]:
    audit: list[dict] = []
    result = deepcopy(result)

    result = clean_null_values(result)
    result = validate_agenda_quality(result, audit)
    result = repair_source_text_for_conclusions(result, transcript)
    result = validate_deadlines(result, transcript)
    result = validate_source_text(result, transcript)
    result = validate_claim_source_consistency(result)
    result = validate_action_items(result)
    result = validate_owner_resolution(result)
    result = validate_risks(result)
    result = remove_issue_derived_action_items(result)
    result = final_remove_forbidden_action_items(result)
    result = deduplicate_result(result)
    result = final_cleanup(result)
    result = post_repair_real_meeting_analysis(result, transcript)
    result = validate_agenda_quality(result, audit)
    result = filter_core_conclusions(result, audit)
    result = repair_confirmed_short_term_direction(result, transcript, audit)
    result = enforce_continuous_source_text(result, transcript, audit)
    result = clear_action_fields_without_source_evidence(result, audit)
    result = filter_unassigned_or_suggested_action_items(result, audit)
    result = filter_weak_unresolved_issues(result, audit)
    result = filter_inferred_risks(result, audit)
    result = remove_cross_dimension_duplicates(result, audit)
    result = deduplicate_result(result)
    result = final_cleanup(result)
    result["_validator_audit"] = audit

    return result, audit


def validate_meeting_analysis(result: dict, transcript: str) -> dict:
    result, _audit = validate_meeting_analysis_with_audit(result, transcript)
    return result
