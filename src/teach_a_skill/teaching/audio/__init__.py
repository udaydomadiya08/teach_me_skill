"""Audio capture and hardware abstractions for local teaching demonstrations."""

from teach_a_skill.teaching.audio.buffer import AudioBufferMetrics, BoundedAudioBuffer
from teach_a_skill.teaching.audio.capture import AudioCaptureEngine, AudioCaptureState
from teach_a_skill.teaching.audio.device import AudioBackend, AudioDevice
from teach_a_skill.teaching.audio.permissions import AudioPermissionManager, AudioPermissionStatus
from teach_a_skill.teaching.audio.sources import (
    BaseAudioSource,
    SyntheticAudioSource,
    SystemAudioSource,
)
from teach_a_skill.teaching.audio.wav import (
    AudioChunk,
    decode_wav_file,
    encode_pcm_to_wav_bytes,
    write_wav_file_atomic,
)

__all__ = [
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
    "encode_pcm_to_wav_bytes",
    "decode_wav_file",
    "write_wav_file_atomic",
]
