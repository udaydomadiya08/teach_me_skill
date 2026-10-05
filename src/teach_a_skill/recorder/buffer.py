"""Thread-safe bounded event buffering and backpressure enforcement."""

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from teach_a_skill.core.logging import get_logger
from teach_a_skill.recorder.events import Event, EventPriority

logger = get_logger("teach_a_skill.recorder.buffer")


@dataclass
class BufferMetrics:
    events_enqueued: int = 0
    events_persisted: int = 0
    events_dropped_low: int = 0
    events_dropped_medium: int = 0
    events_dropped_critical: int = 0  # Must always remain 0
    high_watermark: int = 0
    current_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_enqueued": self.events_enqueued,
            "events_persisted": self.events_persisted,
            "events_dropped_low": self.events_dropped_low,
            "events_dropped_medium": self.events_dropped_medium,
            "events_dropped_critical": self.events_dropped_critical,
            "high_watermark": self.high_watermark,
            "current_size": self.current_size,
        }


class BoundedEventQueue:
    """Bounded, thread-safe in-memory queue enforcing backpressure policies."""

    def __init__(self, maxsize: int = 10000) -> None:
        self.maxsize = maxsize
        self._queue: queue.Queue[Optional[Event]] = queue.Queue(maxsize=maxsize)
        self.metrics = BufferMetrics()
        self._lock = threading.Lock()

    def put(self, event: Event) -> bool:
        """Enqueue event respecting priority-based backpressure rules.

        Returns True if enqueued, False if dropped due to congestion.
        """
        with self._lock:
            qsize = self._queue.qsize()
            self.metrics.current_size = qsize
            if qsize > self.metrics.high_watermark:
                self.metrics.high_watermark = qsize

            fill_ratio = qsize / self.maxsize

            # Priority 1: Backpressure drop for LOW priority (e.g. redundant screenshots)
            if fill_ratio >= 0.80 and event.priority == EventPriority.LOW:
                self.metrics.events_dropped_low += 1
                return False

            # Priority 2: Backpressure drop for MEDIUM priority (e.g. dense mouse moves)
            if fill_ratio >= 0.90 and event.priority == EventPriority.MEDIUM:
                self.metrics.events_dropped_medium += 1
                return False

            # Priority 3: CRITICAL and HIGH events are enqueued; if queue is completely full,
            # wait briefly or drop lowest priority event to make room
            try:
                self._queue.put_nowait(event)
                self.metrics.events_enqueued += 1
                return True
            except queue.Full:
                if event.priority == EventPriority.CRITICAL:
                    # Never drop CRITICAL: block with timeout to allow worker to drain
                    try:
                        self._queue.put(event, timeout=0.1)
                        self.metrics.events_enqueued += 1
                        return True
                    except queue.Full:
                        self.metrics.events_dropped_critical += 1
                        logger.error("Critical event queue overflow! Event was lost.")
                        return False
                else:
                    self.metrics.events_dropped_low += 1
                    return False

    def get(self, timeout: Optional[float] = None) -> Optional[Event]:
        """Fetch next event for persistence. Returns None on poison pill."""
        event = self._queue.get(timeout=timeout)
        with self._lock:
            self.metrics.current_size = self._queue.qsize()
        return event

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()

    def get_metrics(self) -> BufferMetrics:
        with self._lock:
            self.metrics.current_size = self._queue.qsize()
            return self.metrics


class AsyncPersistenceWorker:
    """Background worker draining events from BoundedEventQueue and saving to disk."""

    def __init__(
        self,
        event_queue: BoundedEventQueue,
        persist_fn: Callable[[Event], None],
        flush_interval_sec: float = 0.5,
    ) -> None:
        self.queue = event_queue
        self.persist_fn = persist_fn
        self.flush_interval_sec = flush_interval_sec

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="teach-skill-recorder-persistence",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal worker to stop, drain all remaining events, and join."""
        self._stop_event.set()
        # Post poison pill to unblock queue.get
        try:
            self.queue._queue.put(None, timeout=0.5)
        except Exception:
            pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _worker_loop(self) -> None:
        while True:
            try:
                event = self.queue.get(timeout=0.2)
                if event is None:
                    # Poison pill or stop signal
                    self.queue.task_done()
                    break

                self.persist_fn(event)
                with self.queue._lock:
                    self.queue.metrics.events_persisted += 1
                self.queue.task_done()
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue
            except Exception as e:
                logger.error(f"Error persisting event in worker: {e}")
                self.queue.task_done()

        # Final drain of remaining items
        while True:
            try:
                event = self.queue._queue.get_nowait()
                if event is not None:
                    self.persist_fn(event)
                    with self.queue._lock:
                        self.queue.metrics.events_persisted += 1
                self.queue.task_done()
            except queue.Empty:
                break
            except Exception:
                break
