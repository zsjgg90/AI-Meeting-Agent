import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.anti_hallucination_validator import clear_action_fields_without_source_evidence, validate_meeting_analysis
from app.meeting_analysis_pipeline import _rule_intent


TRANSCRIPT = "\n".join(
    [
        "项目负责人（0.0-8.0）：各位大家下午好，今天会议控制在30分钟。首先请产品介绍本期迭代内容。",
        "产品经理（10.0-18.0）：本期核心有三大模块：会员体系升级、订单结算逻辑优化、后台数据看板改版。",
        "UI设计师（20.0-28.0）：如果开发提前介入，会出现设计未定稿导致返工的风险。",
        "项目负责人（30.0-38.0）：UI设计周期一周，所有人严格遵循设计定稿后再开发，禁止边改边开发。",
        "前端负责人（40.0-48.0）：建议将2个P2级的次要看板功能延后至下一期迭代。",
        "项目负责人（50.0-58.0）：我同意前端建议，将两个非核心P2看板功能砍掉至下期。",
        "产品经理（60.0-68.0）：我会后更新迭代范围，剔除两个次要功能，重新同步排期表。",
        "后端负责人（70.0-78.0）：第三方积分接口回调超时没有明确容错方案，需求文档里没有写极端场景。",
        "产品经理（80.0-88.0）：确实遗漏，我会后补充异常场景、超时重试、失败回滚方案，今天内更新文档。",
        "测试负责人（90.0-98.0）：那我这边等文档更新完毕后，明日启动测试用例编写，提前覆盖异常场景。",
    ]
)


