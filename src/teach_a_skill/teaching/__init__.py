"""Phase 3: Local Voice + Text Teaching Layer for Teach A Skill."""

from teach_a_skill.teaching.annotations import (
    AnnotationType,
    TeachingAnnotation,
    TeachingAnnotationStore,
    TextNote,
)
from teach_a_skill.teaching.audio import (
    AudioBackend,
    AudioBufferMetrics,
    AudioCaptureEngine,
    AudioCaptureState,
    AudioChunk,
    AudioDevice,
    AudioPermissionManager,
    AudioPermissionStatus,
    BaseAudioSource,
    BoundedAudioBuffer,
    SyntheticAudioSource,
    SystemAudioSource,
)
from teach_a_skill.teaching.orchestrator import TeachingOrchestrator
from teach_a_skill.teaching.session import TeachingManifest, TeachingSession, TeachingState
from teach_a_skill.teaching.storage import TeachingStorage
from teach_a_skill.teaching.stt import (
    AsyncTranscriptionWorker,
    EnergyVAD,
    ISpeechToTextProvider,
    LocalWhisperSTTProvider,
    MockSTTProvider,
    TranscriptionMetrics,
)
from teach_a_skill.teaching.timeline import TeachingTimelineEngine, TimelineContext
from teach_a_skill.teaching.transcript import (
    TranscriptCorrection,
    TranscriptEditor,
    TranscriptSegment,
    TranscriptStore,
)

__all__ = [
    # Audio
    "AudioChunk",
    "AudioDevice",
    "AudioBackend",
    "AudioPermissionManager",
    "AudioPermissionStatus",
    "BaseAudioSource",
    "SyntheticAudioSource",
    "SystemAudioSource",
    "BoundedAudioBuffer",
    "AudioBufferMetrics",
    "AudioCaptureState",
    "AudioCaptureEngine",
    # STT
    "ISpeechToTextProvider",
    "EnergyVAD",
    "MockSTTProvider",
    "LocalWhisperSTTProvider",
    "AsyncTranscriptionWorker",
    "TranscriptionMetrics",
    # Transcript
    "TranscriptSegment",
    "TranscriptCorrection",
    "TranscriptStore",
    "TranscriptEditor",
    # Annotations
    "AnnotationType",
    "TeachingAnnotation",
    "TextNote",
    "TeachingAnnotationStore",
    # Timeline
    "TimelineContext",
    "TeachingTimelineEngine",
    # Session & Storage
    "TeachingState",
    "TeachingManifest",
    "TeachingSession",
    "TeachingStorage",
    "TeachingOrchestrator",
]
