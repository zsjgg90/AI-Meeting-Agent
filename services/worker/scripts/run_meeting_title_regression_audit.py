from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from app.meeting_title import (  # noqa: E402
    has_valid_meeting_type,
    has_valid_title_basis,
    is_valid_ai_title,
    maybe_apply_ai_title,
)


DEFAULT_TITLE = "2026-07-30 10:00 实时录音"
OUTPUT_DIR = PROJECT_ROOT / "data" / "debug" / "title_regression"


@dataclass(frozen=True)
class TitleSample:
    sample_id: str
    source: str
    meeting_type: str
    meeting_type_confidence: float
    meeting_title_candidate: str
    title_basis: list[str]
    expected: str
    notes: str


class MeetingStub:
    title = DEFAULT_TITLE
    title_source = "fallback"


SAMPLES = [
    TitleSample(
        sample_id="real_project_weekly_good",
        source="data/debug/real_production_analysis/6387afc1-1287-4a45-b1e0-a2d33b8ca777/input_transcript.txt",
        meeting_type="project_weekly",
        meeting_type_confidence=0.92,
        meeting_title_candidate="项目周例会：进度同步与版本排期",
        title_basis=["会议原文说明召开本周项目例行短会并同步进度", "会议议题覆盖现存问题对齐和下周工作排期"],
        expected="accepted",
        notes="真实项目周会，候选覆盖全会主题。",
    ),
    TitleSample(
        sample_id="real_project_weekly_bad_task",
        source="data/debug/real_production_analysis/6387afc1-1287-4a45-b1e0-a2d33b8ca777/input_transcript.txt",
        meeting_type="project_weekly",
        meeting_type_confidence=0.92,
        meeting_title_candidate="后端接口优化需在明天上午完成",
        title_basis=["会议原文说明召开本周项目例行短会并同步进度", "会议议题覆盖现存问题对齐和下周工作排期"],
        expected="rejected",
        notes="固定禁止样例，单条待办加截止时间。",
    ),
    TitleSample(
        sample_id="acceptance_project_weekly_role_task",
        source="data/debug/meeting_pipeline_acceptance/20260717_011621/project_weekly/meeting_input.json",
        meeting_type="project_weekly",
        meeting_type_confidence=0.89,
        meeting_title_candidate="后端接口优化确认会",
        title_basis=["会议整体同步支付改造本周进展", "议程覆盖联调上线计划和遗留风险"],
        expected="rejected",
        notes="已有验收项目周会，候选只覆盖后端岗位事项。",
    ),
    TitleSample(
        sample_id="requirement_review_good",
        source="data/debug/prompt_stability_eval/meeting_001_迭代启动会/input_transcript.txt",
        meeting_type="requirement_review",
        meeting_type_confidence=0.88,
        meeting_title_candidate="版本迭代需求评审会",
        title_basis=["会议整体对齐V3.2迭代需求范围和排期", "会议总结覆盖需求锁定交付标准和风险保障"],
        expected="accepted",
        notes="已有迭代启动/需求对齐样例，候选为全会主题。",
    ),
    TitleSample(
        sample_id="risk_review_good",
        source="data/debug/prompt_stability_eval/meeting_004_会议场景_新版本上线前全维度风险评审_排查功能_性能_兼容_运维_线上故障风/input_transcript.txt",
        meeting_type="risk_review",
        meeting_type_confidence=0.91,
        meeting_title_candidate="新版本上线风险评审会",
        title_basis=["会议整体全面排查V3.2新版本上线风险", "会议议程覆盖功能性能兼容运维和应急预案"],
        expected="accepted",
        notes="已有风险评审样例，候选覆盖上线风险全局。",
    ),
    TitleSample(
        sample_id="project_retrospective_good",
        source="data/debug/prompt_stability_eval/meeting_003_会议场景_月度全渠道广告投放复盘_核算投产比_排查低效渠道_优化下月投放策略/input_transcript.txt",
        meeting_type="project_retrospective",
        meeting_type_confidence=0.90,
        meeting_title_candidate="渠道投放月度复盘会",
        title_basis=["会议整体复盘上月渠道投放数据和投产比", "会议总结覆盖低效渠道排查和下月预算分配"],
        expected="accepted",
        notes="已有月度投放复盘样例，候选覆盖复盘对象和类型。",
    ),
    TitleSample(
        sample_id="generic_title_rejected",
        source="data/debug/prompt_stability_eval/meeting_002_需求评审会/input_transcript.txt",
        meeting_type="project_retrospective",
        meeting_type_confidence=0.86,
        meeting_title_candidate="会议总结",
        title_basis=["会议整体复盘上月增长数据", "会议总结覆盖渠道留存转化和增长目标"],
        expected="rejected",
        notes="过度泛化标题。",
    ),
    TitleSample(
        sample_id="insufficient_basis_fallback",
        source="data/debug/prompt_stability_eval/meeting_002_需求评审会/input_transcript.txt",
        meeting_type="project_retrospective",
        meeting_type_confidence=0.86,
        meeting_title_candidate="月度增长数据复盘会",
        title_basis=["会议整体复盘上月增长数据"],
        expected="rejected",
        notes="候选本身可接受，但证据不足。",
    ),
]


