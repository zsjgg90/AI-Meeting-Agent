import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor
from app.meeting_analysis_schema import (
    KeyConclusion,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAnalysisSchema,
    RiskAndFocus,
    UnresolvedIssue,
)


TRANSCRIPT = "\n".join(
    [
        "主持人：今天讨论需求范围、工作量、问题风险和后续安排。",
        "产品：我建议把报表导出放到下期。",
        "负责人：我同意这个建议，报表导出放到下期，本期只做数据看板。",
        "后端：接口回调超时没有明确容错方案。",
        "产品：我会后补充异常场景，今天内更新文档。",
        "测试：如果容错方案不明确，可能影响回归测试范围。",
        "负责人：登录问题已经解决，没有问题。",
        "产品：张三周五前提交验收方案。",
    ]
)


def base_analysis(**kwargs) -> MeetingAnalysisSchema:
    data = {
        "meeting_agenda": [],
        "meeting_summary": "会议讨论需求范围和后续安排。",
        "key_conclusions": [],
        "action_items": [],
        "unresolved_issues": [],
        "risks_and_focus": [],
    }
    data.update(kwargs)
    return MeetingAnalysisSchema(**data)


class MeetingAnalysisPostProcessorTest(unittest.TestCase):
    def test_agenda_merge_and_limit(self) -> None:
        analysis = base_analysis(
            meeting_agenda=[
                MeetingAgendaItem(item="大家好会议开始", order=1),
                MeetingAgendaItem(item="需求范围讨论", order=2),
                MeetingAgendaItem(item="需求范围讨论", order=3),
                MeetingAgendaItem(item="工作量评估", order=4),
                MeetingAgendaItem(item="问题风险讨论", order=5),
                MeetingAgendaItem(item="后续安排", order=6),
                MeetingAgendaItem(item="上线范围", order=7),
                MeetingAgendaItem(item="测试计划", order=8),
                MeetingAgendaItem(item="发布准备", order=9),
                MeetingAgendaItem(item="复盘安排", order=10),
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, TRANSCRIPT)

        self.assertLessEqual(len(result.meeting_agenda), 6)
        self.assertNotIn("大家好会议开始", [item.item for item in result.meeting_agenda])
        self.assertEqual([item.order for item in result.meeting_agenda], list(range(1, len(result.meeting_agenda) + 1)))

    def test_proposal_removed_and_confirmed_decision_kept(self) -> None:
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(conclusion="报表导出建议放到下期", source_text="我建议把报表导出放到下期。"),
                KeyConclusion(
                    conclusion="报表导出放到下期，本期只做数据看板",
                    source_text="我同意这个建议，报表导出放到下期，本期只做数据看板。",
                ),
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, TRANSCRIPT)

        self.assertEqual(len(result.key_conclusions), 1)
        self.assertEqual(result.key_conclusions[0].conclusion, "报表导出放到下期，本期只做数据看板")

    def test_action_dedupe_and_metadata_cleanup(self) -> None:
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="李四",
                    task="补充异常场景并更新文档",
                    deadline="明天",
                    priority="high",
                    source_text="我会后补充异常场景，今天内更新文档。",
                ),
                MeetingActionItem(
                    owner_name="张三",
                    task="提交验收方案",
                    deadline="周五前",
                    priority="medium",
                    source_text="张三周五前提交验收方案。",
                ),
                MeetingActionItem(
                    owner_name="张三",
                    task="提交验收方案",
                    deadline="周五前",
                    priority="medium",
                    source_text="张三周五前提交验收方案。",
                ),
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, TRANSCRIPT)

        tasks = [item.task for item in result.action_items]
        self.assertEqual(tasks.count("提交验收方案"), 1)
        cleanup_item = next(item for item in result.action_items if item.task == "补充异常场景并更新文档")
        self.assertIsNone(cleanup_item.owner_name)
        self.assertIsNone(cleanup_item.deadline)
        self.assertEqual(cleanup_item.priority, "medium")

    def test_resolved_issue_removed_and_risk_without_evidence_filtered(self) -> None:
        analysis = base_analysis(
            unresolved_issues=[
                UnresolvedIssue(issue="登录问题仍未解决", source_text="登录问题已经解决，没有问题。"),
                UnresolvedIssue(issue="接口回调超时容错方案仍未明确", source_text="接口回调超时没有明确容错方案。"),
            ],
            risks_and_focus=[
                RiskAndFocus(risk="完成同步", source_text="张三周五前提交验收方案。"),
                RiskAndFocus(risk="容错方案不明确可能影响回归测试范围", source_text="如果容错方案不明确，可能影响回归测试范围。"),
            ],
        )

        result = MeetingAnalysisPostProcessor().process(analysis, TRANSCRIPT)

        self.assertEqual([item.issue for item in result.unresolved_issues], ["接口回调超时容错方案仍未明确"])
        self.assertEqual([item.risk for item in result.risks_and_focus], ["容错方案不明确可能影响回归测试范围"])

    def test_stable_sort_and_idempotence(self) -> None:
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(task="提交验收方案", deadline="周五前", source_text="张三周五前提交验收方案。"),
                MeetingActionItem(task="补充异常场景并更新文档", source_text="我会后补充异常场景，今天内更新文档。"),
            ]
        )
        processor = MeetingAnalysisPostProcessor()

        first = processor.process(analysis, TRANSCRIPT)
        second = processor.process(first, TRANSCRIPT)

        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual([item.task for item in first.action_items], ["提交验收方案", "补充异常场景并更新文档"])


if __name__ == "__main__":
    unittest.main()
