"""Speech-to-Text (STT) providers, VAD, and asynchronous transcription worker."""

from teach_a_skill.teaching.stt.local_whisper import LocalWhisperSTTProvider
from teach_a_skill.teaching.stt.mock_provider import MockSTTProvider
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider
from teach_a_skill.teaching.stt.selector import (
    STTTierConfiguration,
    create_tier_stt_provider,
    select_stt_configuration,
)
from teach_a_skill.teaching.stt.vad import EnergyVAD
from teach_a_skill.teaching.stt.worker import AsyncTranscriptionWorker, TranscriptionMetrics

__all__ = [
    "ISpeechToTextProvider",
    "EnergyVAD",
    "MockSTTProvider",
    "LocalWhisperSTTProvider",
    "AsyncTranscriptionWorker",
    "TranscriptionMetrics",
    "STTTierConfiguration",
    "select_stt_configuration",
    "create_tier_stt_provider",
]