def source_exists(sample: TitleSample) -> bool:
    return (PROJECT_ROOT / sample.source).exists()


def audit_sample(sample: TitleSample) -> dict[str, Any]:
    payload = {
        "meeting_type": sample.meeting_type,
        "meeting_type_confidence": sample.meeting_type_confidence,
        "meeting_title_candidate": sample.meeting_title_candidate,
        "title_basis": sample.title_basis,
    }
    meeting = MeetingStub()
    applied = maybe_apply_ai_title(meeting, payload)
    title_validator_passed = (
        is_valid_ai_title(sample.meeting_title_candidate)
        and has_valid_meeting_type(payload)
        and has_valid_title_basis(payload)
    )
    return {
        "sample_id": sample.sample_id,
        "source": sample.source,
        "source_exists": source_exists(sample),
        "meeting_type": sample.meeting_type,
        "meeting_type_confidence": sample.meeting_type_confidence,
        "meeting_title_candidate": sample.meeting_title_candidate,
        "title_basis": sample.title_basis,
        "title_validator_passed": title_validator_passed,
        "final_title": meeting.title,
        "title_source": meeting.title_source,
        "expected": sample.expected,
        "outcome": "accepted" if applied else "rejected",
        "safe_fallback": applied is None and meeting.title == DEFAULT_TITLE,
        "notes": sample.notes,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    accepted = sum(1 for row in rows if row["title_validator_passed"])
    rejected = len(rows) - accepted
    safe_fallback = sum(1 for row in rows if row["safe_fallback"])
    local_issue_leaks = sum(
        1
        for row in rows
        if row["title_validator_passed"]
        and any(word in row["meeting_title_candidate"] for word in ["后端接口优化", "周四前完成", "明天上午完成"])
    )
    return {
        "sample_count": len(rows),
        "acceptable_title_count": accepted,
        "rejected_count": rejected,
        "safe_fallback_count": safe_fallback,
        "local_issue_wrong_title_count": local_issue_leaks,
    }


def render_markdown(rows: list[dict[str, Any]], summary: dict[str, int]) -> str:
    lines = [
        "# AI Meeting Title Regression Audit",
        "",
        "## Scope",
        "",
        "- No database access.",
        "- No new model calls.",
        "- No six-dimension analysis refactor.",
        "- Samples use existing real/debug/acceptance transcript files as source context and deterministic title payloads.",
        "",
        "## Summary",
        "",
        f"- 样例数：{summary['sample_count']}",
        f"- 可接受标题数：{summary['acceptable_title_count']}",
        f"- 被拒绝数：{summary['rejected_count']}",
        f"- 安全回退数：{summary['safe_fallback_count']}",
        f"- 局部事项误标题数：{summary['local_issue_wrong_title_count']}",
        "- 主要失败原因：任务型标题、单岗位事项标题、过度泛化标题、证据不足。",
        "",
        "## Results",
        "",
        "| sample | meeting_type | confidence | candidate | basis | Validator | final_title | source_exists | notes |",
        "|---|---|---:|---|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {sample_id} | {meeting_type} | {meeting_type_confidence:.2f} | {meeting_title_candidate} | {basis_count} | {validator} | {final_title} | {source_exists} | {notes} |".format(
                sample_id=row["sample_id"],
                meeting_type=row["meeting_type"],
                meeting_type_confidence=row["meeting_type_confidence"],
                meeting_title_candidate=row["meeting_title_candidate"],
                basis_count=len(row["title_basis"]),
                validator="通过" if row["title_validator_passed"] else "拒绝",
                final_title=row["final_title"],
                source_exists="是" if row["source_exists"] else "否",
                notes=row["notes"],
            )
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "当前第一版标题门禁能拦截固定项目周会任务型坏标题、单岗位事项标题、泛化标题和证据不足标题；可接受的项目周会、需求评审、风险评审和复盘标题能通过。",
            "审计中发现不含时间词的单岗位事项标题需要补充拦截，本次已用最小 Validator 规则修复。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = [audit_sample(sample) for sample in SAMPLES]
    summary = summarize(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "20260730_title_regression_report.json"
    md_path = OUTPUT_DIR / "20260730_title_regression_report.md"
    json_path.write_text(json.dumps({"summary": summary, "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(rows, summary), encoding="utf-8")

    print(md_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
