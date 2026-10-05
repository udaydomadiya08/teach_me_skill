"""Asynchronous background transcription worker managing queueing, backlog metrics, and persistence."""

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.audio.wav import AudioChunk
from teach_a_skill.teaching.stt.provider import ISpeechToTextProvider
from teach_a_skill.teaching.transcript.segment import TranscriptSegment

logger = get_logger("teach_a_skill.teaching.stt.worker")


@dataclass
class TranscriptionMetrics:
    """Metrics tracking asynchronous STT processing and backlog."""

    total_chunks_received: int = 0
    total_chunks_processed: int = 0
    total_segments_produced: int = 0
    audio_duration_sec: float = 0.0
    transcription_time_sec: float = 0.0
    real_time_factor: float = 0.0
    queue_backlog_chunks: int = 0
    queue_backlog_sec: float = 0.0


class AsyncTranscriptionWorker:
    """Background worker processing audio chunks through STT provider without stalling audio capture."""

    def __init__(
        self,
        provider: ISpeechToTextProvider,
        on_segments_ready: Callable[[list[TranscriptSegment]], None],
        max_queue_size: int = 200,
        preferred_language: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.on_segments_ready = on_segments_ready
        self.preferred_language = preferred_language

        self._queue: queue.Queue[Optional[AudioChunk]] = queue.Queue(maxsize=max_queue_size)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.metrics = TranscriptionMetrics()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background transcription thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="AsyncSTTWorkerThread",
        )
        self._thread.start()
        logger.info(f"Async STT worker started with provider '{self.provider.provider_id}'")

    def enqueue_chunk(self, chunk: AudioChunk) -> bool:
        """Enqueue an AudioChunk for transcription."""
        with self._lock:
            self.metrics.total_chunks_received += 1
            self.metrics.audio_duration_sec += chunk.duration_ms / 1000.0

        try:
            self._queue.put_nowait(chunk)
            with self._lock:
                self.metrics.queue_backlog_chunks = self._queue.qsize()
                self.metrics.queue_backlog_sec = self.metrics.queue_backlog_chunks * (
                    chunk.duration_ms / 1000.0
                )
            return True
        except queue.Full:
            logger.warning(
                "Transcription backlog queue full! Audio capture is unaffected, STT will catch up."
            )
            return False

    def stop(self, timeout: float = 5.0) -> None:
        """Stop worker, allowing in-flight chunks to drain."""
        self._queue.put(None)  # Poison pill
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("Async STT worker stopped.")

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if chunk is None:
                # Poison pill
                break

            t0 = time.perf_counter()
            try:
                segments = self.provider.transcribe(chunk, language=self.preferred_language)
                dt = time.perf_counter() - t0

                with self._lock:
                    self.metrics.total_chunks_processed += 1
                    self.metrics.total_segments_produced += len(segments)
                    self.metrics.transcription_time_sec += dt
                    if self.metrics.audio_duration_sec > 0:
                        self.metrics.real_time_factor = (
                            self.metrics.transcription_time_sec / self.metrics.audio_duration_sec
                        )
                    self.metrics.queue_backlog_chunks = self._queue.qsize()

                if segments:
                    self.on_segments_ready(segments)

                logger.debug(
                    f"Transcribed chunk {chunk.chunk_id} in {dt:.3f}s "
                    f"({len(segments)} segments, RTF: {self.metrics.real_time_factor:.2f})"
                )
            except Exception as e:
                logger.error(f"Error transcribing chunk {chunk.chunk_id}: {e}")
            finally:
                self._queue.task_done()
