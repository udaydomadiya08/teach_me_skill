"""Speech and voice transcription interface (Phase 3 contract)."""

from abc import ABC, abstractmethod
from typing import Any


class ISpeechEngine(ABC):
    """Local speech transcription and voice explanation interface."""

    @abstractmethod
    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> dict[str, Any]:
        """Transcribe speech audio into timestamped text tokens."""
        pass
