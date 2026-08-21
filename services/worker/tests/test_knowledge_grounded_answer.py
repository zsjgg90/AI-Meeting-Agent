import unittest

from app.knowledge_grounded_answer import (
    FALLBACK_ANSWER,
    KnowledgeAnswerSource,
    KnowledgeGroundedAnswerRequest,
    answer_from_sources,
)


class FakeOllamaClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict] = []

    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.response


class KnowledgeGroundedAnswerTest(unittest.TestCase):
    def test_answers_from_sources_with_grounding_prompt(self) -> None:
        client = FakeOllamaClient("Login was delayed.")
        result = answer_from_sources(
            KnowledgeGroundedAnswerRequest(
                query="Why was login delayed?",
                structured_facts={"meetings": {"count": 1}},
                sources=[
                    KnowledgeAnswerSource(
                        knowledge_id="k1",
                        meeting_id="m1",
                        meeting_title="Login Review",
                        knowledge_type="decision",
                        source_text="Product: Delay login module to next iteration.",
                        speaker="Product",
                        meeting_time="2026-08-13T09:00:00Z",
                        source_segment_id="s1",
                    )
                ],
            ),
            llm_client=client,
        )

        self.assertTrue(result.answer.startswith("Login was delayed."))
        self.assertIn("证据原文要点：", result.answer)
        self.assertIn("Product: Delay login module to next iteration.", result.answer)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("User Question", client.calls[0]["prompt"])
        self.assertIn("Structured Facts", client.calls[0]["prompt"])
        self.assertIn("Retrieved Evidence", client.calls[0]["prompt"])
        self.assertIn('"count": 1', client.calls[0]["prompt"])
        self.assertIn("Do not use outside knowledge", client.calls[0]["system_prompt"])

    def test_no_evidence_or_facts_returns_fallback_without_model_call(self) -> None:
        client = FakeOllamaClient("should not be used")
        result = answer_from_sources(
            KnowledgeGroundedAnswerRequest(query="Anything?", sources=[]),
            llm_client=client,
        )

        self.assertEqual(result.answer, FALLBACK_ANSWER)
        self.assertEqual(client.calls, [])

    def test_fallback_with_sources_keeps_evidence_notes(self) -> None:
        client = FakeOllamaClient(FALLBACK_ANSWER)
        result = answer_from_sources(
            KnowledgeGroundedAnswerRequest(
                query="本周是否决定采购云GPU？",
                sources=[
                    KnowledgeAnswerSource(
                        knowledge_id="k1",
                        meeting_id="m1",
                        meeting_title="AI稳定性专项会",
                        knowledge_type="risk",
                        source_text="本地14B模型服务器当前压力较大，后面需要考虑云GPU或者其他方案。",
                    )
                ],
            ),
            llm_client=client,
        )

        self.assertTrue(result.answer.startswith("暂未找到明确证据支持该结论。"))
        self.assertIn("证据原文要点：", result.answer)
        self.assertIn("云GPU", result.answer)
        self.assertEqual(len(client.calls), 1)

    def test_structured_facts_without_evidence_can_be_answered_by_model(self) -> None:
        client = FakeOllamaClient("本周共 2 次会议。")
        result = answer_from_sources(
            KnowledgeGroundedAnswerRequest(
                query="本周开了几次会议？",
                structured_facts={"meetings": {"count": 2, "items": []}},
                sources=[],
            ),
            llm_client=client,
        )

        self.assertEqual(result.answer, "本周共 2 次会议。")
        self.assertEqual(len(client.calls), 1)
        self.assertIn(
            "Never add or infer missing quantities, owners, deadlines, decisions, or risks",
            client.calls[0]["system_prompt"],
        )

    def test_decision_evidence_prompt_does_not_force_fallback(self) -> None:
        client = FakeOllamaClient("最近关键决策是优先加急优化并锁定迭代内容。")
        result = answer_from_sources(
            KnowledgeGroundedAnswerRequest(
                query="最近有哪些关键决策？",
                sources=[
                    KnowledgeAnswerSource(
                        knowledge_id="k1",
                        meeting_id="m1",
                        meeting_title="项目周进度同步与版本排期会",
                        knowledge_type="decision",
                        source_text="优先加急优化，明天上午必须完成，确保不影响下午整体联调和测试工作。",
                    ),
                    KnowledgeAnswerSource(
                        knowledge_id="k2",
                        meeting_id="m1",
                        meeting_title="项目周进度同步与版本排期会",
                        knowledge_type="decision",
                        source_text="产品这边同步跟进，确认所有需求无变更，锁定本期迭代内容。",
                    ),
                ],
            ),
            llm_client=client,
        )

        self.assertTrue(result.answer.startswith("最近关键决策是优先加急优化并锁定迭代内容。"))
        self.assertIn("证据原文要点：", result.answer)
        self.assertIn("明天上午必须完成", result.answer)
        self.assertIn("Structured Facts and Retrieved Evidence", client.calls[0]["system_prompt"])
        self.assertIn("最近有哪些关键决策？", client.calls[0]["prompt"])

    def test_partial_evidence_rule_is_explicit_in_prompt(self) -> None:
        client = FakeOllamaClient("AI stability is assigned. 暂未找到明确证据")
        result = answer_from_sources(
            KnowledgeGroundedAnswerRequest(
                query="谁负责 AI 稳定性优化？什么时候完成？",
                sources=[
                    KnowledgeAnswerSource(
                        knowledge_id="k1",
                        meeting_id="m1",
                        meeting_title="AI Stability Review",
                        knowledge_type="action",
                        source_text="AI 负责稳定性优化。",
                    )
                ],
            ),
            llm_client=client,
        )

        self.assertTrue(result.answer.startswith("AI stability is assigned. 暂未找到明确证据"))
        self.assertIn("证据原文要点：", result.answer)
        self.assertIn("AI 负责稳定性优化。", result.answer)
        self.assertIn("partial evidence", client.calls[0]["system_prompt"].lower())
        self.assertIn("暂未找到明确证据", client.calls[0]["prompt"])
        self.assertIn("If one part of the question is supported", client.calls[0]["prompt"])

    def test_prompt_forbids_adding_missing_decisions_and_risks(self) -> None:
        client = FakeOllamaClient("暂未找到明确证据")
        answer_from_sources(
            KnowledgeGroundedAnswerRequest(
                query="本月有哪些主要风险？",
                structured_facts={"scope": {"date_range": "this_month"}},
                sources=[
                    KnowledgeAnswerSource(
                        knowledge_id="k1",
                        meeting_id="m1",
                        meeting_title="Weekly",
                        knowledge_type="meeting_summary",
                        source_text="会议讨论了版本进度和测试计划。",
                    )
                ],
            ),
            llm_client=client,
        )

        prompt = client.calls[0]["prompt"]
        system_prompt = client.calls[0]["system_prompt"]
        self.assertIn("decisions, and risks must appear only when explicitly present", prompt)
        self.assertIn(
            "Never add or infer missing quantities, owners, deadlines, decisions, or risks",
            system_prompt,
        )
        self.assertIn("Do not rewrite structured facts into new facts", system_prompt)


if __name__ == "__main__":
    unittest.main()
