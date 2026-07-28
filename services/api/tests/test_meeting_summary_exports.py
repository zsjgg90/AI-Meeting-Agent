import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.models import ActionItem, Meeting, MeetingSummary, SpeakerMapping, TranscriptSegment


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


class MeetingSummaryExportTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp_parent = Path(__file__).resolve().parents[3] / "storage" / "test_exports"
        tmp_parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=tmp_parent)
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
        self.meeting_id = "summary-export-meeting"
        self.seed_summary_meeting()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    def test_summary_export_endpoint_supports_all_mobile_formats(self) -> None:
        expected_types = {
            "md": "text/markdown",
            "txt": "text/plain",
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

        with self.storage_settings():
            for file_format, media_type in expected_types.items():
                with self.subTest(file_format=file_format):
                    response = self.client.get(f"/meetings/{self.meeting_id}/exports/summary.{file_format}")

                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIn(media_type, response.headers["content-type"])
                    self.assertGreater(len(response.content), 20)
                    if file_format in {"md", "txt"}:
                        text = response.content.decode("utf-8")
                        self.assertIn("结构化会议纪要", text)
                        self.assertIn("确认移动端 AI 纪要重构范围", text)
                        self.assertIn("状态：open", text)
                    if file_format == "pdf":
                        self.assertTrue(response.content.startswith(b"%PDF"))
                    if file_format == "docx":
                        docx_path = Path(self.tmp.name) / "summary-export.docx"
                        docx_path.write_bytes(response.content)
                        with zipfile.ZipFile(docx_path) as archive:
                            self.assertIn("word/document.xml", archive.namelist())

    def test_summary_export_rejects_unsupported_format(self) -> None:
        with self.storage_settings():
            response = self.client.get(f"/meetings/{self.meeting_id}/exports/summary.xlsx")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported export format", response.text)

    def seed_summary_meeting(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(
                id=self.meeting_id,
                title="AI纪要导出测试会议",
                status="completed",
                location="会议室 A",
            )
            summary = MeetingSummary(
                id="summary-export-summary",
                meeting_id=self.meeting_id,
                overview="legacy overview",
                agenda=[{"item": "legacy agenda"}],
                topics=[],
                speaker_summaries=[],
                decisions=[],
                risks=[],
                open_questions=[],
                meeting_agenda=[{"item": "确认移动端 AI 纪要重构范围", "source_text": "只重构前端展示"}],
                meeting_summary="会议确认 AI 纪要页使用正式六维结果。",
                key_conclusions=[{"conclusion": "不修改后端接口", "source_text": "不修改后端"}],
                unresolved_issues=[{"issue": "真机视觉回归后续补充"}],
                risks_and_focus=[{"risk": "避免误用原文导出"}],
                model_name="fixture-gold-standard",
            )
            action = ActionItem(
                id="summary-export-action",
                meeting_id=self.meeting_id,
                summary_id=summary.id,
                task="更新移动端 AI 纪要展示",
                owner_name="说话人1",
                deadline="2026-07-28",
                priority="medium",
                status="open",
                source_text="需要完成 AI 纪要展示重构",
            )
            segment = TranscriptSegment(
                id="summary-export-segment",
                meeting_id=self.meeting_id,
                audio_file_id=None,
                segment_index=0,
                start_time=1.0,
                end_time=3.0,
                text="需要完成 AI 纪要展示重构",
                speaker_label="spk_0",
                speaker_name=None,
                speaker_gender=None,
                semantic_label=None,
            )
            speaker = SpeakerMapping(
                id="summary-export-speaker",
                meeting_id=self.meeting_id,
                speaker_label="spk_0",
                display_name="说话人1",
            )
            db.add_all([meeting, summary, action, segment, speaker])
            db.commit()
        finally:
            db.close()

    def storage_settings(self):
        return patch(
            "app.services.meeting_exports.get_settings",
            return_value=Settings(database_url="sqlite://", storage_dir=self.tmp.name),
        )


if __name__ == "__main__":
    unittest.main()
