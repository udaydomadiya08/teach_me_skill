"""Transcript segment and revision models for local speech-to-text evidence."""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class TranscriptSegment:
    """Strongly structured, timestamped transcript segment."""

    segment_id: str
    teaching_session_id: str
    sequence_number: int
    start_monotonic_ns: int
    end_monotonic_ns: int
    start_wall_time: str
    end_wall_time: str
    text: str
    language: str = "en"
    confidence: Optional[float] = None
    source: str = "local_stt"
    audio_chunk_ids: list[str] = field(default_factory=list)
    revision: int = 1
    is_active: bool = True
    edited_at: Optional[str] = None
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptSegment":
        return cls(
            segment_id=data["segment_id"],
            teaching_session_id=data["teaching_session_id"],
            sequence_number=data["sequence_number"],
            start_monotonic_ns=int(data["start_monotonic_ns"]),
            end_monotonic_ns=int(data["end_monotonic_ns"]),
            start_wall_time=data["start_wall_time"],
            end_wall_time=data["end_wall_time"],
            text=data["text"],
            language=data.get("language", "en"),
            confidence=data.get("confidence"),
            source=data.get("source", "local_stt"),
            audio_chunk_ids=data.get("audio_chunk_ids", []),
            revision=data.get("revision", 1),
            is_active=data.get("is_active", True),
            edited_at=data.get("edited_at"),
            schema_version=data.get("schema_version", "1.0"),
        )


@dataclass
class TranscriptCorrection:
    """Audit log entry recording an edit, correction, or split to a transcript segment."""

    correction_id: str
    teaching_session_id: str
    segment_id: str
    previous_text: str
    new_text: str
    revision: int
    timestamp: str  # ISO 8601 UTC
    monotonic_timestamp_ns: int
    action: str = "edit"  # "edit", "split", "merge", "hide"
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptCorrection":
        return cls(
            correction_id=data["correction_id"],
            teaching_session_id=data["teaching_session_id"],
            segment_id=data["segment_id"],
            previous_text=data["previous_text"],
            new_text=data["new_text"],
            revision=int(data["revision"]),
            timestamp=data["timestamp"],
            monotonic_timestamp_ns=int(data["monotonic_timestamp_ns"]),
            action=data.get("action", "edit"),
            reason=data.get("reason"),
        )
