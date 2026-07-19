import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.stt_providers import build_volcengine_submit_payload, extract_volcengine_segments
from app.transcript_builder import build_transcript_text
from app.transcription import TranscriptSegmentResult, number_of_speakers_for_meeting


class DummyMeeting:
    def __init__(self, participant_count: int | None = None) -> None:
        self.participant_count = participant_count


class VolcengineSpeakerDiarizationTest(unittest.TestCase):
    def test_submit_payload_uses_known_two_speakers(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_file.write(b"fake audio")
            audio_path = Path(audio_file.name)
        try:
            payload = build_volcengine_submit_payload(audio_path, number_of_speakers=2)
        finally:
            audio_path.unlink(missing_ok=True)

        request = payload["request"]
        self.assertTrue(request["enable_speaker_info"])
        self.assertTrue(request["show_utterances"])
        self.assertEqual(request["NumberOfSpeaker"], 2)

    def test_unknown_speaker_count_uses_zero(self) -> None:
        self.assertEqual(number_of_speakers_for_meeting(DummyMeeting(None)), 0)
        self.assertEqual(number_of_speakers_for_meeting(DummyMeeting(0)), 0)
        self.assertEqual(number_of_speakers_for_meeting(DummyMeeting(11)), 0)

    def test_extract_utterances_maps_speaker_zero_and_one(self) -> None:
        segments = extract_volcengine_segments(
            {
                "result": {
                    "utterances": [
                        {
                            "start_time": 0.2,
                            "end_time": 4.6,
                            "text": "今天我们讨论项目进度",
                            "additions": {"speaker": "0"},
                        },
                        {
                            "start_time": 4.8,
                            "end_time": 9.2,
                            "text": "我这边开发模块已经完成",
                            "additions": {"speaker": "1"},
                        },
                    ]
                }
            }
        )

        self.assertEqual([segment.speaker_label for segment in segments], ["speaker_0", "speaker_1"])
        self.assertEqual(segments[0].start_time, 0.2)
        self.assertEqual(segments[1].end_time, 9.2)

    def test_missing_speaker_uses_unknown(self) -> None:
        segments = extract_volcengine_segments(
            {
                "result": {
                    "utterances": [
                        {
                            "start_time": 1.0,
                            "end_time": 2.0,
                            "text": "没有说话人标签",
                        }
                    ]
                }
            }
        )

        self.assertEqual(segments[0].speaker_label, "speaker_unknown")

    def test_no_utterances_falls_back_to_transcript_text(self) -> None:
        segments = extract_volcengine_segments({"result": {"text": "这是完整转写文本"}}, duration_seconds=8.0)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].text, "这是完整转写文本")
        self.assertIsNone(segments[0].speaker_label)
        self.assertEqual(segments[0].end_time, 8.0)

    def test_build_transcript_text_preserves_speaker_prefix(self) -> None:
        text = build_transcript_text(
            [
                {
                    "speaker_label": "speaker_0",
                    "start_time": 0.2,
                    "end_time": 4.6,
                    "text": "今天我们讨论项目进度",
                },
                {
                    "speaker_label": "speaker_1",
                    "start_time": 4.8,
                    "end_time": 9.2,
                    "text": "我这边开发模块已经完成",
                },
            ]
        )

        self.assertIn("speaker_0", text)
        self.assertIn("speaker_1", text)


if __name__ == "__main__":
    unittest.main()
