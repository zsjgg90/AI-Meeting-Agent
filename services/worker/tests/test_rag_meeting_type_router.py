import unittest
from pathlib import Path
import sys


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)


from app.rag_meeting_type_router import (
    route_rag_meeting_type,
)


class RagMeetingTypeRouterTest(unittest.TestCase):
    def test_routes_requirement_review(self) -> None:
        route = route_rag_meeting_type(
            "今天进行需求评审，重点确认需求范围和验收标准。"
        )

        self.assertIsNotNone(route)
        assert route is not None

        self.assertEqual(
            route.meeting_type,
            "requirement_review",
        )
        self.assertEqual(
            route.scenario,
            "requirement_review",
        )

    def test_routes_project_weekly(self) -> None:
        route = route_rag_meeting_type(
            "本次项目周会同步本周进度、联调进度和下周计划。"
        )

        self.assertIsNotNone(route)
        assert route is not None

        self.assertEqual(
            route.meeting_type,
            "project_weekly",
        )
        self.assertEqual(
            route.scenario,
            "project_weekly",
        )

    def test_routes_technical_incident(self) -> None:
        route = route_rag_meeting_type(
            "线上接口超时触发告警，目前根因尚未确认，"
            "本次进行技术故障复盘。"
        )

        self.assertIsNotNone(route)
        assert route is not None

        self.assertEqual(
            route.meeting_type,
            "technical_incident",
        )
        self.assertEqual(
            route.scenario,
            "technical_incident",
        )

    def test_returns_none_for_unknown_meeting(self) -> None:
        route = route_rag_meeting_type(
            "大家简单聊一下近期工作情况。"
        )

        self.assertIsNone(route)

    def test_returns_none_for_empty_transcript(self) -> None:
        self.assertIsNone(
            route_rag_meeting_type("")
        )

    def test_returns_none_for_tied_routes(self) -> None:
        route = route_rag_meeting_type(
            "今天既进行需求评审，也同步项目周会。"
        )

        self.assertIsNone(route)


if __name__ == "__main__":
    unittest.main()