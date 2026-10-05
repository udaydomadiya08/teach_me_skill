"""Deterministic Mock Speech-to-Text provider for CI, testing, and benchmark simulation."""

import time
from datetime import datetime, timezone
from typing import Optional

from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider
from teach_a_skill.teaching.transcript.segment import TranscriptSegment


class MockSTTProvider(ISpeechToTextProvider):
    """Deterministic, local speech transcriber that does not require external models or network access."""

    SAMPLE_PHRASES = [
        "First, I open the application settings.",
        "Now I click the general preferences tab.",
        "Here I enter the configuration values.",
        "Next, I select the advanced network options.",
        "Finally, I save the changes and close the dialog.",
    ]

    def __init__(
        self,
        model_id: str = "whisper-tiny-local",
        simulated_latency_sec: float = 0.01,
        default_confidence: float = 0.95,
    ) -> None:
        self._model_id = model_id
        self.simulated_latency_sec = simulated_latency_sec
        self.default_confidence = default_confidence
        self._is_loaded = False
        self._phrase_index = 0

    @property
    def provider_id(self) -> str:
        return "mock-stt"

    @property
    def model_id(self) -> str:
        return self._model_id

    def is_available(self) -> bool:
        return True

    def load(self) -> None:
        self._is_loaded = True

    def unload(self) -> None:
        self._is_loaded = False

    def transcribe(
        self, chunk: AudioChunk, language: Optional[str] = None
    ) -> list[TranscriptSegment]:
        if not self._is_loaded:
            self.load()

        if self.simulated_latency_sec > 0:
            time.sleep(self.simulated_latency_sec)

        # Select deterministic phrase
        phrase = self.SAMPLE_PHRASES[self._phrase_index % len(self.SAMPLE_PHRASES)]
        self._phrase_index += 1

        seg_id = f"seg_{chunk.sequence_number:06d}"
        now_wall = datetime.now(timezone.utc).isoformat()

        segment = TranscriptSegment(
            segment_id=seg_id,
            teaching_session_id=chunk.teaching_session_id,
            sequence_number=chunk.sequence_number,
            start_monotonic_ns=chunk.start_monotonic_ns,
            end_monotonic_ns=chunk.end_monotonic_ns,
            start_wall_time=chunk.start_wall_time or now_wall,
            end_wall_time=chunk.end_wall_time or now_wall,
            text=phrase,
            language=language or "en",
            confidence=self.default_confidence,
            source="mock_stt",
            audio_chunk_ids=[chunk.chunk_id],
            revision=1,
            is_active=True,
        )

        return [segment]

    def supported_languages(self) -> list[str]:
        return ["en", "es", "fr", "de", "hi", "ja", "zh"]

    def supports_timestamps(self) -> bool:
        return True

    def supports_confidence(self) -> bool:
        return True

    def estimated_memory_mb(self) -> int:
        return 10  # Minimal memory footprint
