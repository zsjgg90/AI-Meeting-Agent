from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

from app.meeting_analysis_postprocessor import normalize_text, source_is_continuous
from app.meeting_analysis_schema import MeetingAnalysisSchema
from app.transcript_builder import build_transcript_text


MAX_WINDOW_LINES = 3
MIN_TOKEN_MATCHES = 4
MIN_TOKEN_COVERAGE = 0.45
MIN_SEQUENCE_SCORE = 0.32
MIN_SHORT_TOKEN_MATCHES = 2
MIN_SHORT_TOKEN_COVERAGE = 0.75
MIN_LONG_CJK_ANCHOR_MATCHES = 3
MIN_LONG_CJK_SEQUENCE_SCORE = 0.12


@dataclass(frozen=True)
class EvidenceWindow:
    text: str
    normalized_text: str
    start_index: int
    line_count: int
    segment_ids: tuple[str, ...] = ()
    segment_normalized_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceMatch:
    source_text: str
    score: float
    token_coverage: float
    token_matches: int


def _transcript_windows(transcript: str) -> list[EvidenceWindow]:
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    windows: list[EvidenceWindow] = []
    for start in range(len(lines)):
        for line_count in range(1, MAX_WINDOW_LINES + 1):
            end = start + line_count
            if end > len(lines):
                break
            text = "\n".join(lines[start:end])
            normalized = normalize_text(text)
            if normalized:
                windows.append(
                    EvidenceWindow(
                        text=text,
                        normalized_text=normalized,
                        start_index=start,
                        line_count=line_count,
                    )
                )
    return windows


def _segment_value(segment: Any, key: str) -> Any:
    if isinstance(segment, Mapping):
        return segment.get(key)
    return getattr(segment, key, None)


def _segment_text(segment: Any) -> str:
    return str(_segment_value(segment, "text") or "").strip()


def _segment_id(segment: Any) -> str:
    return str(_segment_value(segment, "id") or "").strip()


def _segment_to_transcript_row(segment: Any) -> dict[str, Any]:
    return {
        "speaker_name": _segment_value(segment, "speaker_name"),
        "speaker_label": _segment_value(segment, "speaker_label"),
        "start_time": _segment_value(segment, "start_time"),
        "end_time": _segment_value(segment, "end_time"),
        "text": _segment_text(segment),
    }


def _segment_sort_key(segment: Any) -> tuple[float, float, str]:
    segment_index = _segment_value(segment, "segment_index")
    start_time = _segment_value(segment, "start_time")
    try:
        segment_index_value = float(segment_index)
    except (TypeError, ValueError):
        segment_index_value = 0.0
    try:
        start_time_value = float(start_time)
    except (TypeError, ValueError):
        start_time_value = 0.0
    return (segment_index_value, start_time_value, _segment_id(segment))


def _segment_windows(transcript_segments: Iterable[Any] | None, transcript: str) -> list[EvidenceWindow]:
    if transcript_segments is None:
        return []

    rows = [
        segment
        for segment in sorted(transcript_segments, key=_segment_sort_key)
        if _segment_id(segment) and _segment_text(segment)
    ]
    windows: list[EvidenceWindow] = []
    for start in range(len(rows)):
        for line_count in range(1, MAX_WINDOW_LINES + 1):
            end = start + line_count
            if end > len(rows):
                break
            window_segments = rows[start:end]
            segment_texts = tuple(_segment_text(segment) for segment in window_segments)
            normalized_segment_texts = tuple(
                normalized
                for normalized in (normalize_text(text) for text in segment_texts)
                if normalized
            )
            text = build_transcript_text(
                [_segment_to_transcript_row(segment) for segment in window_segments]
            )
            normalized = normalize_text(text)
            if (
                normalized
                and len(normalized_segment_texts) == len(segment_texts)
                and source_is_continuous(text, transcript)
            ):
                windows.append(
                    EvidenceWindow(
                        text=text,
                        normalized_text=normalized,
                        start_index=start,
                        line_count=line_count,
                        segment_ids=tuple(_segment_id(segment) for segment in window_segments),
                        segment_normalized_texts=normalized_segment_texts,
                    )
                )
    return windows


def _cjk_bigrams(text: str) -> set[str]:
    tokens: set[str] = set()
    for block in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(block) == 1:
            continue
        if len(block) <= 4:
            tokens.add(block)
        for index in range(len(block) - 1):
            tokens.add(block[index : index + 2])
    return tokens


def _latin_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_+\-.]{1,}", text)
        if len(token) >= 2
    }


def _tokens(text: str) -> set[str]:
    return _cjk_bigrams(text) | _latin_tokens(text)


