from pathlib import Path
import re

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.diarization import DiarizationError, DiarizationSegment, overlap_seconds, run_diarization
from app.models import AudioFile, TranscriptSegment


class SpeakerAgent:
    name = "speaker"

    def run(
        self,
        db: Session,
        meeting_id: str,
        segments: list[TranscriptSegment],
        audio_path: Path | None = None,
    ) -> tuple[list[TranscriptSegment], AgentResult]:
        diarization_status = "skipped"
        diarization_error: str | None = None
        diarization_segments: list[DiarizationSegment] = []
        existing_speaker_labels = sorted({segment.speaker_label for segment in segments if segment.speaker_label})
        audio_file_count = int(
            db.scalar(select(func.count(AudioFile.id)).where(AudioFile.meeting_id == meeting_id)) or 0
        )
        provider_speaker_labels_are_stable = bool(existing_speaker_labels) and all(
            re.fullmatch(r"speaker_\d+", label) or label == "speaker_unknown"
            for label in existing_speaker_labels
        )
        speaker_labels_are_stable = audio_file_count <= 1 or provider_speaker_labels_are_stable

        if existing_speaker_labels and speaker_labels_are_stable:
            return (
                segments,
                AgentResult(
                    agent=self.name,
                    status="completed",
                    data={
                        "diarization_status": "provided_by_transcript_provider",
                        "diarization_error": None,
                        "diarization_segment_count": 0,
                        "speaker_count": len(existing_speaker_labels),
                        "speaker_labels": existing_speaker_labels,
                        "speaker_label_stability": "stable_single_audio",
                        "updated_transcript_segment_count": 0,
                        "voiceprint_matching": "reserved",
                    },
                ),
            )

        if audio_path is not None and segments:
            try:
                diarization_segments = run_diarization(audio_path)
                diarization_status = "completed"
            except DiarizationError as exc:
                diarization_status = "unavailable"
                diarization_error = str(exc)

        updated_count = 0
        if diarization_segments:
            for segment in segments:
                speaker_label = self.match_speaker_label(segment, diarization_segments)
                if speaker_label and segment.speaker_label != speaker_label:
                    segment.speaker_label = speaker_label
                    updated_count += 1
            db.commit()
            for segment in segments:
                db.refresh(segment)

        speaker_labels = sorted({segment.speaker_label for segment in segments if segment.speaker_label})
        return (
            segments,
            AgentResult(
                agent=self.name,
                status="completed",
                data={
                    "diarization_status": diarization_status,
                    "diarization_error": diarization_error,
                    "diarization_segment_count": len(diarization_segments),
                    "speaker_count": len(speaker_labels),
                    "speaker_labels": speaker_labels,
                    "speaker_label_stability": "recomputed_from_full_audio" if audio_file_count > 1 else "recomputed",
                    "updated_transcript_segment_count": updated_count,
                    "voiceprint_matching": "reserved",
                },
            ),
        )

    @staticmethod
    def match_speaker_label(
        transcript_segment: TranscriptSegment,
        diarization_segments: list[DiarizationSegment],
    ) -> str | None:
        best_speaker_label: str | None = None
        best_overlap = 0.0
        for diarization_segment in diarization_segments:
            overlap = overlap_seconds(
                transcript_segment.start_time,
                transcript_segment.end_time,
                diarization_segment.start_time,
                diarization_segment.end_time,
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker_label = diarization_segment.speaker_label
        return best_speaker_label