class AntiHallucinationValidatorTest(unittest.TestCase):
    def test_agenda_is_compressed_and_flow_talk_removed(self) -> None:
        raw = {
            "meeting_agenda": [
                "大家下午好",
                "产品介绍本期迭代内容",
                "UI设计师补充设计排期风险",
                "后端负责人评估工作量与周期",
                "前端负责人说明开发难点",
                "测试负责人提出需求锁定建议",
                "项目负责人协调排期与风险控制",
                "产品经理调整需求优先级",
                "后端负责人补充接口容错问题",
                "测试负责人确认测试计划",
            ]
        }

        result = validate_meeting_analysis(raw, TRANSCRIPT)

        self.assertLessEqual(len(result["meeting_agenda"]), 6)
        self.assertNotIn("大家下午好", result["meeting_agenda"])
        self.assertFalse(any("风险" in item for item in result["meeting_agenda"]))

    def test_cross_dimension_duplicate_is_removed_but_decision_and_action_can_coexist(self) -> None:
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "将两个非核心P2看板功能砍掉至下期",
                    "source_text": "项目负责人（50.0-58.0）：我同意前端建议，将两个非核心P2看板功能砍掉至下期。",
                },
                {
                    "conclusion": "补充第三方积分接口异常场景方案",
                    "source_text": "产品经理（80.0-88.0）：确实遗漏，我会后补充异常场景、超时重试、失败回滚方案，今天内更新文档。",
                },
            ],
            "action_items": [
                {
                    "owner_name": "产品经理",
                    "task": "补充第三方积分接口异常场景方案",
                    "deadline": "今天内",
                    "priority": "high",
                    "source_text": "产品经理（80.0-88.0）：确实遗漏，我会后补充异常场景、超时重试、失败回滚方案，今天内更新文档。",
                },
                {
                    "owner_name": "产品经理",
                    "task": "更新迭代范围并重新同步排期表",
                    "source_text": "产品经理（60.0-68.0）：我会后更新迭代范围，剔除两个次要功能，重新同步排期表。",
                },
            ],
        }

        result = validate_meeting_analysis(raw, TRANSCRIPT)

        conclusions = [item["conclusion"] for item in result["key_conclusions"]]
        tasks = [item["task"] for item in result["action_items"]]
        self.assertIn("将两个非核心P2看板功能砍掉至下期", conclusions)
        self.assertIn("更新迭代范围并重新同步排期表", tasks)
        self.assertIn("补充第三方积分接口异常场景方案", tasks)
        self.assertNotIn("补充第三方积分接口异常场景方案", conclusions)

    def test_complete_source_passes_and_ellipsis_source_is_rejected_or_repaired(self) -> None:
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "UI设计周期一周，禁止边改边开发",
                    "source_text": "项目负责人（30.0-38.0）：UI设计周期一周，所有人严格遵循设计定稿后再开发，禁止边改边开发。",
                },
                {
                    "conclusion": "后端需要新增十余张数据表",
                    "source_text": "后端负责人：...需要新增十余张数据表",
                },
            ]
        }

        result = validate_meeting_analysis(raw, TRANSCRIPT)

        conclusions = [item["conclusion"] for item in result["key_conclusions"]]
        self.assertIn("UI设计周期一周，禁止边改边开发", conclusions)
        self.assertNotIn("后端需要新增十余张数据表", conclusions)

    def test_owner_deadline_priority_without_source_evidence_are_cleared(self) -> None:
        raw = {
            "action_items": [
                {
                    "owner_name": "项目负责人",
                    "task": "每日晚同步进度",
                    "deadline": "今天内",
                    "priority": "high",
                    "source_text": "项目负责人（30.0-38.0）：UI设计周期一周，所有人严格遵循设计定稿后再开发，禁止边改边开发。",
                }
            ]
        }

        result = validate_meeting_analysis(raw, TRANSCRIPT)
        item = result["action_items"][0]

        self.assertIsNone(item["owner_name"])
        self.assertIsNone(item["deadline"])
        self.assertIsNone(item["priority"])

    def test_owner_deadline_can_use_evidence_text_or_semantic_attributes(self) -> None:
        raw = {
            "action_items": [
                {
                    "owner_name": "Alice",
                    "deadline": "Friday",
                    "source_text": "ship payment flow",
                    "evidence_text": "Alice will ship payment flow on Friday",
                    "priority": None,
                },
                {
                    "owner_name": "Bob",
                    "deadline": "Monday",
                    "source_text": "prepare rollout checklist",
                    "semantic_event": {
                        "attributes": {
                            "owner": "Bob",
                            "deadline": "Monday",
                        },
                        "evidence": {
                            "source_text": "prepare rollout checklist",
                        },
                    },
                    "priority": None,
                },
                {
                    "owner_name": "Carol",
                    "deadline": "Tuesday",
                    "source_text": "prepare release note",
                    "priority": None,
                },
            ]
        }

        result = clear_action_fields_without_source_evidence(raw)
        items = result["action_items"]

        self.assertEqual(items[0]["owner_name"], "Alice")
        self.assertEqual(items[0]["deadline"], "Friday")
        self.assertEqual(items[1]["owner_name"], "Bob")
        self.assertEqual(items[1]["deadline"], "Monday")
        self.assertIsNone(items[2]["owner_name"])
        self.assertIsNone(items[2]["deadline"])

    def test_proposal_cannot_enter_core_conclusions(self) -> None:
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "建议将2个P2级的次要看板功能延后至下一期迭代",
                    "source_text": "前端负责人（40.0-48.0）：建议将2个P2级的次要看板功能延后至下一期迭代。",
                }
            ]
        }

        result = validate_meeting_analysis(raw, TRANSCRIPT)

        self.assertEqual(result["key_conclusions"], [])

    def test_unresolved_cannot_enter_core_conclusions(self) -> None:
        transcript = "项目经理：这个方向先推进，但是底层重构是否启动，本次会议暂时不做最终决定。"
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "底层重构是否启动的最终决定将延后至后续会议",
                    "source_text": "本次会议暂时不做最终决定",
                }
            ],
            "unresolved_issues": [
                {
                    "issue": "底层重构启动时机未明确",
                    "source_text": "本次会议暂时不做最终决定",
                }
            ],
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(result["key_conclusions"], [])
        self.assertEqual(result["unresolved_issues"][0]["issue"], "底层重构启动时机未明确")

    def test_project_delivery_001_boundaries_are_filtered(self) -> None:
        transcript = "\n".join(
            [
                "项目经理：今天复盘客户交付项目阶段情况，重点确认当前问题、短期方案和后续安排。",
                "后端负责人：目前看不是单点问题。短期可以优化流程和页面说明，但是底层能力还没有完全准备好，如果直接做完整方案，时间风险比较高。",
                "客户成功：我建议先做可以快速上线的部分，长期能力建设放到后续阶段。",
                "项目经理：这个方向先推进，但是底层重构是否启动，本次会议暂时不做最终决定。",
                "实施顾问：第一版改动可以配合，不过规则边界需要提前确认，否则联调可能反复。",
                "项目经理：如果指标继续没有改善，需要重新评估资源投入。",
            ]
        )
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "底层重构是否启动的最终决定将延后至后续会议",
                    "source_text": "本次会议暂时不做最终决定",
                },
                {
                    "conclusion": "若指标持续未改善需重新评估资源投入",
                    "source_text": "如果指标继续没有改善，需要重新评估资源投入",
                },
            ],
            "action_items": [
                {
                    "owner_name": None,
                    "task": "推进可快速上线的部分功能开发",
                    "deadline": None,
                    "priority": "medium",
                    "source_text": "这个方向先推进",
                },
                {
                    "owner_name": None,
                    "task": "确认规则边界以避免联调反复",
                    "deadline": None,
                    "priority": "medium",
                    "source_text": "规则边界需要提前确认，否则联调可能反复",
                },
            ],
            "unresolved_issues": [
                {
                    "issue": "底层重构启动时机未明确",
                    "source_text": "本次会议暂时不做最终决定",
                },
                {
                    "issue": "规则边界未达成具体确认",
                    "source_text": "规则边界需要提前确认，否则联调可能反复",
                },
            ],
            "risks_and_focus": [
                {
                    "risk": "底层能力未准备就绪导致时间风险",
                    "impact": "完整方案实施可能延迟",
                    "source_text": "底层能力还没有完全准备好，如果直接做完整方案，时间风险比较高",
                },
                {
                    "risk": "指标未改善导致资源投入调整",
                    "impact": "可能影响项目整体进度",
                    "source_text": "如果指标继续没有改善，需要重新评估资源投入",
                },
            ],
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(
            [item["conclusion"] for item in result["key_conclusions"]],
            ["优先执行当前可落地方案"],
        )
        self.assertEqual(result["action_items"], [])
        self.assertEqual(
            [item["issue"] for item in result["unresolved_issues"]],
            ["底层重构启动时机未明确"],
        )
        self.assertEqual(
            [item["risk"] for item in result["risks_and_focus"]],
            ["方案延期可能影响交付节奏"],
        )

    def test_non_final_decision_text_cannot_enter_key_conclusions(self) -> None:
        transcript = "项目经理：底层重构是否启动，本次会议暂时不做最终决定。"
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "底层重构暂时不做最终决定",
                    "source_text": "本次会议暂时不做最终决定",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(result["key_conclusions"], [])

    def test_conditional_risk_source_is_kept_and_clamped(self) -> None:
        transcript = "项目经理：如果指标继续下降，可能影响交付。"
        raw = {
            "risks_and_focus": [
                {
                    "risk": "指标下降一定导致交付失败",
                    "source_text": "如果指标继续下降，可能影响交付",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(len(result["risks_and_focus"]), 1)
        self.assertEqual(result["risks_and_focus"][0]["risk"], "如果指标继续下降，可能影响交付")

    def test_requirement_action_cannot_enter_unresolved_issues(self) -> None:
        transcript = "前端负责人：如果确定方案，需要同步组件规范。"
        raw = {
            "unresolved_issues": [
                {
                    "issue": "组件规范需要同步",
                    "source_text": "需要同步组件规范",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(result["unresolved_issues"], [])

    def test_plain_proposal_cannot_enter_key_conclusions(self) -> None:
        transcript = "产品经理：建议先优化流程。"
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "建议先优化流程",
                    "source_text": "建议先优化流程",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(result["key_conclusions"], [])

    def test_strong_decision_can_enter_key_conclusions(self) -> None:
        transcript = "产品经理：确定采用方案A。"
        raw = {
            "key_conclusions": [
                {
                    "conclusion": "确定采用方案A",
                    "source_text": "确定采用方案A",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual([item["conclusion"] for item in result["key_conclusions"]], ["确定采用方案A"])

    def test_explicit_need_verify_can_enter_action_items(self) -> None:
        transcript = "设计负责人：需要验证新版交互数据。"
        raw = {
            "action_items": [
                {
                    "task": "验证新版交互数据",
                    "owner_name": "产品经理",
                    "deadline": "本周",
                    "source_text": "需要验证新版交互数据",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual([item["task"] for item in result["action_items"]], ["验证新版交互数据"])
        self.assertIsNone(result["action_items"][0]["owner_name"])
        self.assertIsNone(result["action_items"][0]["deadline"])

    def test_explicit_need_sync_can_enter_action_items(self) -> None:
        transcript = "前端负责人：需要同步组件规范。"
        raw = {
            "action_items": [
                {
                    "task": "同步组件规范",
                    "owner_name": None,
                    "deadline": None,
                    "source_text": "需要同步组件规范",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual([item["task"] for item in result["action_items"]], ["同步组件规范"])

    def test_suggestion_optimize_cannot_enter_action_items(self) -> None:
        transcript = "产品经理：建议优化流程。"
        raw = {
            "action_items": [
                {
                    "task": "优化流程",
                    "source_text": "建议优化流程",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(result["action_items"], [])

    def test_can_consider_cannot_enter_action_items(self) -> None:
        transcript = "产品经理：可以考虑优化流程。"
        raw = {
            "action_items": [
                {
                    "task": "优化流程",
                    "source_text": "可以考虑优化流程",
                }
            ]
        }

        result = validate_meeting_analysis(raw, transcript)

        self.assertEqual(result["action_items"], [])

    def test_fast_path_action_boundary(self) -> None:
        self.assertEqual(_rule_intent("需要验证新版交互数据", 1), "task_assignment")
        self.assertEqual(_rule_intent("需要同步组件规范", 1), "task_assignment")
        self.assertEqual(_rule_intent("建议优化流程", 1), "proposal")
        self.assertEqual(_rule_intent("可以考虑优化流程", 1), "proposal")


if __name__ == "__main__":
    unittest.main()
