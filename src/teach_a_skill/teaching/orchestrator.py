"""Teaching orchestrator coordinating audio capture, STT, annotations, and timeline fusion."""

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from teach_a_skill.core.errors import PrivacyViolationError, StorageError
from teach_a_skill.core.logging import get_logger
from teach_a_skill.hardware.budget import ResourceBudget
from teach_a_skill.models.registry import ModelRegistry
from teach_a_skill.privacy.guard import PrivacyGuard
from teach_a_skill.recorder.storage import SessionStorage
from teach_a_skill.storage.manager import StorageManager
from teach_a_skill.teaching.annotations.model import AnnotationType, TeachingAnnotation, TextNote
from teach_a_skill.teaching.audio.capture import AudioCaptureEngine
from teach_a_skill.teaching.audio.sources import (
    BaseAudioSource,
    SyntheticAudioSource,
)
from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.session import TeachingSession, TeachingState
from teach_a_skill.teaching.storage import TeachingStorage
from teach_a_skill.teaching.stt.mock_provider import MockSTTProvider
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider
from teach_a_skill.teaching.stt.worker import AsyncTranscriptionWorker
from teach_a_skill.teaching.timeline.engine import TeachingTimelineEngine
from teach_a_skill.teaching.transcript.editor import TranscriptEditor
from teach_a_skill.teaching.transcript.segment import TranscriptSegment

logger = get_logger("teach_a_skill.teaching.orchestrator")


