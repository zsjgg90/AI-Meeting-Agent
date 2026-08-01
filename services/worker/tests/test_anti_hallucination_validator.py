import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.anti_hallucination_validator import clear_action_fields_without_source_evidence, validate_meeting_analysis


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


if __name__ == "__main__":
    unittest.main()
