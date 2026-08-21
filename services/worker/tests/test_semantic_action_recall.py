import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_pipeline import _action_recap_flags, _enhanced_action_event, _extract_rule_based_events, _should_add_action_candidate
from app.semantic_event_schema import UtteranceInput


def utterance(index: int, text: str, speaker: str = "项目经理") -> UtteranceInput:
    return UtteranceInput(
        utterance_id=f"utt-{index}",
        segment_id=f"seg-{index}",
        speaker=speaker,
        start_time=float(index * 10),
        end_time=float(index * 10 + 5),
        text=text,
    )


def enhanced_actions(utterances: list[UtteranceInput]):
    return [
        event
        for event in _extract_rule_based_events(utterances)
        if event.primary_intent == "task_assignment"
        and event.normalized_text != event.source_text
    ]


def rule_actions(utterances: list[UtteranceInput]):
    return [
        event
        for event in _extract_rule_based_events(utterances)
        if event.primary_intent == "task_assignment"
    ]


def with_intro(*rows: UtteranceInput) -> list[UtteranceInput]:
    return [utterance(0, "今天我们讨论 AI 分析稳定性和测试安排。"), *rows]


class SemanticActionRecallTest(unittest.TestCase):
    def test_quoted_negative_example_rejected(self) -> None:
        actions = rule_actions(
            with_intro(utterance(1, "模型有时候直接变成：“负责人跟进这个事情。” 但是实际上用户只是提醒一下。"))
        )

        self.assertEqual(actions, [])

    def test_progress_update_rejected(self) -> None:
        actions = rule_actions(
            with_intro(utterance(1, "我同步一下前端。 录音页面现在基本完成。 结束会议以后增加了二次确认。 生成状态也增加了处理中。", "王强"))
        )

        self.assertEqual(actions, [])

    def test_explicit_owner_assignment_kept(self) -> None:
        actions = rule_actions(
            with_intro(utterance(1, "陈涛，你负责排查 AI 分析结果波动原因。"))
        )

        self.assertTrue(any("陈涛" in event.source_text and event.primary_intent == "task_assignment" for event in actions))

    def test_explicit_sample_assignment_kept(self) -> None:
        actions = rule_actions(
            with_intro(utterance(1, "赵敏，你补充真实会议测试样本。"))
        )

        self.assertTrue(any("赵敏" in event.source_text and event.primary_intent == "task_assignment" for event in actions))

    def test_future_recording_test_arrangement_kept(self) -> None:
        actions = rule_actions(
            with_intro(utterance(1, "下午安排录音流程测试。", "王强"))
        )

        self.assertTrue(any("下午安排录音流程测试" in event.source_text for event in actions))

    def test_explicit_commitment_kept(self) -> None:
        actions = rule_actions(
            with_intro(utterance(1, "我今天先跑一批 Golden Dataset。", "陈涛"))
        )

        self.assertTrue(any("Golden Dataset" in event.source_text and event.primary_intent == "task_assignment" for event in actions))

    def test_recap_mode_extracts_task_lines(self) -> None:
        actions = enhanced_actions(
            [
                utterance(0, "最后过一下任务。大家如果我说错了直接打断。"),
                utterance(1, "前端，明天下午前修任务搜索结果闪动和 Android 后台恢复后录音计时不准。", "项目经理"),
            ]
        )

        tasks = [event.normalized_text for event in actions]

        self.assertIn("修复任务搜索结果闪动问题", tasks)

    def test_future_recap_mention_does_not_trigger_recap_mode(self) -> None:
        actions = enhanced_actions(
            [
                utterance(0, "没事，待会儿结论会再过。"),
                utterance(1, "那最好提前做个检查清单。", "产品"),
            ]
        )

        self.assertEqual(actions, [])

    def test_recap_mode_is_limited_by_utterance_count(self) -> None:
        utterances = [utterance(0, "任务再过一下。")]
        utterances.extend(utterance(index, f"普通讨论 {index}。") for index in range(1, 31))
        utterances.append(utterance(31, "前端，明天下午前修任务搜索结果闪动。"))

        flags = _action_recap_flags(utterances)

        self.assertFalse(flags[31])
        self.assertFalse(_should_add_action_candidate(utterances, 31, recap_mode=flags[31]))

    def test_short_confirmation_does_not_trigger_from_context_window(self) -> None:
        utterances = [
            utterance(0, "任务再过一下。"),
            utterance(1, "前端，明天下午前修任务搜索结果闪动。"),
            utterance(2, "好。", "前端"),
            utterance(3, "首页首次加载短暂空白，周一前给结果。"),
        ]
        flags = _action_recap_flags(utterances)

        self.assertFalse(_should_add_action_candidate(utterances, 2, recap_mode=flags[2]))

    def test_chinese_question_does_not_add_enhanced_candidate(self) -> None:
        actions = enhanced_actions(
            [
                utterance(0, "任务再过一下。"),
                utterance(1, "明天下午能修？", "项目经理"),
                utterance(2, "能否周一完成支付验证。", "项目经理"),
            ]
        )

        self.assertEqual(actions, [])

    def test_context_window_assembles_object_action_and_deadline(self) -> None:
        actions = enhanced_actions(
            [
                utterance(0, "搜索结果会闪。", "测试"),
                utterance(1, "主要还得取消旧请求，或者用 request id。", "前端"),
                utterance(2, "明天下午吧，别说“之前”太模糊。", "项目经理"),
            ]
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].normalized_text, "修复任务搜索结果闪动问题")
        self.assertIn("搜索结果会闪。", actions[0].source_text)
        self.assertIn("明天下午吧", actions[0].source_text)

    def test_weak_commitment_does_not_add_enhanced_candidate(self) -> None:
        actions = enhanced_actions(
            [
                utterance(0, "任务再过一下。"),
                utterance(1, "我回去看看。", "后端"),
            ]
        )

        self.assertEqual(actions, [])

    def test_completed_state_does_not_add_enhanced_candidate(self) -> None:
        actions = enhanced_actions(
            [
                utterance(0, "任务再过一下。"),
                utterance(1, "summary 新旧字段兼容都正常。然后知识库 reindex 也已经通了。", "后端"),
            ]
        )

        self.assertEqual(actions, [])


    def test_context_window_preserves_order_and_does_not_repeat_center_segment(self) -> None:
        before = "Search result flickers."
        center = "Use request id to cancel stale requests."
        after = "Send the result tomorrow."
        event = _enhanced_action_event(
            [
                utterance(0, before, "QA"),
                utterance(1, center, "Frontend"),
                utterance(2, after, "PM"),
            ],
            1,
            recap_mode=True,
        )

        self.assertEqual(event.segment_id, "seg-0,seg-1,seg-2")
        self.assertEqual(event.source_text.splitlines(), [before, center, after])
        self.assertEqual(event.source_text.count(center), 1)


if __name__ == "__main__":
    unittest.main()
