"""Teaching session lifecycle state machine and manifest model."""

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from teach_a_skill.core.errors import StorageError
from teach_a_skill.core.logging import get_logger

logger = get_logger("teach_a_skill.teaching.session")


class TeachingState(str, Enum):
    """Formal states for a teaching session."""

    CREATED = "CREATED"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"

    def __str__(self) -> str:
        return self.value


VALID_TEACHING_TRANSITIONS = {
    TeachingState.CREATED: {TeachingState.RECORDING, TeachingState.FAILED, TeachingState.ABORTED},
    TeachingState.RECORDING: {
        TeachingState.PAUSED,
        TeachingState.STOPPING,
        TeachingState.ABORTED,
        TeachingState.FAILED,
    },
    TeachingState.PAUSED: {
        TeachingState.RECORDING,
        TeachingState.STOPPING,
        TeachingState.ABORTED,
        TeachingState.FAILED,
    },
    TeachingState.STOPPING: {TeachingState.COMPLETED, TeachingState.FAILED, TeachingState.ABORTED},
    TeachingState.COMPLETED: set(),
    TeachingState.ABORTED: set(),
    TeachingState.FAILED: set(),
}


@dataclass
class TeachingManifest:
    """Strongly structured, versioned teaching session manifest."""

    teaching_session_id: str
    recording_session_id: str
    status: TeachingState = TeachingState.CREATED
    audio_enabled: bool = True
    transcription_enabled: bool = True
    text_annotations_enabled: bool = True
    language: str = "en"
    audio_chunks: int = 0
    transcript_segments: int = 0
    annotations: int = 0
    text_notes: int = 0
    total_audio_duration_sec: float = 0.0
    stt_processing_time_sec: float = 0.0
    stt_real_time_factor: float = 0.0
    stt_provider_id: str = "mock-stt"
    stt_model_id: str = "whisper-tiny-local"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeachingManifest":
        status_val = data.get("status", "CREATED")
        try:
            status_enum = TeachingState(status_val)
        except ValueError:
            status_enum = TeachingState.CREATED

        return cls(
            teaching_session_id=data["teaching_session_id"],
            recording_session_id=data["recording_session_id"],
            status=status_enum,
            audio_enabled=data.get("audio_enabled", True),
            transcription_enabled=data.get("transcription_enabled", True),
            text_annotations_enabled=data.get("text_annotations_enabled", True),
            language=data.get("language", "en"),
            audio_chunks=int(data.get("audio_chunks", 0)),
            transcript_segments=int(data.get("transcript_segments", 0)),
            annotations=int(data.get("annotations", 0)),
            text_notes=int(data.get("text_notes", 0)),
            total_audio_duration_sec=float(data.get("total_audio_duration_sec", 0.0)),
            stt_processing_time_sec=float(data.get("stt_processing_time_sec", 0.0)),
            stt_real_time_factor=float(data.get("stt_real_time_factor", 0.0)),
            stt_provider_id=data.get("stt_provider_id", "mock-stt"),
            stt_model_id=data.get("stt_model_id", "whisper-tiny-local"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            schema_version=data.get("schema_version", "1.0"),
        )


class TeachingSession:
    """Manages state transitions and metrics aggregation for a teaching session."""

    def __init__(
        self,
        teaching_session_id: str,
        recording_session_id: str,
        audio_enabled: bool = True,
        transcription_enabled: bool = True,
        language: str = "en",
        stt_provider_id: str = "mock-stt",
        stt_model_id: str = "whisper-tiny-local",
    ) -> None:
        self.manifest = TeachingManifest(
            teaching_session_id=teaching_session_id,
            recording_session_id=recording_session_id,
            audio_enabled=audio_enabled,
            transcription_enabled=transcription_enabled,
            language=language,
            stt_provider_id=stt_provider_id,
            stt_model_id=stt_model_id,
        )
        self.state = TeachingState.CREATED
        self._start_mono: Optional[float] = None
        self._pause_mono: Optional[float] = None
        self._total_paused_duration: float = 0.0

    @property
    def teaching_session_id(self) -> str:
        return self.manifest.teaching_session_id

    @property
    def recording_session_id(self) -> str:
        return self.manifest.recording_session_id

    def transition_to(self, new_state: TeachingState) -> None:
        """Enforces legal state transitions."""
        allowed = VALID_TEACHING_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise StorageError(
                f"Invalid teaching state transition from {self.state} to {new_state}. "
                f"Allowed target states: {[s.value for s in allowed]}"
            )

        now_mono = time.monotonic()
        now_utc = datetime.now(timezone.utc).isoformat()

        if new_state == TeachingState.RECORDING:
            if self.state == TeachingState.CREATED:
                self._start_mono = now_mono
            elif self.state == TeachingState.PAUSED and self._pause_mono is not None:
                self._total_paused_duration += now_mono - self._pause_mono
                self._pause_mono = None
        elif new_state == TeachingState.PAUSED:
            self._pause_mono = now_mono

        self.state = new_state
        self.manifest.status = new_state
        self.manifest.updated_at = now_utc
        logger.info(f"Teaching session {self.teaching_session_id} transitioned to: {new_state}")

    def record_audio_chunk_metric(self, duration_sec: float) -> None:
        self.manifest.audio_chunks += 1
        self.manifest.total_audio_duration_sec += duration_sec
        self.manifest.updated_at = datetime.now(timezone.utc).isoformat()

    def record_transcript_segment_metric(self, count: int = 1) -> None:
        self.manifest.transcript_segments += count
        self.manifest.updated_at = datetime.now(timezone.utc).isoformat()

    def record_annotation_metric(self, count: int = 1) -> None:
        self.manifest.annotations += count
        self.manifest.updated_at = datetime.now(timezone.utc).isoformat()

    def record_note_metric(self, count: int = 1) -> None:
        self.manifest.text_notes += count
        self.manifest.updated_at = datetime.now(timezone.utc).isoformat()

    def update_stt_performance(self, processing_time_sec: float, rtf: float) -> None:
        self.manifest.stt_processing_time_sec += processing_time_sec
        self.manifest.stt_real_time_factor = rtf
        self.manifest.updated_at = datetime.now(timezone.utc).isoformat()
