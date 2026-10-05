"""Bounded in-memory audio queue and streaming persistence buffer."""

import queue
import threading
from dataclasses import dataclass
from typing import Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.teaching.audio.wav import AudioChunk

logger = get_logger("teach_a_skill.teaching.audio.buffer")


@dataclass
class AudioBufferMetrics:
    """Metrics tracking audio queue status and throughput."""

    chunks_enqueued: int = 0
    chunks_persisted: int = 0
    chunks_dropped: int = 0
    bytes_buffered: int = 0
    high_watermark: int = 0
    current_size: int = 0


class BoundedAudioBuffer:
    """Thread-safe bounded queue for captured AudioChunks preventing memory bloat."""

    def __init__(self, maxsize: int = 100) -> None:
        # 100 chunks of 10s = 16.6 minutes of audio maximum backlog
        self.maxsize = maxsize
        self._queue: queue.Queue[Optional[AudioChunk]] = queue.Queue(maxsize=maxsize)
        self.metrics = AudioBufferMetrics()
        self._lock = threading.Lock()

    def put(self, chunk: Optional[AudioChunk], block: bool = True, timeout: float = 2.0) -> bool:
        """Enqueue an audio chunk. Audio capture has high priority, so it will block briefly before shedding."""
        with self._lock:
            qsize = self._queue.qsize()
            self.metrics.current_size = qsize
            if qsize > self.metrics.high_watermark:
                self.metrics.high_watermark = qsize

        try:
            self._queue.put(chunk, block=block, timeout=timeout)
            with self._lock:
                self.metrics.chunks_enqueued += 1
                if chunk is not None:
                    self.metrics.bytes_buffered += chunk.size_bytes
                self.metrics.current_size = self._queue.qsize()
            return True
        except queue.Full:
            with self._lock:
                self.metrics.chunks_dropped += 1
            logger.error(
                "Audio buffer overflow! An audio chunk was dropped due to disk persistence saturation."
            )
            return False

    def get(self, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """Retrieve next audio chunk for persistence. Returns None on poison pill."""
        chunk = self._queue.get(timeout=timeout)
        with self._lock:
            self.metrics.current_size = self._queue.qsize()
            if chunk is not None:
                self.metrics.chunks_persisted += 1
                self.metrics.bytes_buffered = max(0, self.metrics.bytes_buffered - chunk.size_bytes)
        return chunk

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()
