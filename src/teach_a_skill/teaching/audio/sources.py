"""Audio stream sources: abstract interface, synthetic generator, and OS microphone capture."""

import math
import shutil
import struct
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.audio.wav import AudioChunk

logger = get_logger("teach_a_skill.teaching.audio.sources")


class BaseAudioSource(ABC):
    """Abstract interface for audio capture sources."""

    @abstractmethod
    def start(self, on_chunk_ready: Callable[[AudioChunk], None]) -> None:
        """Begin audio capture and deliver completed AudioChunks to callback."""
        pass

    @abstractmethod
    def pause(self) -> None:
        """Temporarily suspend audio capture."""
        pass

    @abstractmethod
    def resume(self) -> None:
        """Resume suspended audio capture."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Halt audio capture and release resources."""
        pass

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Returns True if the source is actively recording."""
        pass


class SyntheticAudioSource(BaseAudioSource):
    """Deterministic synthetic audio source producing 16 kHz 16-bit mono PCM chunks.

    Ideal for CI testing, benchmarks, and offline reproducible verification.
    """

    def __init__(
        self,
        teaching_session_id: str,
        chunk_duration_sec: float = 2.0,
        sample_rate: int = 16000,
        frequency_hz: float = 440.0,
        total_chunks: Optional[int] = None,
        simulate_speech_intervals: bool = True,
    ) -> None:
        self.teaching_session_id = teaching_session_id
        self.chunk_duration_sec = chunk_duration_sec
        self.sample_rate = sample_rate
        self.frequency_hz = frequency_hz
        self.total_chunks = total_chunks
        self.simulate_speech_intervals = simulate_speech_intervals

        self._is_active = False
        self._is_paused = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._chunk_sequence = 0

    @property
    def is_active(self) -> bool:
        return self._is_active

    def start(self, on_chunk_ready: Callable[[AudioChunk], None]) -> None:
        self._is_active = True
        self._is_paused = False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(on_chunk_ready,),
            daemon=True,
            name="SyntheticAudioSourceThread",
        )
        self._thread.start()
        logger.info(f"Synthetic audio source started for session {self.teaching_session_id}")

    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    def stop(self) -> None:
        self._is_active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"Synthetic audio source stopped for session {self.teaching_session_id}")

    def generate_pcm_chunk(self, duration_sec: float, is_speech: bool = True) -> bytes:
        """Generate raw 16-bit mono PCM samples."""
        num_samples = int(self.sample_rate * duration_sec)
        samples = []
        amplitude = 12000.0 if is_speech else 0.0

        for i in range(num_samples):
            if is_speech:
                val = int(
                    amplitude * math.sin(2.0 * math.pi * self.frequency_hz * (i / self.sample_rate))
                )
            else:
                val = 0
            samples.append(struct.pack("<h", max(-32768, min(32767, val))))

        return b"".join(samples)

    def _run_loop(self, on_chunk_ready: Callable[[AudioChunk], None]) -> None:
        while not self._stop_event.is_set():
            if self.total_chunks is not None and self._chunk_sequence >= self.total_chunks:
                break

            if self._is_paused:
                time.sleep(0.05)
                continue

            t_start_mono = time.monotonic_ns()
            t_start_wall = datetime.now(timezone.utc).isoformat()

            # Simulate interval in fast slices
            step_duration = min(self.chunk_duration_sec, 0.1)
            time.sleep(step_duration)

            if self._stop_event.is_set() or self._is_paused:
                continue

            t_end_mono = time.monotonic_ns()
            t_end_wall = datetime.now(timezone.utc).isoformat()
            duration_ms = (t_end_mono - t_start_mono) / 1_000_000.0

            # Alternate speech and silence if simulated intervals
            is_speech = True
            if self.simulate_speech_intervals and (self._chunk_sequence % 3 == 2):
                is_speech = False

            raw_pcm = self.generate_pcm_chunk(self.chunk_duration_sec, is_speech=is_speech)
            self._chunk_sequence += 1

            chunk = AudioChunk(
                chunk_id=f"audio_{self._chunk_sequence:06d}",
                teaching_session_id=self.teaching_session_id,
                sequence_number=self._chunk_sequence,
                start_monotonic_ns=t_start_mono,
                end_monotonic_ns=t_end_mono,
                start_wall_time=t_start_wall,
                end_wall_time=t_end_wall,
                duration_ms=duration_ms,
                sample_rate=self.sample_rate,
                channels=1,
                sample_width=2,
                raw_pcm=raw_pcm,
                size_bytes=len(raw_pcm),
            )

            try:
                on_chunk_ready(chunk)
            except Exception as e:
                logger.error(f"Error dispatching synthetic audio chunk: {e}")


class SystemAudioSource(BaseAudioSource):
    """Microphone audio capture utilizing ffmpeg (or OS native utility) to stream 16 kHz mono PCM."""

    def __init__(
        self,
        teaching_session_id: str,
        device_id: str = ":0",
        chunk_duration_sec: float = 10.0,
        sample_rate: int = 16000,
    ) -> None:
        self.teaching_session_id = teaching_session_id
        self.device_id = device_id
        self.chunk_duration_sec = chunk_duration_sec
        self.sample_rate = sample_rate

        self._is_active = False
        self._is_paused = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._chunk_sequence = 0
        self._process: Optional[subprocess.Popen] = None

    @property
    def is_active(self) -> bool:
        return self._is_active

    def start(self, on_chunk_ready: Callable[[AudioChunk], None]) -> None:
        self._is_active = True
        self._is_paused = False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_worker,
            args=(on_chunk_ready,),
            daemon=True,
            name="SystemAudioCaptureThread",
        )
        self._thread.start()
        logger.info(f"System audio capture started for session {self.teaching_session_id}")

    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    def stop(self) -> None:
        self._is_active = False
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.5)
            except Exception:
                self._process.kill()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"System audio capture stopped for session {self.teaching_session_id}")

    def _capture_worker(self, on_chunk_ready: Callable[[AudioChunk], None]) -> None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            logger.warning(
                "ffmpeg not found for live audio capture. Falling back to synthetic source."
            )
            synth = SyntheticAudioSource(
                self.teaching_session_id, chunk_duration_sec=self.chunk_duration_sec
            )
            synth.start(on_chunk_ready)
            while not self._stop_event.is_set():
                time.sleep(0.1)
            synth.stop()
            return

        # 16-bit mono 16 kHz raw PCM: 16000 * 2 = 32000 bytes/sec
        bytes_per_second = self.sample_rate * 2
        chunk_target_bytes = int(bytes_per_second * self.chunk_duration_sec)

        cmd = [
            ffmpeg_bin,
            "-f",
            "avfoundation",
            "-i",
            self.device_id,
            "-ar",
            str(self.sample_rate),
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=chunk_target_bytes,
            )
        except Exception as e:
            logger.error(f"Failed to launch system audio capture: {e}")
            return

        current_buffer = bytearray()
        t_start_mono = time.monotonic_ns()
        t_start_wall = datetime.now(timezone.utc).isoformat()

        while not self._stop_event.is_set() and self._process.poll() is None:
            if self._is_paused:
                time.sleep(0.05)
                continue

            # Read up to 4096 bytes
            data = self._process.stdout.read(4096) if self._process.stdout else None
            if not data:
                time.sleep(0.01)
                continue

            current_buffer.extend(data)

            if len(current_buffer) >= chunk_target_bytes:
                t_end_mono = time.monotonic_ns()
                t_end_wall = datetime.now(timezone.utc).isoformat()
                duration_ms = (t_end_mono - t_start_mono) / 1_000_000.0

                self._chunk_sequence += 1
                pcm_bytes = bytes(current_buffer[:chunk_target_bytes])
                current_buffer = current_buffer[chunk_target_bytes:]

                chunk = AudioChunk(
                    chunk_id=f"audio_{self._chunk_sequence:06d}",
                    teaching_session_id=self.teaching_session_id,
                    sequence_number=self._chunk_sequence,
                    start_monotonic_ns=t_start_mono,
                    end_monotonic_ns=t_end_mono,
                    start_wall_time=t_start_wall,
                    end_wall_time=t_end_wall,
                    duration_ms=duration_ms,
                    sample_rate=self.sample_rate,
                    channels=1,
                    sample_width=2,
                    raw_pcm=pcm_bytes,
                    size_bytes=len(pcm_bytes),
                )

                on_chunk_ready(chunk)

                t_start_mono = time.monotonic_ns()
                t_start_wall = datetime.now(timezone.utc).isoformat()

        # Flush residual buffer on stop
        if current_buffer and not self._stop_event.is_set():
            t_end_mono = time.monotonic_ns()
            t_end_wall = datetime.now(timezone.utc).isoformat()
            duration_ms = (t_end_mono - t_start_mono) / 1_000_000.0
            self._chunk_sequence += 1
            chunk = AudioChunk(
                chunk_id=f"audio_{self._chunk_sequence:06d}",
                teaching_session_id=self.teaching_session_id,
                sequence_number=self._chunk_sequence,
                start_monotonic_ns=t_start_mono,
                end_monotonic_ns=t_end_mono,
                start_wall_time=t_start_wall,
                end_wall_time=t_end_wall,
                duration_ms=duration_ms,
                sample_rate=self.sample_rate,
                channels=1,
                sample_width=2,
                raw_pcm=bytes(current_buffer),
                size_bytes=len(current_buffer),
            )
            on_chunk_ready(chunk)
