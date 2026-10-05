"""Speech-to-Text provider abstraction and capabilities."""

from abc import ABC, abstractmethod
from typing import Optional

from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


class ISpeechToTextProvider(ABC):
    """Abstract interface for local speech-to-text transcription engines."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Identifier for the transcription engine (e.g. 'mock-stt', 'whisper-local')."""
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Registered model ID from ModelRegistry."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the backend runtime and model are available locally."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Initialize and allocate model resources into memory."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Release allocated model resources and free memory."""
        pass

    @abstractmethod
    def transcribe(
        self, chunk: AudioChunk, language: Optional[str] = None
    ) -> list[TranscriptSegment]:
        """Transcribe an AudioChunk into timestamped TranscriptSegments."""
        pass

    @abstractmethod
    def supported_languages(self) -> list[str]:
        """List of supported ISO-639-1 language codes."""
        pass

    @abstractmethod
    def supports_timestamps(self) -> bool:
        """True if the provider returns word- or phrase-level timestamps."""
        pass

    @abstractmethod
    def supports_confidence(self) -> bool:
        """True if the provider returns segment confidence scores."""
        pass

    @abstractmethod
    def estimated_memory_mb(self) -> int:
        """Estimated resident memory in megabytes when loaded."""
        pass
