"""Local Whisper STT provider supporting offline execution via local binary or python runtime."""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider
from teach_a_skill.teaching.transcript.segment import TranscriptSegment

logger = get_logger("teach_a_skill.teaching.stt.whisper")


class LocalWhisperSTTProvider(ISpeechToTextProvider):
    """Local, offline Whisper provider executing on host CPU or accelerator.

    Zero network access or cloud API calls.
    """

    def __init__(
        self,
        model_id: str = "whisper-tiny-local",
        binary_path: Optional[str] = None,
        model_path: Optional[Path] = None,
    ) -> None:
        self._model_id = model_id
        self.binary_path = (
            binary_path
            or shutil.which("whisper")
            or shutil.which("whisper-cli")
            or shutil.which("main")
        )
        self.model_path = model_path
        self._is_loaded = False

    @property
    def provider_id(self) -> str:
        return "local-whisper"

    @property
    def model_id(self) -> str:
        return self._model_id

    def _resolve_model_file(self) -> Optional[Path]:
        """Verify presence of local model weights to prevent unauthorized network downloads."""
        if self.model_path is not None:
            return self.model_path if self.model_path.is_file() else None

        clean_name = self._model_id.replace("whisper-", "").replace("-local", "")
        candidates = [
            Path.home() / ".cache" / "whisper" / f"{clean_name}.pt",
            Path.home() / ".cache" / "teach_a_skill" / "models" / f"{clean_name}.pt",
            Path.home() / ".cache" / "teach_a_skill" / "models" / f"{clean_name}.bin",
            Path.cwd() / "models" / f"{clean_name}.pt",
            Path.cwd() / "models" / f"{clean_name}.bin",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def is_available(self) -> bool:
        """Available only if a local binary is found and local model weights are present."""
        has_binary = self.binary_path is not None and shutil.which(self.binary_path) is not None
        has_model = self._resolve_model_file() is not None
        return bool(has_binary and has_model)

    def load(self) -> None:
        """Verify binary and local model readiness."""
        if not self.is_available():
            logger.info(
                f"Local Whisper binary or offline model weights for '{self._model_id}' not found locally. "
                "Automatic network download is blocked to maintain privacy and offline operation."
            )
            return
        self._is_loaded = True

    def unload(self) -> None:
        self._is_loaded = False

    def transcribe(
        self, chunk: AudioChunk, language: Optional[str] = None
    ) -> list[TranscriptSegment]:
        if not self.is_available():
            logger.warning(
                f"Local Whisper backend or weights for '{self._model_id}' unavailable locally. "
                "Skipping transcription without internet fallback."
            )
            return []

        # If binary and model are available, run local CLI transcription
        import tempfile

        from teach_a_skill.teaching.audio.wav import write_wav_file_atomic

        model_file = self._resolve_model_file()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_wav = Path(tmp_dir) / f"{chunk.chunk_id}.wav"
            write_wav_file_atomic(
                tmp_wav, chunk.raw_pcm, chunk.sample_rate, chunk.channels, chunk.sample_width
            )

            lang = language or "en"
            cmd = [
                self.binary_path,  # type: ignore[list-item]
                str(tmp_wav),
                "--language",
                lang,
                "--output_format",
                "json",
                "--output_dir",
                str(tmp_dir),
            ]
            if model_file:
                cmd.extend(["--model", str(model_file)])

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
                if res.returncode != 0:
                    logger.error(f"Whisper process returned error: {res.stderr}")
                    return []

                json_output_path = Path(tmp_dir) / f"{chunk.chunk_id}.json"
                if json_output_path.exists():
                    with open(json_output_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    segments: list[TranscriptSegment] = []
                    now_wall = datetime.now(timezone.utc).isoformat()
                    raw_segments = data.get("segments", [])

                    for idx, raw_seg in enumerate(raw_segments):
                        start_offset_s = float(raw_seg.get("start", 0.0))
                        end_offset_s = float(raw_seg.get("end", 0.0))
                        seg_start_ns = chunk.start_monotonic_ns + int(
                            start_offset_s * 1_000_000_000
                        )
                        seg_end_ns = chunk.start_monotonic_ns + int(end_offset_s * 1_000_000_000)

                        segments.append(
                            TranscriptSegment(
                                segment_id=f"seg_{chunk.sequence_number:04d}_{idx:02d}",
                                teaching_session_id=chunk.teaching_session_id,
                                sequence_number=chunk.sequence_number,
                                start_monotonic_ns=seg_start_ns,
                                end_monotonic_ns=seg_end_ns,
                                start_wall_time=chunk.start_wall_time or now_wall,
                                end_wall_time=chunk.end_wall_time or now_wall,
                                text=raw_seg.get("text", "").strip(),
                                language=data.get("language", lang),
                                confidence=None,
                                source="local_whisper",
                                audio_chunk_ids=[chunk.chunk_id],
                                revision=1,
                            )
                        )
                    return segments
            except Exception as e:
                logger.error(f"Failed to execute local Whisper: {e}")
                return []

        return []

    def supported_languages(self) -> list[str]:
        return ["en", "es", "fr", "de", "hi", "it", "ja", "ko", "pt", "ru", "zh"]

    def supports_timestamps(self) -> bool:
        return True

    def supports_confidence(self) -> bool:
        return False

    def estimated_memory_mb(self) -> int:
        if "tiny" in self._model_id:
            return 150
        elif "base" in self._model_id:
            return 250
        return 600
