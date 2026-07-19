import argparse
import json

from app.database import SessionLocal
from app.diarization import DiarizationError
from app.transcription import TranscriptionError, transcribe_meeting


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe one meeting audio file with faster-whisper.")
    parser.add_argument("meeting_id", help="Meeting ID to transcribe.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    db = SessionLocal()
    try:
        segments = transcribe_meeting(db, args.meeting_id)
        print(
            json.dumps(
                {
                    "meeting_id": args.meeting_id,
                    "segment_count": len(segments),
                    "segments": [
                        {
                            "start_time": segment.start_time,
                            "end_time": segment.end_time,
                            "text": segment.text,
                            "speaker_label": segment.speaker_label,
                        }
                        for segment in segments
                    ],
                },
                ensure_ascii=False,
            )
        )
    except (TranscriptionError, DiarizationError) as exc:
        parser.exit(status=1, message=f"{exc}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
