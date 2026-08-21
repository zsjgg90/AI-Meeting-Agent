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

    def test_summary_context_negative_decision_kept(self) -> None:
        transcript = "\n".join(
            [
                "项目经理：我最后把结论过一下。大家如果我说错了直接打断。",
                "项目经理：第四，V2.5 不增加完整记忆能力。",
                "产品经理：确认。",
            ]
        )
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="V2.5版本不包含完整记忆功能",
                    source_text="项目经理：第四，V2.5 不增加完整记忆能力。",
                )
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, transcript)

        self.assertEqual([item.conclusion for item in result.key_conclusions], ["V2.5版本不包含完整记忆功能"])

    def test_scope_version_decisions_without_traditional_marker_kept(self) -> None:
        transcript = "\n".join(
            [
                "项目经理：V2.5范围冻结，新需求放V2.6。",
                "产品：飞书邮箱短信这版不上实际能力。",
                "架构：完整Agent Memory这版不做。",
            ]
        )
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="V2.5范围冻结，新需求放V2.6",
                    source_text="项目经理：V2.5范围冻结，新需求放V2.6。",
                ),
                KeyConclusion(
                    conclusion="飞书邮箱短信这版不上实际能力",
                    source_text="产品：飞书邮箱短信这版不上实际能力。",
                ),
                KeyConclusion(
                    conclusion="完整Agent Memory这版不做",
                    source_text="架构：完整Agent Memory这版不做。",
                ),
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, transcript)

        self.assertEqual(
            [item.conclusion for item in result.key_conclusions],
            [
                "V2.5范围冻结，新需求放V2.6",
                "飞书邮箱短信这版不上实际能力",
                "完整Agent Memory这版不做",
            ],
        )

    def test_scope_version_false_positives_removed(self) -> None:
        transcript = "\n".join(
            [
                "产品：建议放V2.6。",
                "产品：是否放V2.6？",
                "研发：如果来不及可能不上。",
                "测试：必须修。",
                "项目经理：后续再确认。",
            ]
        )
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(conclusion="建议放V2.6", source_text="产品：建议放V2.6。"),
                KeyConclusion(conclusion="是否放V2.6", source_text="产品：是否放V2.6？"),
                KeyConclusion(conclusion="如果来不及可能不上", source_text="研发：如果来不及可能不上。"),
                KeyConclusion(conclusion="必须修", source_text="测试：必须修。"),
                KeyConclusion(conclusion="后续再确认", source_text="项目经理：后续再确认。"),
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.key_conclusions, [])
        self.assertTrue(
            all(
                event["reason"] in {"not_confirmed_decision", "invalid_or_ellipsized_source_text"}
                for event in processor.last_audit
            )
        )

    def test_defer_decisions_kept_without_promoting_proposals_or_actions(self) -> None:
        transcript = "\n".join(
            [
                "张伟：这个优先级先确定一下。 稳定性问题最高。 标题那些优化先放一下。 先把六维输出稳定。",
                "张伟：还有一个性能优化先不要急。 等版本稳定以后再看。",
                "产品：建议下个版本再看看。",
                "研发：性能优化是不是这版必须改？",
                "王强：下午安排录音流程测试。",
            ]
        )
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="标题优化先放，先把六维输出稳定",
                    source_text="张伟：这个优先级先确定一下。 稳定性问题最高。 标题那些优化先放一下。 先把六维输出稳定。",
                ),
                KeyConclusion(
                    conclusion="性能优化等版本稳定以后再看",
                    source_text="张伟：还有一个性能优化先不要急。 等版本稳定以后再看。",
                ),
                KeyConclusion(
                    conclusion="建议下个版本再看看",
                    source_text="产品：建议下个版本再看看。",
                ),
                KeyConclusion(
                    conclusion="性能优化这版必须改",
                    source_text="研发：性能优化是不是这版必须改？",
                ),
                KeyConclusion(
                    conclusion="下午安排录音流程测试",
                    source_text="王强：下午安排录音流程测试。",
                ),
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, transcript)

        self.assertEqual(
            [item.conclusion for item in result.key_conclusions],
            [
                "标题优化先放，先把六维输出稳定",
                "性能优化等版本稳定以后再看",
            ],
        )

    def test_recording_test_action_rewrite_uses_continuous_source(self) -> None:
        transcript = "\n".join(
            [
                "王强：录音页面现在基本完成。",
                "张伟：王强，下午安排录音流程测试。",
            ]
        )
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    task="王强：安排前端录音流程的压测（责任人：王强）",
                    source_text="王强：安排前端录音流程的压测（责任人：王强）",
                ),
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(len(result.action_items), 1)
        self.assertEqual(result.action_items[0].source_text, "张伟：王强，下午安排录音流程测试。")
        self.assertIn("安排前端录音流程", result.action_items[0].task)
        self.assertTrue(
            any(
                event["reason"] == "recording_test_source_repaired_from_transcript"
                for event in processor.last_audit
            )
        )

    def test_recording_arrangement_proposal_is_not_promoted_to_action(self) -> None:
        transcript = "产品：建议下午安排录音流程测试。"
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    task="建议下午安排录音流程测试",
                    source_text="产品：建议下午安排录音流程测试。",
                )
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, transcript)

        self.assertEqual(result.action_items, [])

    def test_payment_date_claim_without_confirmation_removed(self) -> None:
        transcript = "\n".join(
            [
                "项目经理：然后风险就是，如果支付继续延期，会压缩测试时间，可能影响上线。",
                "后端：第三方如果一直不回，不是后端单方面能解决的。",
            ]
        )
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="支付功能上线时间冻结至10月15日",
                    source_text="项目经理：然后风险就是，如果支付继续延期，会压缩测试时间，可能影响上线。",
                )
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.key_conclusions, [])
        self.assertEqual(processor.last_audit[-1]["reason"], "not_confirmed_decision")

    def test_unsupported_rehearsal_date_claim_removed(self) -> None:
        transcript = "项目经理：然后彩排最终时间周四下午四点。"
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="测试彩排时间确定为10月10日",
                    source_text="项目经理：然后彩排最终时间周四下午四点。",
                )
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.key_conclusions, [])
        self.assertEqual(processor.last_audit[-1]["reason"], "not_confirmed_decision")

    def test_device_adaptation_suggestion_not_promoted_to_decision(self) -> None:
        transcript = "\n".join(
            [
                "项目经理：还有设备适配。",
                "测试：那这不是当前待办里的明确设备型号，测试自己选一个常见尺寸就行。",
            ]
        )
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="设备适配优先级明确",
                    source_text="测试：那这不是当前待办里的明确设备型号，测试自己选一个常见尺寸就行。",
                )
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.key_conclusions, [])
        self.assertEqual(processor.last_audit[-1]["reason"], "not_confirmed_decision")

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

    def test_meeting_control_question_removed_from_unresolved(self) -> None:
        transcript = "主持人：还有遗漏吗？"
        analysis = base_analysis(
            unresolved_issues=[
                UnresolvedIssue(issue="还有遗漏吗", source_text="主持人：还有遗漏吗？"),
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.unresolved_issues, [])
        self.assertEqual(processor.last_audit[-1]["reason"], "meeting_control_question")

    def test_issue_resolved_by_followup_removed_from_unresolved(self) -> None:
        transcript = "\n".join(
            [
                "产品：小屏适配具体哪台？",
                "测试：测试自己选一个常见尺寸就行。",
            ]
        )
        analysis = base_analysis(
            unresolved_issues=[
                UnresolvedIssue(issue="小屏适配具体型号未确认", source_text="产品：小屏适配具体哪台？"),
            ]
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.unresolved_issues, [])
        self.assertEqual(processor.last_audit[-1]["reason"], "resolved_by_followup")

    def test_action_like_issue_removed_without_affecting_action_or_risk(self) -> None:
        transcript = "项目经理：AI分析失败，需要后端明天下午修复。"
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="后端",
                    task="修复AI分析失败",
                    deadline="明天下午",
                    source_text="项目经理：AI分析失败，需要后端明天下午修复。",
                )
            ],
            unresolved_issues=[
                UnresolvedIssue(
                    issue="AI分析失败需要修复",
                    source_text="项目经理：AI分析失败，需要后端明天下午修复。",
                ),
            ],
            risks_and_focus=[
                RiskAndFocus(
                    risk="AI分析失败风险",
                    source_text="项目经理：AI分析失败，需要后端明天下午修复。",
                )
            ],
        )

        processor = MeetingAnalysisPostProcessor()
        result = processor.process(analysis, transcript)

        self.assertEqual(result.unresolved_issues, [])
        self.assertEqual([item.task for item in result.action_items], ["修复AI分析失败"])
        self.assertEqual([item.risk for item in result.risks_and_focus], ["AI分析失败风险"])
        self.assertIn(
            {"field": "unresolved_issues", "action": "remove", "reason": "action_like_issue"},
            [{key: event[key] for key in ("field", "action", "reason")} for event in processor.last_audit],
        )

    def test_currently_unconfirmed_business_issue_is_kept(self) -> None:
        transcript = "技术：支付回调签名验证为什么失败，目前还没有确认原因。"
        analysis = base_analysis(
            unresolved_issues=[
                UnresolvedIssue(
                    issue="支付回调签名验证失败原因未确认",
                    source_text="技术：支付回调签名验证为什么失败，目前还没有确认原因。",
                )
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, transcript)

        self.assertEqual([item.issue for item in result.unresolved_issues], ["支付回调签名验证失败原因未确认"])

    def test_normal_unresolved_issue_is_kept(self) -> None:
        transcript = "研发：第三方SDK原因还没有确认，需要继续排查。"
        analysis = base_analysis(
            unresolved_issues=[
                UnresolvedIssue(
                    issue="第三方SDK原因还没有确认，需要继续排查",
                    source_text="研发：第三方SDK原因还没有确认，需要继续排查。",
                )
            ]
        )

        result = MeetingAnalysisPostProcessor().process(analysis, transcript)

        self.assertEqual([item.issue for item in result.unresolved_issues], ["第三方SDK原因还没有确认，需要继续排查"])
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
