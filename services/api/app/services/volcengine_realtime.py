import asyncio
import gzip
import json
import struct
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

import websockets

from app.config import get_settings
from app.secrets import resolve_volcengine_api_key


class RealtimeAsrError(RuntimeError):
    pass


class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111


class MessageFlags:
    POS_SEQUENCE = 0b0001
    NEG_WITH_SEQUENCE = 0b0011


def _header(message_type: int, flags: int, serialization: int = 0b0001, compression: int = 0b0001) -> bytes:
    return bytes(
        [
            (0b0001 << 4) | 1,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0,
        ]
    )


def _frame(message_type: int, flags: int, sequence: int, payload: bytes, serialize_json: bool = False) -> bytes:
    if serialize_json:
        payload = json.dumps(json.loads(payload.decode("utf-8")), ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(payload)
    return b"".join(
        [
            _header(message_type, flags),
            struct.pack(">i", sequence),
            struct.pack(">I", len(compressed)),
            compressed,
        ]
    )


def _parse_frame(message: bytes) -> dict[str, Any]:
    if len(message) < 4:
        raise RealtimeAsrError("Volcengine ASR returned an invalid frame.")

    header_size = message[0] & 0x0F
    message_type = message[1] >> 4
    flags = message[1] & 0x0F
    serialization = message[2] >> 4
    compression = message[2] & 0x0F
    payload = message[header_size * 4 :]

    payload_sequence = 0
    if flags & 0x01:
        payload_sequence = struct.unpack(">i", payload[:4])[0]
        payload = payload[4:]

    is_last = bool(flags & 0x02)

    if message_type == MessageType.SERVER_FULL_RESPONSE:
        payload_size = struct.unpack(">I", payload[:4])[0]
        payload = payload[4 : 4 + payload_size]
        code = 0
    elif message_type == MessageType.SERVER_ERROR_RESPONSE:
        code = struct.unpack(">i", payload[:4])[0]
        payload_size = struct.unpack(">I", payload[4:8])[0]
        payload = payload[8 : 8 + payload_size]
    else:
        code = 0

    if payload and compression == 0b0001:
        payload = gzip.decompress(payload)

    payload_msg: dict[str, Any] | None = None
    if payload and serialization == 0b0001:
        payload_msg = json.loads(payload.decode("utf-8"))

    return {
        "code": code,
        "payload_sequence": payload_sequence,
        "is_last_package": is_last,
        "payload_msg": payload_msg,
    }


def normalize_speaker_label(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("spk_"):
        suffix = lower.removeprefix("spk_")
        if suffix.isdigit():
            return f"Speaker {int(suffix) + 1}"
    if lower.startswith("speaker_"):
        suffix = lower.removeprefix("speaker_")
        if suffix.isdigit():
            return f"Speaker {int(suffix) + 1}"
    if lower.isdigit():
        return f"Speaker {int(lower) + 1}"
    return raw


def normalize_gender(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in {"male", "man", "m", "男", "男性"}:
        return "male"
    if raw in {"female", "woman", "f", "女", "女性"}:
        return "female"
    if "female" in raw:
        return "female"
    if "male" in raw:
        return "male"
    return "unknown"


def extract_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    utterances = result.get("utterances") or result.get("utterance") or payload.get("utterances") or []
    segments: list[dict[str, Any]] = []

    if isinstance(utterances, list):
        for item in utterances:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("utterance") or "").strip()
            if not text:
                continue
            start_ms = item.get("start_time") or item.get("start") or item.get("begin_time") or 0
            end_ms = item.get("end_time") or item.get("end") or item.get("stop_time") or start_ms
            try:
                start_time = float(start_ms) / 1000.0
                end_time = float(end_ms) / 1000.0
            except (TypeError, ValueError):
                start_time = 0.0
                end_time = 0.1
            speaker_info = item.get("speaker_info") if isinstance(item.get("speaker_info"), dict) else {}
            speaker = item.get("speaker") or item.get("speaker_id") or item.get("speaker_label") or speaker_info.get("id")
            gender = item.get("gender") or item.get("speaker_gender") or item.get("gender_label") or speaker_info.get("gender")
            segments.append(
                {
                    "start_time": start_time,
                    "end_time": max(end_time, start_time + 0.1),
                    "text": text,
                    "speaker_label": normalize_speaker_label(speaker),
                    "speaker_gender": normalize_gender(gender),
                }
            )

    if segments:
        return segments

    text = str(result.get("text") or result.get("transcript") or payload.get("text") or "").strip()
    if not text:
        return []
    return [
        {
            "start_time": 0.0,
            "end_time": 0.1,
            "text": text,
            "speaker_label": None,
            "speaker_gender": None,
        }
    ]


@dataclass
class VolcengineRealtimeClient:
    request_id: str
    sequence: int = 1
    websocket: Any = None

    async def connect(self) -> None:
        settings = get_settings()
        api_key = resolve_volcengine_api_key()
        if not api_key:
            raise RealtimeAsrError("VOLCENGINE_ASR_API_KEY is not configured.")

        self.websocket = await websockets.connect(
            settings.volcengine_realtime_asr_url,
            additional_headers={
                "X-Api-Key": api_key,
                "X-Api-Resource-Id": settings.volcengine_realtime_asr_resource_id,
                "X-Api-Request-Id": self.request_id,
            },
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
        )
        await self._send_full_request()

    async def close(self) -> None:
        if self.websocket is not None:
            await self.websocket.close()

    async def _send_full_request(self) -> None:
        settings = get_settings()
        payload = {
            "user": {"uid": "meeting-agent"},
            "audio": {
                "format": "wav",
                "codec": "raw",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "enable_nonstream": False,
                "enable_speaker_info": settings.volcengine_enable_speaker_info,
                "enable_gender_detection": settings.volcengine_enable_gender_detection,
            },
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await self.websocket.send(
            _frame(MessageType.CLIENT_FULL_REQUEST, MessageFlags.POS_SEQUENCE, self.sequence, data)
        )
        self.sequence += 1
        await asyncio.wait_for(self.websocket.recv(), timeout=10)

    async def send_audio(self, chunk: bytes, is_last: bool = False) -> None:
        if self.websocket is None:
            raise RealtimeAsrError("Volcengine realtime ASR is not connected.")
        flags = MessageFlags.NEG_WITH_SEQUENCE if is_last else MessageFlags.POS_SEQUENCE
        sequence = -self.sequence if is_last else self.sequence
        await self.websocket.send(_frame(MessageType.CLIENT_AUDIO_ONLY_REQUEST, flags, sequence, chunk))
        if not is_last:
            self.sequence += 1

    async def receive(self) -> AsyncIterator[dict[str, Any]]:
        if self.websocket is None:
            raise RealtimeAsrError("Volcengine realtime ASR is not connected.")
        async for message in self.websocket:
            if isinstance(message, str):
                continue
            parsed = _parse_frame(message)
            if parsed["code"]:
                raise RealtimeAsrError(f"Volcengine realtime ASR error: {parsed['code']}")
            payload = parsed.get("payload_msg")
            if isinstance(payload, dict):
                yield payload
            if parsed.get("is_last_package"):
                break


def new_realtime_client() -> VolcengineRealtimeClient:
    return VolcengineRealtimeClient(request_id=str(uuid.uuid4()))
