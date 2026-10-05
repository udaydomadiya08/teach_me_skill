"""Pure Python standard-library WAV chunk encoder, decoder, and metadata structures."""

import hashlib
import io
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from teach_a_skill.core.errors import StorageError


@dataclass
class AudioChunk:
    """Metadata and raw PCM payload for an immutable audio segment."""

    chunk_id: str
    teaching_session_id: str
    sequence_number: int
    start_monotonic_ns: int
    end_monotonic_ns: int
    start_wall_time: str  # ISO 8601 UTC
    end_wall_time: str  # ISO 8601 UTC
    duration_ms: float
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit PCM
    sha256: str = ""
    size_bytes: int = 0
    raw_pcm: bytes = b""

    def to_metadata_dict(self) -> dict[str, Any]:
        """Return serializable metadata descriptor excluding raw audio bytes."""
        d = asdict(self)
        d.pop("raw_pcm", None)
        return d


def encode_pcm_to_wav_bytes(
    raw_pcm: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Encode raw PCM bytes into a compliant RIFF/WAVE byte stream."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(raw_pcm)
    return buffer.getvalue()


def decode_wav_file(path: Path) -> tuple[bytes, int, int, int]:
    """Read a WAV file and return (raw_pcm, sample_rate, channels, sample_width)."""
    if not path.exists():
        raise StorageError(f"WAV file not found: {path}")
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        raw_pcm = wav_file.readframes(wav_file.getnframes())
    return raw_pcm, sample_rate, channels, sample_width


def write_wav_file_atomic(
    target_path: Path,
    raw_pcm: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> tuple[str, int]:
    """Atomically write raw PCM as a standard WAV file.

    Returns (sha256_hex, file_size_bytes).
    """
    wav_bytes = encode_pcm_to_wav_bytes(raw_pcm, sample_rate, channels, sample_width)
    sha256_hash = hashlib.sha256(wav_bytes).hexdigest()
    file_size = len(wav_bytes)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        f.write(wav_bytes)
        f.flush()
    tmp_path.replace(target_path)

    return sha256_hash, file_size
