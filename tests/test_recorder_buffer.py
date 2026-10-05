"""Tests for bounded event queue and backpressure policies."""

from teach_a_skill.recorder.buffer import AsyncPersistenceWorker, BoundedEventQueue
from teach_a_skill.recorder.events import Event, EventPriority, EventType


def test_queue_enqueues_within_bounds():
    q = BoundedEventQueue(maxsize=100)
    evt = Event.create("s1", 1, EventType.MOUSE_CLICK, "mouse", priority=EventPriority.CRITICAL)
    assert q.put(evt) is True
    assert q.qsize() == 1
    assert q.metrics.events_enqueued == 1


def test_backpressure_drops_low_priority_first():
    # Small queue of size 10 to test watermark limits
    q = BoundedEventQueue(maxsize=10)

    # Fill queue to 8 items (80% full)
    for i in range(8):
        evt = Event.create("s1", i, EventType.MOUSE_MOVE, "mouse", priority=EventPriority.MEDIUM)
        assert q.put(evt) is True

    assert q.qsize() == 8

    # 9th event with LOW priority (redundant screenshot): should be dropped!
    low_evt = Event.create(
        "s1", 9, EventType.SCREENSHOT_CAPTURED, "screen", priority=EventPriority.LOW
    )
    assert q.put(low_evt) is False
    assert q.metrics.events_dropped_low == 1

    # But a CRITICAL event (click) must STILL be enqueued!
    crit_evt = Event.create(
        "s1", 10, EventType.MOUSE_CLICK, "mouse", priority=EventPriority.CRITICAL
    )
    assert q.put(crit_evt) is True
    assert q.metrics.events_dropped_critical == 0


def test_async_persistence_worker_drain():
    q = BoundedEventQueue(maxsize=100)
    persisted: list[Event] = []

    worker = AsyncPersistenceWorker(
        event_queue=q,
        persist_fn=lambda e: persisted.append(e),
    )
    worker.start()

    # Enqueue 10 events
    for i in range(10):
        evt = Event.create("s_work", i, EventType.KEY_DOWN, "keyboard")
        q.put(evt)

    # Stop worker gracefully flushes all items
    worker.stop()

    assert len(persisted) == 10
    assert q.qsize() == 0
    assert q.metrics.events_persisted == 10
