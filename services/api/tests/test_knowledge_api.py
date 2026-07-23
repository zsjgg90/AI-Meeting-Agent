import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.knowledge_sync_service import mark_meeting_knowledge_deleted, sync_meeting_knowledge
from app.main import create_app
from app.models import ActionItem, Meeting, MeetingKnowledgeItem, MeetingSummary, TranscriptSegment


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


class KnowledgeApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.app = create_app()

        def override_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(self.app)
        self.seed_meeting()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def seed_meeting(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(
                id="knowledge-meeting-1",
                title="订单接口评审",
                status="completed",
                created_at=datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 7, 24, 9, 30, tzinfo=timezone.utc),
            )
            summary = MeetingSummary(
                id="summary-1",
                meeting_id=meeting.id,
                overview="会议确认订单接口优化方案。",
                agenda=[],
                topics=[],
                speaker_summaries=[],
                decisions=[],
                risks=[],
                open_questions=[],
                next_steps=[],
                meeting_agenda=[{"item": "讨论订单接口性能"}],
                meeting_summary="会议确认订单接口优化方案，并要求保留兼容逻辑。",
                key_conclusions=[{"conclusion": "订单接口优化方案已确认", "source_text": "speaker_1（1.0-3.0）：产品：订单接口优化方案已确认。"}],
                unresolved_issues=[{"issue": "压测数据口径仍需确认", "source_text": "测试：压测数据口径仍需确认。"}],
                risks_and_focus=[{"risk": "后端接口延期会影响提测", "impact": "提测排期受影响", "source_text": "研发：后端接口延期会影响提测。"}],
                model_name="qwen3:14b+rag",
                prompt_version="meeting-analyst-v1",
            )
            segment1 = TranscriptSegment(
                id="segment-1",
                meeting_id=meeting.id,
                audio_file_id=None,
                segment_index=0,
                start_time=1.0,
                end_time=3.0,
                text="产品：订单接口优化方案已确认。",
                speaker_label="speaker_1",
            )
            segment2 = TranscriptSegment(
                id="segment-2",
                meeting_id=meeting.id,
                audio_file_id=None,
                segment_index=1,
                start_time=4.0,
                end_time=6.0,
                text="测试：压测数据口径仍需确认。",
                speaker_label="speaker_2",
            )
            segment3 = TranscriptSegment(
                id="segment-3",
                meeting_id=meeting.id,
                audio_file_id=None,
                segment_index=2,
                start_time=7.0,
                end_time=9.0,
                text="研发：后端接口延期会影响提测。",
                speaker_label="speaker_3",
            )
            action = ActionItem(
                id="action-1",
                meeting_id=meeting.id,
                summary_id=summary.id,
                task="补充接口压测报告",
                source_text="测试：压测数据口径仍需确认。",
                source_segment_id="segment-2",
            )
            db.add_all([meeting, summary, segment1, segment2, segment3, action])
            db.commit()
        finally:
            db.close()

    def test_sync_is_idempotent_and_search_is_paginated(self) -> None:
        db = self.SessionLocal()
        try:
            first = sync_meeting_knowledge(db, "knowledge-meeting-1")
            first_status = first.status
            first_count = db.query(MeetingKnowledgeItem).filter_by(meeting_id="knowledge-meeting-1").count()
            second = sync_meeting_knowledge(db, "knowledge-meeting-1")
            second_status = second.status
            second_count = db.query(MeetingKnowledgeItem).filter_by(meeting_id="knowledge-meeting-1").count()
        finally:
            db.close()

        self.assertEqual(first_status, "completed")
        self.assertEqual(second_status, "completed")
        self.assertEqual(first_count, second_count)

        response = self.client.get("/knowledge/search", params={"query": "订单接口", "limit": 2, "offset": 0})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["limit"], 2)
        self.assertGreaterEqual(body["total"], 2)
        self.assertIn("items", body)

    def test_decision_result_contains_source_meeting_and_real_segment_time(self) -> None:
        db = self.SessionLocal()
        try:
            sync_meeting_knowledge(db, "knowledge-meeting-1")
        finally:
            db.close()

        response = self.client.get("/knowledge/decisions", params={"query": "订单接口"})
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["items"][0]
        self.assertEqual(item["content_type"], "key_decision")
        self.assertEqual(item["meeting_id"], "knowledge-meeting-1")
        self.assertEqual(item["meeting_title"], "订单接口评审")
        self.assertEqual(item["source_segment_id"], "segment-1")
        self.assertEqual(item["start_time"], 1.0)

    def test_resync_updates_existing_key_and_marks_removed_items_stale(self) -> None:
        db = self.SessionLocal()
        try:
            sync_meeting_knowledge(db, "knowledge-meeting-1")
            summary = db.get(MeetingSummary, "summary-1")
            summary.key_conclusions = [{"conclusion": "订单接口优化方案延期确认", "source_text": "产品：订单接口优化方案已确认。"}]
            summary.unresolved_issues = []
            db.commit()
            sync_meeting_knowledge(db, "knowledge-meeting-1")

            decision = db.scalars(
                select(MeetingKnowledgeItem).where(
                    MeetingKnowledgeItem.meeting_id == "knowledge-meeting-1",
                    MeetingKnowledgeItem.content_type == "key_decision",
                    MeetingKnowledgeItem.source_item_key == "key_decision:0",
                )
            ).first()
            stale_issue = db.scalars(
                select(MeetingKnowledgeItem).where(
                    MeetingKnowledgeItem.meeting_id == "knowledge-meeting-1",
                    MeetingKnowledgeItem.content_type == "unresolved_issue",
                )
            ).first()
        finally:
            db.close()

        self.assertEqual(decision.content, "订单接口优化方案延期确认")
        self.assertEqual(stale_issue.status, "stale")

    def test_delete_marks_knowledge_deleted(self) -> None:
        db = self.SessionLocal()
        try:
            sync_meeting_knowledge(db, "knowledge-meeting-1")
            deleted = mark_meeting_knowledge_deleted(db, "knowledge-meeting-1")
            statuses = {
                item.status
                for item in db.scalars(select(MeetingKnowledgeItem).where(MeetingKnowledgeItem.meeting_id == "knowledge-meeting-1")).all()
            }
        finally:
            db.close()

        self.assertGreater(deleted, 0)
        self.assertEqual(statuses, {"deleted"})

    def test_reindex_endpoint_queues_retry(self) -> None:
        response = self.client.post("/meetings/knowledge-meeting-1/knowledge/reindex")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(response.json()["status"], {"pending", "completed"})


if __name__ == "__main__":
    unittest.main()