class TeachingOrchestrator:
    """Coordinates voice teaching, typed annotations, local STT, and cross-timeline synchronization."""

    def __init__(
        self,
        storage_manager: StorageManager,
        privacy_guard: Optional[PrivacyGuard] = None,
        model_registry: Optional[ModelRegistry] = None,
        resource_budget: Optional[ResourceBudget] = None,
        stt_provider: Optional[ISpeechToTextProvider] = None,
        audio_source: Optional[BaseAudioSource] = None,
        language: str = "en",
        enable_audio: bool = True,
        enable_transcription: bool = True,
    ) -> None:
        self.storage_manager = storage_manager
        self.privacy_guard = privacy_guard
        self.model_registry = model_registry or ModelRegistry()
        self.resource_budget = resource_budget
        self.stt_provider = stt_provider or MockSTTProvider()
        self.audio_source = audio_source
        self.language = language
        self.enable_audio = enable_audio
        self.enable_transcription = enable_transcription

        self._session: Optional[TeachingSession] = None
        self._storage: Optional[TeachingStorage] = None
        self._audio_capture: Optional[AudioCaptureEngine] = None
        self._stt_worker: Optional[AsyncTranscriptionWorker] = None
        self._editor: Optional[TranscriptEditor] = None

        self._lock = threading.Lock()
        self._current_sequence = 0

    @property
    def is_teaching(self) -> bool:
        return self._session is not None and self._session.state == TeachingState.RECORDING

    @property
    def is_paused(self) -> bool:
        return self._session is not None and self._session.state == TeachingState.PAUSED

    @property
    def current_session(self) -> Optional[TeachingSession]:
        return self._session

    def start_teaching(
        self,
        recording_session_id: str,
        teaching_session_id: Optional[str] = None,
        use_synthetic_audio: bool = False,
    ) -> str:
        """Start a synchronized teaching session alongside an existing or active recording session."""
        with self._lock:
            # Privacy check
            if self.enable_audio and self.privacy_guard:
                # If privacy guard has microphone access disabled, fail or log
                try:
                    self.privacy_guard.assert_microphone_allowed()
                except PrivacyViolationError as e:
                    logger.warning(f"Microphone access blocked by privacy guard: {e}")
                    raise

            ts_id = teaching_session_id or f"teach_{uuid.uuid4().hex[:10]}"
            self._session = TeachingSession(
                teaching_session_id=ts_id,
                recording_session_id=recording_session_id,
                audio_enabled=self.enable_audio,
                transcription_enabled=self.enable_transcription,
                language=self.language,
                stt_provider_id=self.stt_provider.provider_id,
                stt_model_id=self.stt_provider.model_id,
            )

            self._storage = TeachingStorage(self.storage_manager, recording_session_id)
            self._storage.initialize_teaching_layout(self._session.manifest)
            self._editor = TranscriptEditor(self._storage.transcript_store)

            # Start asynchronous STT worker if enabled
            if self.enable_transcription:
                self._stt_worker = AsyncTranscriptionWorker(
                    provider=self.stt_provider,
                    on_segments_ready=self._on_transcript_segments_ready,
                    preferred_language=self.language,
                )
                self._stt_worker.start()

            # Start audio capture if enabled
            if self.enable_audio:
                if use_synthetic_audio or self.audio_source is None:
                    src = SyntheticAudioSource(teaching_session_id=ts_id, chunk_duration_sec=2.0)
                else:
                    src = self.audio_source

                self._audio_capture = AudioCaptureEngine(
                    teaching_session_id=ts_id,
                    audio_dir=self._storage.audio_dir,
                    source=src,
                    on_chunk_persisted=self._on_audio_chunk_persisted,
                )
                self._audio_capture.start()

            self._session.transition_to(TeachingState.RECORDING)
            logger.info(
                f"MIC: RECORDING | Teaching session {ts_id} active for recording {recording_session_id}"
            )
            return ts_id

    def pause_teaching(self) -> None:
        """Suspend teaching and pause audio capture."""
        with self._lock:
            if not self.is_teaching or not self._session:
                return
            self._session.transition_to(TeachingState.PAUSED)
            if self._audio_capture:
                self._audio_capture.pause()
            logger.info(
                f"MIC: PAUSED | Teaching session {self._session.teaching_session_id} paused"
            )

    def resume_teaching(self) -> None:
        """Resume active teaching and audio capture."""
        with self._lock:
            if not self.is_paused or not self._session:
                return
            self._session.transition_to(TeachingState.RECORDING)
            if self._audio_capture:
                self._audio_capture.resume()
            logger.info(
                f"MIC: RECORDING | Teaching session {self._session.teaching_session_id} resumed"
            )

    def stop_teaching(self) -> str:
        """Stop teaching session, finalize audio, drain transcription queue, and compute checksums."""
        with self._lock:
            if not self._session:
                raise StorageError("No active teaching session to stop.")

            self._session.transition_to(TeachingState.STOPPING)

            # 1. Stop audio capture and drain chunks
            if self._audio_capture:
                self._audio_capture.stop()
                self._audio_capture = None

            # 2. Stop and drain STT worker
            if self._stt_worker:
                self._stt_worker.stop()
                metrics = self._stt_worker.metrics
                self._session.update_stt_performance(
                    processing_time_sec=metrics.transcription_time_sec,
                    rtf=metrics.real_time_factor,
                )
                self._stt_worker = None

            self._session.transition_to(TeachingState.COMPLETED)

            # 3. Finalize storage and checksums
            if self._storage:
                self._storage.finalize_teaching_session(self._session.manifest)
                teaching_path = str(self._storage.teaching_dir)
            else:
                teaching_path = ""

            logger.info(
                f"MIC: STOPPED | Teaching session {self._session.teaching_session_id} completed"
            )
            return teaching_path

    def cancel_teaching(self) -> str:
        """Cancel teaching session and mark status ABORTED."""
        with self._lock:
            if not self._session:
                raise StorageError("No active teaching session to cancel.")

            if self._audio_capture:
                self._audio_capture.cancel()
                self._audio_capture = None

            if self._stt_worker:
                self._stt_worker.stop()
                self._stt_worker = None

            self._session.transition_to(TeachingState.ABORTED)
            if self._storage:
                self._storage.finalize_teaching_session(self._session.manifest)
                teaching_path = str(self._storage.teaching_dir)
            else:
                teaching_path = ""

            logger.warning(
                f"MIC: STOPPED | Teaching session {self._session.teaching_session_id} ABORTED"
            )
            return teaching_path

    def add_annotation(
        self,
        text: str,
        annotation_type: AnnotationType = AnnotationType.INSTRUCTION,
        start_mono_ns: Optional[int] = None,
        end_mono_ns: Optional[int] = None,
        event_ids: Optional[list[str]] = None,
        frame_ids: Optional[list[str]] = None,
    ) -> TeachingAnnotation:
        """Attach a structured text annotation to a timeline moment or event range."""
        if not self._session or not self._storage:
            raise StorageError("Cannot add annotation: no active teaching session.")

        now_mono = time.monotonic_ns()
        s_mono = start_mono_ns or now_mono
        e_mono = end_mono_ns or s_mono

        ann = TeachingAnnotation(
            annotation_id=f"ann_{uuid.uuid4().hex[:10]}",
            teaching_session_id=self._session.teaching_session_id,
            created_monotonic_ns=now_mono,
            start_monotonic_ns=s_mono,
            end_monotonic_ns=e_mono,
            text=text,
            type=annotation_type,
            author="user",
            revision=1,
            is_active=True,
            references={
                "event_ids": event_ids or [],
                "frame_ids": frame_ids or [],
            },
        )

        self._storage.annotation_store.append_annotation(ann)
        self._session.record_annotation_metric(1)
        logger.info(f"Recorded teaching annotation: '{text[:30]}...' ({annotation_type})")
        return ann

    def add_note(self, text: str) -> TextNote:
        """Add an unstructured text note timestamped to the current moment."""
        if not self._session or not self._storage:
            raise StorageError("Cannot add note: no active teaching session.")

        note = TextNote(
            note_id=f"note_{uuid.uuid4().hex[:10]}",
            teaching_session_id=self._session.teaching_session_id,
            timestamp_monotonic_ns=time.monotonic_ns(),
            wall_time=datetime.now(timezone.utc).isoformat(),
            text=text,
        )

        self._storage.annotation_store.append_note(note)
        self._session.record_note_metric(1)
        return note

    def get_editor(self) -> TranscriptEditor:
        """Return the transcript editor for the active session."""
        if not self._editor:
            raise StorageError("Transcript editor not initialized.")
        return self._editor

    def build_timeline_engine(self, recording_session_id: str) -> TeachingTimelineEngine:
        """Load Phase 2 raw evidence and Phase 3 teaching artifacts, constructing a queryable timeline."""
        # 1. Load Phase 2 raw events and frames
        raw_storage = SessionStorage(self.storage_manager, recording_session_id)
        raw_events = raw_storage.read_all_events()

        frame_idx_file = raw_storage.metadata_dir / "frame_index.json"
        frame_idx: dict[str, Any] = {}
        if frame_idx_file.exists():
            frame_idx = raw_storage.storage_manager.read_metadata(frame_idx_file)

        # 2. Load Phase 3 teaching artifacts
        teaching_storage = TeachingStorage(self.storage_manager, recording_session_id)
        transcripts = teaching_storage.transcript_store.read_all_segments(only_active=True)
        annotations = teaching_storage.annotation_store.read_all_annotations(only_active=True)

        return TeachingTimelineEngine(
            events=raw_events,
            transcript_segments=transcripts,
            annotations=annotations,
            frame_index=frame_idx,
        )

    def _on_audio_chunk_persisted(self, chunk: AudioChunk) -> None:
        """Callback triggered when an audio chunk is written to disk."""
        if self._session:
            self._session.record_audio_chunk_metric(chunk.duration_ms / 1000.0)

        # Enqueue chunk for asynchronous STT processing
        if self.enable_transcription and self._stt_worker:
            self._stt_worker.enqueue_chunk(chunk)

    def _on_transcript_segments_ready(self, segments: list[TranscriptSegment]) -> None:
        """Callback from STT worker when segments are transcribed."""
        if self._storage:
            self._storage.transcript_store.append_segments(segments)
        if self._session:
            self._session.record_transcript_segment_metric(len(segments))
