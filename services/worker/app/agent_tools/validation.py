from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


class ValidateMeetingAnalysisTool(AgentTool):
    def __init__(
        self,
        *,
        validator: Callable[[dict[str, Any], str], tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
        policy: ToolPolicy | None = None,
    ) -> None:
        super().__init__(
            name="validate_meeting_analysis",
            policy=policy
            or ToolPolicy(
                timeout_seconds=10,
                max_calls_per_run=3,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        self.validator = validator

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = payload.get("analysis")
        if not isinstance(analysis, dict):
            raise ValueError("analysis must be a dict")
        transcript = self._transcript_text(payload.get("transcript"))
        if not transcript:
            raise ValueError("transcript is required")

        validator = self.validator
        if validator is None:
            from app.anti_hallucination_validator import validate_meeting_analysis_with_audit

            validator = validate_meeting_analysis_with_audit

        validated, audit = validator(analysis, transcript)
        metadata = analysis.get("_metadata") if isinstance(analysis.get("_metadata"), dict) else {}
        warnings = [
            item
            for item in audit
            if str(item.get("action") or "") in {"remove", "modify"}
        ]
        return {
            "meeting_id": payload.get("meeting_id") or context.meeting_id,
            "validated_analysis": validated,
            "validator_audit": audit,
            "warnings": warnings,
            "_result_source": str(metadata.get("result_source") or "validator"),
        }

    def _transcript_text(self, transcript: Any) -> str:
        if isinstance(transcript, str):
            return transcript.strip()
        if isinstance(transcript, list):
            from app.transcript_builder import build_transcript_text

            return build_transcript_text(transcript)
        return ""


__all__ = ["ValidateMeetingAnalysisTool"]
