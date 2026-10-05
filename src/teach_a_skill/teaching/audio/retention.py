"""Audio retention policies and storage estimation for teaching demonstration sessions."""

import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from teach_a_skill.core.logging import get_logger

logger = get_logger("teach_a_skill.teaching.audio.retention")


class AudioRetentionMode(str, Enum):
    """Retention policies for raw audio evidence."""

    RETAIN_RAW = "retain_raw"  # Default: keep raw WAV chunks permanently
    RETAIN_UNTIL_TRANSCRIBED = (
        "retain_until_transcribed"  # Delete raw WAV only after STT and hash verification
    )
    RETAIN_AND_COMPRESS_COPY = (
        "retain_and_compress_copy"  # Keep raw WAV, plus optional archival compressed copy
    )

    def __str__(self) -> str:
        return self.value


@dataclass
class AudioRetentionPolicy:
    """Configurable audio retention and archival settings."""

    mode: AudioRetentionMode = AudioRetentionMode.RETAIN_RAW
    archive_format: str = "flac"  # Lossless compressed format ("flac") or speech codec ("opus")
    auto_delete_raw_after_transcription: bool = False


def estimate_audio_storage(
    duration_minutes: float,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width_bytes: int = 2,
    sample_width: Optional[int] = None,
) -> dict[str, Any]:
    """Calculate exact raw PCM storage requirements and compressed estimates based on formula.

    Formula:
        bytes = duration_minutes * 60 * sample_rate * channels * sample_width_bytes
    """
    if sample_width is not None:
        sample_width_bytes = sample_width
    total_seconds = max(0.0, duration_minutes * 60.0)
    bytes_per_second = sample_rate * channels * sample_width_bytes
    raw_bytes = int(total_seconds * bytes_per_second)

    # Standard RIFF header overhead: 44 bytes per chunk (assuming 10s chunks)
    estimated_chunks = max(1, int(total_seconds / 10.0))
    wav_header_bytes = estimated_chunks * 44
    total_raw_bytes = raw_bytes + wav_header_bytes

    raw_mb = total_raw_bytes / (1024 * 1024)
    raw_gb = total_raw_bytes / (1024 * 1024 * 1024)
    mb_per_minute = (bytes_per_second * 60.0) / (1024 * 1024)
    gb_per_hour = (bytes_per_second * 3600.0) / (1024 * 1024 * 1024)

    # Compression estimates based on standard audio codecs:
    # FLAC lossless speech: ~55% of raw PCM
    # Opus speech at 24 kbps: ~10% of raw PCM
    flac_est_mb = raw_mb * 0.55
    opus_est_mb = raw_mb * 0.10

    return {
        "duration_minutes": duration_minutes,
        "duration_seconds": total_seconds,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width_bytes": sample_width_bytes,
        "bytes_per_second": bytes_per_second,
        "mb_per_minute": round(mb_per_minute, 2),
        "gb_per_hour": round(gb_per_hour, 3),
        "total_raw_bytes": total_raw_bytes,
        "total_raw_mb": round(raw_mb, 2),
        "total_raw_gb": round(raw_gb, 4),
        "flac_compressed_est_mb": round(flac_est_mb, 2),
        "opus_compressed_est_mb": round(opus_est_mb, 2),
    }


def compress_audio_chunk_copy(
    raw_wav_path: Path,
    output_dir: Optional[Path] = None,
    codec: str = "flac",
) -> Optional[Path]:
    """Create an optional local compressed copy of a WAV chunk using local ffmpeg if available.

    IMPORTANT: The original raw WAV remains the authoritative evidence.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin or not raw_wav_path.exists():
        return None

    target_dir = output_dir or (raw_wav_path.parent / "compressed")
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = "flac" if codec.lower() == "flac" else "opus"
    target_file = target_dir / f"{raw_wav_path.stem}.{ext}"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(raw_wav_path),
    ]

    if ext == "flac":
        cmd.extend(["-c:a", "flac"])
    else:
        cmd.extend(["-c:a", "libopus", "-b:a", "24k"])

    cmd.append(str(target_file))

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        if res.returncode == 0 and target_file.exists():
            logger.debug(f"Created archival compressed copy: {target_file}")
            return target_file
        else:
            logger.warning(f"ffmpeg compression returned code {res.returncode}: {res.stderr}")
            return None
    except Exception as e:
        logger.warning(f"Failed to create compressed audio copy: {e}")
        return None