def _score_window(query: str, query_tokens: set[str], window: EvidenceWindow) -> EvidenceMatch | None:
    query_norm = normalize_text(query)
    if not query_norm or not query_tokens:
        return None

    if query_norm in window.normalized_text:
        return EvidenceMatch(
            source_text=window.text,
            score=1.0,
            token_coverage=1.0,
            token_matches=len(query_tokens),
        )

    window_tokens = _tokens(window.text)
    matches = len(query_tokens & window_tokens)
    coverage = matches / len(query_tokens)
    sequence_score = SequenceMatcher(None, query_norm, window.normalized_text).ratio()
    is_short_query = len(query_tokens) <= 3
    is_long_cjk_query = len(re.findall(r"[\u4e00-\u9fff]", query)) >= 10
    has_long_cjk_anchor_match = (
        is_long_cjk_query
        and matches >= MIN_LONG_CJK_ANCHOR_MATCHES
        and sequence_score >= MIN_LONG_CJK_SEQUENCE_SCORE
    )
    if is_short_query:
        if matches < MIN_SHORT_TOKEN_MATCHES or coverage < MIN_SHORT_TOKEN_COVERAGE:
            return None
    elif has_long_cjk_anchor_match:
        pass
    elif matches < MIN_TOKEN_MATCHES or coverage < MIN_TOKEN_COVERAGE:
        return None
    if not has_long_cjk_anchor_match and sequence_score < MIN_SEQUENCE_SCORE and coverage < 0.65:
        return None

    score = (coverage * 0.7) + (sequence_score * 0.3)
    return EvidenceMatch(
        source_text=window.text,
        score=score,
        token_coverage=coverage,
        token_matches=matches,
    )


def _best_match(query_parts: Iterable[str], windows: list[EvidenceWindow]) -> EvidenceMatch | None:
    query = " ".join(part.strip() for part in query_parts if part and part.strip())
    query_tokens = _tokens(query)
    best: tuple[float, int, int, EvidenceMatch] | None = None
    for window in windows:
        match = _score_window(query, query_tokens, window)
        if match is None:
            continue
        rank = (match.score, match.token_matches, -window.line_count, -window.start_index)
        if best is None or rank > best[:4]:
            best = (*rank, match)
    return best[4] if best is not None else None


def _segments_appear_in_order(query_norm: str, segment_norms: tuple[str, ...]) -> bool:
    offset = 0
    for segment_norm in segment_norms:
        found_at = query_norm.find(segment_norm, offset)
        if found_at < 0:
            return False
        offset = found_at + len(segment_norm)
    return True


def _source_text_segment_id(source_text: str, windows: list[EvidenceWindow]) -> str | None:
    query_norm = normalize_text(source_text)
    if len(query_norm) < 4:
        return None
    query_line_count = len([line for line in str(source_text or "").splitlines() if line.strip()])

    best: tuple[int, int, int, EvidenceWindow] | None = None
    for window in windows:
        if not window.segment_ids:
            continue
        if query_line_count > 1 and window.line_count < query_line_count:
            continue
        if window.normalized_text in query_norm or _segments_appear_in_order(
            query_norm,
            window.segment_normalized_texts,
        ):
            rank = (len(window.normalized_text), -window.line_count, -window.start_index, window)
        elif query_norm in window.normalized_text:
            rank = (len(query_norm), -window.line_count, -window.start_index, window)
        else:
            continue
        if best is None or rank[:3] > best[:3]:
            best = rank

    if best is None:
        return None
    return ",".join(best[3].segment_ids)


def _segment_id_window(source_segment_id: str | None, windows: list[EvidenceWindow]) -> EvidenceWindow | None:
    ids = tuple(part.strip() for part in str(source_segment_id or "").split(",") if part.strip())
    if not ids or len(ids) != len(set(ids)):
        return None

    for window in windows:
        if window.segment_ids == ids:
            return window
    return None


def resolve_meeting_analysis_evidence(
    analysis: MeetingAnalysisSchema,
    transcript: str,
    transcript_segments: Iterable[Any] | None = None,
) -> MeetingAnalysisSchema:
    result = analysis.model_copy(deep=True)
    windows = _transcript_windows(transcript)
    segment_windows = _segment_windows(transcript_segments, transcript)
    if not windows and not segment_windows:
        return result

    for item in result.key_conclusions:
        if source_is_continuous(item.source_text, transcript) or not windows:
            continue
        match = _best_match([item.conclusion], windows)
        if match is not None:
            item.source_text = match.source_text

    for item in result.action_items:
        segment_window = _segment_id_window(item.source_segment_id, segment_windows)
        if segment_window is not None:
            item.source_text = segment_window.text
            item.source_segment_id = ",".join(segment_window.segment_ids)
            continue

        source_segment_id = _source_text_segment_id(item.source_text, segment_windows)
        if source_segment_id:
            item.source_segment_id = source_segment_id
            rebuilt_window = _segment_id_window(source_segment_id, segment_windows)
            if rebuilt_window is not None:
                item.source_text = rebuilt_window.text

    for item in result.unresolved_issues:
        if source_is_continuous(item.source_text, transcript) or not windows:
            continue
        match = _best_match([item.issue], windows)
        if match is not None:
            item.source_text = match.source_text

    for item in result.risks_and_focus:
        if source_is_continuous(item.source_text, transcript) or not windows:
            continue
        match = _best_match([item.risk, item.impact, item.focus_area], windows)
        if match is not None:
            item.source_text = match.source_text

    return result


__all__ = [
    "resolve_meeting_analysis_evidence",
]
